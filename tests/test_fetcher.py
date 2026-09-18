import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from muc_notice_engine.config import Settings
from muc_notice_engine.core import fetcher as fetcher_mod
from muc_notice_engine.core.fetcher import CHINA_TZ, MucRssService
from muc_notice_engine.core.models import Notice
from muc_notice_engine.core.sources import SOURCES_BY_KEY


def _service(tmp_path, **kwargs) -> MucRssService:
    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db", **kwargs)
    return MucRssService(settings)


def _portal_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("getNoticeByPage"):
        form = parse_qs(request.content.decode())
        page = int(form.get("currentPage", ["1"])[0])
        tables = []
        if page <= 2:
            tables = [
                {
                    "notice_id": f"10{page}{i}",
                    "notice_title": f"通知 {page}-{i}",
                    "notice_release_time": "2026-09-01 10:00:00",
                    "notice_content": "<p>正文</p>",
                }
                for i in range(2)
            ]
        return httpx.Response(
            200,
            json={
                "state": True,
                "datas": {"tables": tables, "page": {"totalCounts": 2}},
            },
        )
    return httpx.Response(404)


async def test_portal_pagination_collects_all_pages(tmp_path):
    service = _service(tmp_path, portal_page_limit=3)
    source = SOURCES_BY_KEY["my_gsgg"]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_portal_handler)
    ) as client:
        notices = await service._fetch_portal_pages(
            client, source, 11, from_page=1, to_page=3, page_size=20
        )
    assert [n.external_id for n in notices] == ["1010", "1011", "1020", "1021"]
    assert all(n.source_key == "my_gsgg" for n in notices)
    assert notices[0].content == "正文"


async def test_fetch_portal_detail_parses_annex_and_images(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "datas": {
                    "notice_info": {
                        "notice_content": '<p>正文</p><img src="/upload/a.png">',
                        "notice_annext": [
                            {
                                "notice_annex_id": "annex-1",
                                "notice_annex_name": "名单.xlsx",
                                "suffix": "xlsx",
                            }
                        ],
                    }
                }
            },
        )

    settings = Settings(data_dir=tmp_path, db_path=tmp_path / "t.db")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    class _StubAuth:
        async def get_authenticated_client(self):
            return client

        def invalidate(self):
            return None

    service = MucRssService(settings, _StubAuth())
    notice = Notice(
        id="my_gsgg:x",
        title="t",
        link="",
        source="信息门户 - 公示公告",
        source_key="my_gsgg",
        category="notice",
        date="",
        pub_date="",
        published_at=datetime(2026, 9, 1, tzinfo=CHINA_TZ),
        external_id="358513",
    )
    detail = await service.fetch_detail(notice)
    assert detail is not None
    assert "<p>正文</p>" in detail.content_html
    kinds = [(a.kind, a.name) for a in detail.attachments]
    assert kinds == [("file", "名单.xlsx"), ("image", "a.png")]
    assert detail.attachments[0].url.startswith(
        "https://my.muc.edu.cn/comsys-portal-notice-web/download"
    )
    assert detail.attachments[1].url == "https://my.muc.edu.cn/upload/a.png"
    await client.aclose()


async def test_public_detail_extracts_article(tmp_path, monkeypatch):
    html = (
        "<html><body><div class='v_news_content'>"
        "<p>公开源正文内容</p></div></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("headers", None)
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(fetcher_mod.httpx, "AsyncClient", factory)
    service = _service(tmp_path)
    notice = Notice(
        id="muc_tzgg:x",
        title="t",
        link="https://www.muc.edu.cn/info/1/2.htm",
        source="中央民族大学 - 通知公告",
        source_key="muc_tzgg",
        category="muc",
        date="",
        pub_date="",
        published_at=datetime(2026, 9, 1, tzinfo=CHINA_TZ),
        external_id="info-1-2.htm",
    )
    detail = await service.fetch_detail(notice)
    assert detail is not None
    assert "公开源正文内容" in detail.plain_text
    assert detail.attachments == []


async def test_public_source_resolves_onclick_links(tmp_path):
    html = (
        "<html><body><ul class='ulminheight'>"
        "<li><span class='news__title'><a href='javascript:void(0)' "
        "onclick=\"opennews('../info/1041/6535.htm')\">推免成绩公示</a></span>"
        "<span class='news__date'>[2026年09月18日]</span></li>"
        "<li><span class='news__title'><a href='../info/1041/6505.htm'>复试名单</a>"
        "</span><span class='news__date'>[2026-09-14]</span></li>"
        "<li><span class='news__title'><a href='javascript:void(0)'>无链接</a>"
        "</span></li>"
        "</ul></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    source = {
        "key": "xg_test",
        "name": "信工测试",
        "url": "https://xingong.muc.edu.cn/index/tzgg.htm",
        "selector": "ul.ulminheight .news__title a",
        "parser": lambda tag: tag.get_text(" ", strip=True),
        "category": "xingong",
    }
    service = _service(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notices = await service._fetch_source_notices(client, source)

    assert [n.link for n in notices] == [
        "https://xingong.muc.edu.cn/info/1041/6535.htm",
        "https://xingong.muc.edu.cn/info/1041/6505.htm",
    ]
    assert [n.date for n in notices] == ["2026-09-18 00:00", "2026-09-14 00:00"]


async def test_public_source_parses_lxy_list(tmp_path):
    html = (
        "<div class='new_list3'><dl><dd>"
        "<a class='fl' href='info/1098/3253.htm'>复试成绩公示</a>"
        "<span class='fr gray'>2026年09月14日</span></dd></dl></div>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    source = {
        "key": "lxy_test",
        "name": "理学院测试",
        "url": "https://lxy.muc.edu.cn/xydt1.htm",
        "selector": 'div.new_list3 dd a[href*="info/"]',
        "parser": lambda tag: tag.get_text(" ", strip=True),
        "category": "lxy",
    }
    service = _service(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notices = await service._fetch_source_notices(client, source)

    assert len(notices) == 1
    assert notices[0].link == "https://lxy.muc.edu.cn/info/1098/3253.htm"
    assert notices[0].date == "2026-09-14 00:00"


def _notice(i: int) -> Notice:
    return Notice(
        id=f"test:{i}",
        title=f"通知 {i}",
        link=f"https://example.com/{i}",
        source="测试",
        source_key="test",
        category="test",
        date="2026-09-01 00:00",
        pub_date="Tue, 01 Sep 2026 00:00:00 +0800",
        published_at=datetime(2026, 9, 1, tzinfo=CHINA_TZ),
    )


async def test_write_rss_truncates_to_max_items(tmp_path):
    service = _service(tmp_path, rss_max_items=2)
    await service.write_rss([_notice(i) for i in range(4)])
    rss_path = Path(service.rss_file_path)
    root = ET.parse(rss_path).getroot()
    assert len(root.findall("./channel/item")) == 2
