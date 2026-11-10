from datetime import datetime

import httpx

from muc_notice_engine.config import Settings
from muc_notice_engine.core import archive as archive_mod
from muc_notice_engine.core.archive import ArchiveQueue, ArchiveStore, safe_filename
from muc_notice_engine.core.fetcher import CHINA_TZ
from muc_notice_engine.core.models import Attachment, Notice, NoticeDetail
from muc_notice_engine.core.storage import NoticeStore

DOWNLOAD_URL = (
    "https://my.muc.edu.cn/comsys-portal-notice-web/download"
    "?id=annex-1&notice_id=ext-1"
)


def _notice() -> Notice:
    return Notice(
        id="test:hash1",
        title="测试通知",
        link="https://example.com/1",
        source="测试来源",
        source_key="test",
        category="test",
        date="2026-09-01 10:00",
        pub_date="Tue, 01 Sep 2026 10:00:00 +0800",
        published_at=datetime(2026, 9, 1, tzinfo=CHINA_TZ),
        external_id="ext-1",
    )


class _StubAuth:
    def __init__(self, client):
        self._client = client

    async def get_authenticated_client(self):
        return self._client


def test_safe_filename():
    assert safe_filename("../evil.exe") == "evil.exe"
    assert safe_filename("..\\evil.exe") == "evil.exe"
    assert safe_filename("CON.txt") == "_CON.txt"
    assert safe_filename("") == "file"
    assert safe_filename("///") == "file"
    assert safe_filename("a" * 300).endswith("a")
    assert len(safe_filename("a" * 300)) <= 120


