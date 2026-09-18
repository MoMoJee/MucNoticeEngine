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


async def test_query_matches_summary_and_content(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    notice = _notice(1)
    notice.summary = "智慧校园建设进展"
    notice.content = "网络强国 主题学习"
    await store.upsert_notices([notice])

    assert [n.id for n in await store.query(q="智慧校园建设")] == ["src:hash1"]
    assert [n.id for n in await store.query(q="网络强国")] == ["src:hash1"]
    assert [n.id for n in await store.query(q="通知 1")] == ["src:hash1"]
    assert await store.query(q="确定不存在的词") == []


async def test_query_escapes_like_wildcards(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    literal = _notice(1)
    literal.title = "补贴 100% 到账"
    other = _notice(2)
    other.title = "补贴 100元 到账"
    underscore = _notice(3)
    underscore.title = "a_b 文件"
    plain = _notice(4)
    plain.title = "axb 文件"
    await store.upsert_notices([literal, other, underscore, plain])

    assert [n.id for n in await store.query(q="100%")] == ["src:hash1"]
    assert [n.id for n in await store.query(q="a_b")] == ["src:hash3"]
    # 反斜杠按字面处理：库里没有 "a\_b" 这个串，所以不该命中
    assert await store.query(q="a\\_b") == []


async def test_mark_pushed_and_stats(tmp_path):
    store = NoticeStore(tmp_path / "t.db")
    await store.upsert_notices([_notice(1), _notice(2)])
    await store.mark_pushed(["src:hash1"])

    stats = await store.stats()
    assert stats[0]["source_key"] == "test"
    assert stats[0]["total"] == 2
    assert stats[0]["pushed"] == 1
