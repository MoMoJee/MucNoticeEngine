from fastapi.testclient import TestClient

from muc_notice_engine.config import Settings
from muc_notice_engine.core.engine import NoticeEngine
from muc_notice_engine.core.sources import SOURCES
from muc_notice_engine.core.storage import NoticeStore
from muc_notice_engine.transport.api import create_app
from muc_notice_engine.transport.publishers import SubscriberStore


class _FakeFetcher:
    async def fetch_notices(self, source_keys=None):
        return []

    async def write_rss(self, notices):  # pragma: no cover - not used here
        return None


def _client(tmp_path, token: str = ""):
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db", api_token=token)
    store = NoticeStore(settings.db_path)
    subscribers = SubscriberStore(settings.db_path)
    engine = NoticeEngine(settings, fetcher=_FakeFetcher(), store=store)
    app = create_app(
        engine=engine,
        store=store,
        settings=settings,
        fetcher=_FakeFetcher(),
        subscribers=subscribers,
    )
    return TestClient(app)


def test_health_is_public(tmp_path):
    resp = _client(tmp_path).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


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
