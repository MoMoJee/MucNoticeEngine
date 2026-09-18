import time
import zipfile
from datetime import datetime
from io import BytesIO

from fastapi.testclient import TestClient

from muc_notice_engine.config import Settings
from muc_notice_engine.core.archive import ArchiveStore
from muc_notice_engine.core.engine import NoticeEngine
from muc_notice_engine.core.fetcher import CHINA_TZ
from muc_notice_engine.core.models import Notice
from muc_notice_engine.core.sources import SOURCES
from muc_notice_engine.core.storage import NoticeStore
from muc_notice_engine.transport.api import create_app
from muc_notice_engine.transport.publishers import SubscriberStore


def _notice(i: int = 1) -> Notice:
    return Notice(
        id=f"test:hash{i}",
        title=f"通知 {i}",
        link=f"https://example.com/{i}",
        source="测试来源",
        source_key="test",
        category="test",
        date="2026-09-01 10:00",
        pub_date="Tue, 01 Sep 2026 10:00:00 +0800",
        published_at=datetime(2026, 9, 1, tzinfo=CHINA_TZ),
        external_id=f"ext-{i}",
    )


class _FakeFetcher:
    def __init__(self, notices=None):
        self.notices = list(notices or [])
        self.portal_calls = []

    async def fetch_notices(self, source_keys=None):
        return []

    async def write_rss(self, notices):  # pragma: no cover - not used here
        return None

    async def fetch_portal_type(
        self, type_id, *, from_page=1, to_page=1, search_value=None
    ):
        self.portal_calls.append((type_id, from_page, to_page, search_value))
        return list(self.notices)


class _RecordingArchiver:
    def __init__(self):
        self.items = []
        self.pending = 0

    async def enqueue(self, notice, *, force=False):
        self.items.append((notice, force))

    async def enqueue_many(self, notices, *, force=False):
        self.items.extend((n, force) for n in notices)


def _client(tmp_path, token: str = "", store=None, archive_store=None,
            archiver=None, fetcher=None):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db", api_token=token)
    store = store or NoticeStore(settings.db_path)
    subscribers = SubscriberStore(settings.db_path)
    fetcher = fetcher or _FakeFetcher()
    engine = NoticeEngine(settings, fetcher=fetcher, store=store, archiver=archiver)
    app = create_app(
        engine=engine,
        store=store,
        settings=settings,
        fetcher=fetcher,
        subscribers=subscribers,
        archive_store=archive_store,
    )
    return TestClient(app)


def test_health_is_public(tmp_path):
    resp = _client(tmp_path).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["archive_enabled"] is False


def test_sources_endpoint_lists_all(tmp_path):
    resp = _client(tmp_path).get("/api/sources")
    assert resp.status_code == 200
    assert len(resp.json()) == len(SOURCES)


def test_token_required_when_configured(tmp_path):
    client = _client(tmp_path, token="secret")
    assert client.get("/api/notices").status_code == 401
    ok = client.get("/api/notices", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_subscriber_crud(tmp_path):
    client = _client(tmp_path)
    created = client.post(
        "/api/subscribers", json={"url": "https://example.com/hook", "secret": "s"}
    )
    assert created.status_code == 201
    sub_id = created.json()["id"]

    assert len(client.get("/api/subscribers").json()) == 1
    assert client.delete(f"/api/subscribers/{sub_id}").status_code == 200
    assert client.get("/api/subscribers").json() == []


def test_subscriber_rejects_bad_url(tmp_path):
    resp = _client(tmp_path).post("/api/subscribers", json={"url": "ftp://x"})
    assert resp.status_code == 422


async def test_check_manual_portal_params(tmp_path):
    fetcher = _FakeFetcher([_notice(7)])
    client = _client(tmp_path, fetcher=fetcher)
    resp = client.post(
        "/api/check",
        json={"type": 11, "from_page": 2, "to_page": 3, "search_value": "推免"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_count"] == 1
    assert body["backfill"] is True
    assert fetcher.portal_calls == [(11, 2, 3, "推免")]


async def test_archive_endpoint_enqueues_force(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)
    notice = _notice(1)
    await store.upsert_notices([notice])
    archiver = _RecordingArchiver()
    client = _client(tmp_path, store=store, archiver=archiver)

    resp = client.post(f"/api/notices/{notice.id}/archive")
    assert resp.status_code == 202
    assert archiver.items == [(notice, True)]


async def test_archive_endpoint_rejects_when_disabled(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)
    notice = _notice(1)
    await store.upsert_notices([notice])
    client = _client(tmp_path, store=store)

    resp = client.post(f"/api/notices/{notice.id}/archive")
    assert resp.status_code == 409


async def test_content_and_files_endpoints_touch_access(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)
    archive_store = ArchiveStore(settings, store, None)
    notice = _notice(1)
    await store.upsert_notices([notice])

    directory = archive_store.notice_dir(notice)
    (directory / "files").mkdir(parents=True)
    (directory / "content.html").write_text("<p>正文</p>", encoding="utf-8")
    (directory / "content.txt").write_text("正文", encoding="utf-8")
    (directory / "files" / "01-a.xlsx").write_text("x", encoding="utf-8")

    def rel(path):
        return path.relative_to(archive_store.root).as_posix()

    await store.replace_assets(
        notice.id,
        [
            {"kind": "content", "filename": "content.html",
             "local_path": rel(directory / "content.html"), "size": 12, "sha1": "a"},
            {"kind": "content", "filename": "content.txt",
             "local_path": rel(directory / "content.txt"), "size": 6, "sha1": "b"},
            {"kind": "attachment", "filename": "01-a.xlsx",
             "local_path": rel(directory / "files" / "01-a.xlsx"), "size": 1, "sha1": "c"},
        ],
    )
    client = _client(tmp_path, store=store, archive_store=archive_store)

    before = (await store.get_assets(notice.id))[0]["first_download_at"]
    time.sleep(0.01)

    content = client.get(f"/api/notices/{notice.id}/content")
    assert content.status_code == 200
    assert "正文" in content.text

    bundle_resp = client.get(f"/api/notices/{notice.id}/content.zip")
    assert bundle_resp.status_code == 200
    with zipfile.ZipFile(BytesIO(bundle_resp.content)) as bundle:
        names = set(bundle.namelist())
        assert {"content.html", "content.txt", "files/01-a.xlsx"} <= names

    listing = client.get(f"/api/notices/{notice.id}/files").json()
    assert listing["count"] == 3

    single = client.get(
        f"/api/notices/{notice.id}/files", params={"name": "content.html"}
    )
    assert single.status_code == 200

    bad = client.get(
        f"/api/notices/{notice.id}/files", params={"name": "../content.html"}
    )
    assert bad.status_code == 404

    assert client.get(f"/api/notices/{notice.id}").status_code == 200

    after = (await store.get_assets(notice.id))[0]["last_access_at"]
    assert after > before


async def test_content_preview_fallback(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)
    notice = _notice(2)
    notice.content = "预览正文"
    await store.upsert_notices([notice])
    client = _client(tmp_path, store=store)

    resp = client.get(f"/api/notices/{notice.id}/content")
    assert resp.status_code == 200
    assert resp.headers["x-muc-content"] == "preview"
    assert "预览正文" in resp.text