async def test_archive_store_saves_content_and_attachment(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"xlsx-bytes",
            headers={
                "content-disposition": 'attachment; filename="annex.xlsx"',
                "content-type": "application/vnd.ms-excel",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    archive_store = ArchiveStore(settings, store, _StubAuth(client))
    notice = _notice()
    await store.upsert_notices([notice])
    detail = NoticeDetail(
        notice=notice,
        content_html="<p>你好</p>",
        plain_text="你好",
        attachments=[
            Attachment(annex_id="annex-1", name="名单.xlsx", url=DOWNLOAD_URL)
        ],
    )
    records = await archive_store.archive(detail)

    kinds = sorted(r["kind"] for r in records)
    assert kinds == ["attachment", "content", "content", "content"]

    assets = await store.get_assets(notice.id)
    names = {a["filename"] for a in assets}
    assert {"content.html", "content.txt", "meta.json"} <= names
    attachment = next(a for a in assets if a["kind"] == "attachment")
    assert attachment["size"] == len("xlsx-bytes")

    directory = archive_store.notice_dir(notice)
    assert (directory / "content.html").read_text(encoding="utf-8") == "<p>你好</p>"
    assert (directory / "content.txt").read_text(encoding="utf-8") == "你好"
    assert (directory / "files" / "01-名单.xlsx").is_file()
    await client.aclose()


async def test_archive_store_rejects_html_download(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login page</html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    archive_store = ArchiveStore(settings, store, _StubAuth(client))
    notice = _notice()
    await store.upsert_notices([notice])
    detail = NoticeDetail(
        notice=notice,
        content_html="<p>hi</p>",
        plain_text="hi",
        attachments=[
            Attachment(annex_id="annex-1", name="名单.xlsx", url=DOWNLOAD_URL)
        ],
    )
    records = await archive_store.archive(detail)
    assert all(r["kind"] == "content" for r in records)
    assets = await store.get_assets(notice.id)
    assert all(a["kind"] == "content" for a in assets)
    await client.aclose()


async def test_archive_store_limits_images_separately_from_files(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "t.db",
        archive_max_per_notice=1,
        archive_max_images_per_notice=1,
        archive_host_interval_ms=0,
    )
    store = NoticeStore(settings.db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".png"):
            return httpx.Response(
                200, content=b"png-bytes", headers={"content-type": "image/png"}
            )
        return httpx.Response(
            200,
            content=b"file-bytes",
            headers={"content-type": "application/octet-stream"},
        )

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("headers", None)
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(archive_mod.httpx, "AsyncClient", factory)
    archive_store = ArchiveStore(settings, store, None)
    notice = _notice()
    await store.upsert_notices([notice])
    detail = NoticeDetail(
        notice=notice,
        content_html="<p>hi</p>",
        plain_text="hi",
        attachments=[
            Attachment(annex_id="", name="1.png", url="https://x.test/1.png", kind="image"),
            Attachment(annex_id="", name="2.png", url="https://x.test/2.png", kind="image"),
            Attachment(annex_id="", name="a.bin", url="https://x.test/a.bin"),
            Attachment(annex_id="", name="b.bin", url="https://x.test/b.bin"),
        ],
    )
    records = await archive_store.archive(detail)
    attachment_names = sorted(
        r["remote_name"] for r in records if r["kind"] == "attachment"
    )
    assert attachment_names == ["1.png", "a.bin"]


async def test_archive_store_retries_server_error(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "t.db",
        archive_external_retries=1,
        archive_host_interval_ms=0,
    )
    store = NoticeStore(settings.db_path)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(
            200, content=b"png-bytes", headers={"content-type": "image/png"}
        )

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("headers", None)
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(archive_mod.httpx, "AsyncClient", factory)
    archive_store = ArchiveStore(settings, store, None)
    notice = _notice()
    await store.upsert_notices([notice])
    detail = NoticeDetail(
        notice=notice,
        content_html="<p>hi</p>",
        plain_text="hi",
        attachments=[
            Attachment(annex_id="", name="a.png", url="https://x.test/a.png", kind="image")
        ],
    )
    records = await archive_store.archive(detail)
    assert [r["kind"] for r in records].count("attachment") == 1
    assert calls["count"] == 2


async def test_evict_to_limit_removes_oldest(tmp_path):
    settings = Settings(
        data_dir=tmp_path, db_path=tmp_path / "t.db", archive_total_limit_gb=1
    )
    store = NoticeStore(settings.db_path)
    archive_store = ArchiveStore(settings, store, None)
    notice = _notice()
    await store.upsert_notices([notice])

    directory = archive_store.notice_dir(notice) / "files"
    directory.mkdir(parents=True)
    rows = []
    for i in range(2):
        path = directory / f"{i}.bin"
        path.write_bytes(b"x")
        rows.append(
            {
                "kind": "attachment",
                "filename": f"{i}.bin",
                "local_path": path.relative_to(archive_store.root).as_posix(),
                "size": 600 * 1024**2,
                "sha1": "x",
            }
        )
    await store.replace_assets(notice.id, rows)
    assert await store.total_asset_size() == 1200 * 1024**2

    removed = await archive_store.evict_to_limit(force=True)
    assert removed == 1
    assert await store.total_asset_size() == 600 * 1024**2
    assert (directory / "0.bin").exists() is False
    assert (directory / "1.bin").exists() is True


async def test_archive_queue_processes_and_fills_preview(tmp_path):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    store = NoticeStore(settings.db_path)
    archive_store = ArchiveStore(settings, store, None)

    class _FakeFetcher:
        async def fetch_detail(self, notice):
            return NoticeDetail(
                notice=notice,
                content_html="<p>队列正文</p>",
                plain_text="队列正文",
                attachments=[],
            )

    notice = _notice()
    await store.upsert_notices([notice])
    queue = ArchiveQueue(settings, store, _FakeFetcher(), archive_store)
    await queue.start()
    try:
        await queue.enqueue(notice)
        await queue.join()
    finally:
        await queue.stop()

    stored = await store.get(notice.id)
    assert stored is not None and stored.content == "队列正文"
    assets = await store.get_assets(notice.id)
    assert {a["filename"] for a in assets} >= {"content.html", "content.txt", "meta.json"}
    assert queue.stats["processed"] == 1
