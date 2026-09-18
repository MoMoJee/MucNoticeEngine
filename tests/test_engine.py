from datetime import datetime, timedelta

from muc_notice_engine.config import Settings
from muc_notice_engine.core.engine import NoticeEngine
from muc_notice_engine.core.fetcher import CHINA_TZ
from muc_notice_engine.core.models import Notice
from muc_notice_engine.core.storage import NoticeStore


def _notice(i: int, days_ago: int = 0) -> Notice:
    published = datetime.now(CHINA_TZ) - timedelta(days=days_ago)
    return Notice(
        id=f"test:{i}",
        title=f"通知 {i}",
        link=f"https://example.com/{i}",
        source="测试",
        source_key="test",
        category="test",
        date=published.strftime("%Y-%m-%d %H:%M"),
        pub_date=published.strftime("%a, %d %b %Y %H:%M:%S +0800"),
        published_at=published,
        external_id=f"ext-{i}",
    )


class _FakeFetcher:
    def __init__(self, batches):
        self.batches = list(batches)
        self.rss_written = 0
        self.portal_calls = []

    async def fetch_notices(self, source_keys=None):
        return self.batches.pop(0) if self.batches else []

    async def write_rss(self, notices):
        self.rss_written += 1

    async def fetch_portal_type(self, type_id, *, from_page=1, to_page=1, search_value=None):
        self.portal_calls.append((type_id, from_page, to_page, search_value))
        return self.batches.pop(0) if self.batches else []


class _Recorder:
    def __init__(self):
        self.calls = []

    async def publish(self, notices):
        self.calls.append(notices)


class _FakeArchiver:
    def __init__(self):
        self.items = []

    async def enqueue(self, notice, *, force=False):
        self.items.append((notice, force))

    async def enqueue_many(self, notices, *, force=False):
        self.items.extend((n, force) for n in notices)


def _engine(tmp_path, batches, publishers=None, archiver=None, **overrides):
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "t.db",
        poll_on_start=False,
        **overrides,
    )
    store = NoticeStore(settings.db_path)
    fetcher = _FakeFetcher(batches)
    engine = NoticeEngine(
        settings,
        fetcher,
        store,
        publishers=publishers,
        archiver=archiver,
    )
    return engine, store, fetcher


async def test_first_poll_is_backfill_and_does_not_push(tmp_path):
    recorder = _Recorder()
    engine, store, _ = _engine(tmp_path, [[_notice(1)], [_notice(2)]], [recorder])

    assert await engine.poll_once() == []
    assert recorder.calls == []
    assert await store.get_meta("initial_poll_done") is not None

    fresh = await engine.poll_once()
    assert [n.id for n in fresh] == ["test:2"]
    assert len(recorder.calls) == 1


async def test_backfill_push_setting_allows_first_poll(tmp_path):
    recorder = _Recorder()
    engine, _, _ = _engine(
        tmp_path, [[_notice(1)]], [recorder], backfill_push=True
    )
    fresh = await engine.poll_once()
    assert [n.id for n in fresh] == ["test:1"]
    assert len(recorder.calls) == 1


async def test_archive_enqueue_respects_cutoff_and_limit(tmp_path):
    archiver = _FakeArchiver()
    engine, _, _ = _engine(
        tmp_path,
        [[_notice(1, days_ago=1), _notice(2, days_ago=400), _notice(3, days_ago=2)]],
        archiver=archiver,
        archive_window_days=90,
        archive_enqueue_limit_per_poll=1,
    )
    await engine.poll_once()
    assert [n.id for n, _ in archiver.items] == ["test:1"]


async def test_manual_fetch_is_backfill_without_rss(tmp_path):
    recorder = _Recorder()
    engine, _, fetcher = _engine(tmp_path, [[_notice(9)]], [recorder])

    new = await engine.manual_fetch_portal(
        11, from_page=2, to_page=3, search_value="推免"
    )
    assert [n.id for n in new] == ["test:9"]
    assert recorder.calls == []
    assert fetcher.portal_calls == [(11, 2, 3, "推免")]
    assert fetcher.rss_written == 0


async def test_archive_cutoff_prefers_later(tmp_path):
    engine, _, _ = _engine(
        tmp_path,
        [],
        archive_window_days=90,
        archive_floor_date="2026-08-31",
    )
    floor = datetime(2026, 8, 31, tzinfo=CHINA_TZ)

    # 2030 场景：滚动窗口比固定 floor 晚 -> 取窗口，不拉 2026 起的历史
    now_2030 = datetime(2030, 6, 1, tzinfo=CHINA_TZ)
    assert engine.archive_cutoff(now=now_2030) == now_2030 - timedelta(days=90)
    assert engine.archive_cutoff(now=now_2030) > floor

    # 当前（2026-09）：floor 比窗口晚 -> 取 floor
    now_2026 = datetime(2026, 9, 19, tzinfo=CHINA_TZ)
    assert engine.archive_cutoff(now=now_2026) == floor


async def test_archive_cutoff_uses_floor_date(tmp_path):
    engine, _, _ = _engine(
        tmp_path,
        [],
        archive_window_days=0,
        archive_floor_date="2999-01-01",
    )
    assert engine.archive_cutoff() == datetime(2999, 1, 1, tzinfo=CHINA_TZ)

    engine2, _, _ = _engine(
        tmp_path,
        [],
        archive_window_days=90,
        archive_floor_date="2000-01-01",
    )
    oldest = datetime.now(CHINA_TZ) - timedelta(days=90, minutes=1)
    assert engine2.archive_cutoff() > oldest
