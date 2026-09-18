from datetime import datetime

from muc_notice_engine.core.fetcher import CHINA_TZ
from muc_notice_engine.core.models import Notice
from muc_notice_engine.core.storage import NoticeStore


def _notice(i: int) -> Notice:
    return Notice(
        id=f"src:hash{i}",
        title=f"通知 {i}",
        link=f"https://example.com/{i}",
        source="测试来源",
        source_key="test",
        category="test",
        date="2026-01-01 00:00",
        pub_date="Thu, 01 Jan 2026 00:00:00 +0800",
        published_at=datetime(2026, 1, 1, tzinfo=CHINA_TZ),
    )


async def test_upsert_is_deduplicating(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    n1 = _notice(1)

    assert await store.upsert_notices([n1]) == [n1]
    assert await store.upsert_notices([n1]) == []
    assert await store.count() == 1


async def test_query_filters_and_orders(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    await store.upsert_notices([_notice(1), _notice(2)])

    items = await store.query(source_keys=["test"], limit=10)
    assert len(items) == 2

    assert await store.query(source_keys=["other"]) == []
    matched = await store.query(q="通知 2")
    assert matched[0].id == "src:hash2"


async def test_mark_pushed_and_stats(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    await store.upsert_notices([_notice(1), _notice(2)])
    await store.mark_pushed(["src:hash1"])

    stats = await store.stats()
    assert stats[0]["source_key"] == "test"
    assert stats[0]["total"] == 2
    assert stats[0]["pushed"] == 1
