import json
from datetime import datetime

import httpx
import pytest

from muc_notice_engine.core.aop import (
    AOP_SITES,
    SITES_BY_KEY,
    AopSearchClient,
    build_query,
    resolve_site,
)
from muc_notice_engine.core.fetcher import CHINA_TZ


def test_catalog_and_resolve():
    assert len(AOP_SITES) == 34
    assert len({site.key for site in AOP_SITES}) == 34
    assert len({site.owner for site in AOP_SITES}) == 34
    assert resolve_site("xingong").key == "xingong"
    assert resolve_site("1499287359").key == "xingong"
    assert resolve_site("xingong.muc.edu.cn").key == "xingong"
    assert resolve_site("信息工程学院").key == "xingong"
    assert resolve_site("") is None
    assert resolve_site("不存在的站") is None


def test_build_query_maps_params():
    payload = build_query(
        SITES_BY_KEY["xingong"],
        "推免  公示",
        match="all",
        scope="title",
        order="score",
        since="2026-09-01",
        until="2026-09-30",
        page=1,
    )
    assert payload["keyWord"] == "推免 公示"
    assert payload["searchOperator"] == 1
    assert payload["searchScope"] == 1
    assert payload["orderType"] == "score"
    assert payload["searchDateType"] == "custom"
    assert payload["beginDate"] == "2026-09-01"
    assert payload["endDate"] == "2026-09-30"
    assert payload["page"]["current"] == 1
    assert payload["owner"] == "1499287359"


def test_build_query_defaults_to_any_scope_all():
    payload = build_query(SITES_BY_KEY["lxy"], "推免")
    assert payload["searchOperator"] == 0
    assert payload["searchScope"] == 3
    assert payload["orderType"] == "date"
    assert payload["searchDateType"] == ""


@pytest.mark.parametrize("override", [{"match": "x"}, {"scope": "x"}, {"order": "x"}])
def test_build_query_rejects_bad_enum(override):
    with pytest.raises(ValueError):
        build_query(SITES_BY_KEY["lxy"], "推免", **override)


def test_build_query_rejects_empty_keyword():
    with pytest.raises(ValueError):
        build_query(SITES_BY_KEY["lxy"], "   ")


def _record(**over) -> dict:
    base = {
        "id": 6535,
        "column": 1041,
        "columnName": "通知公告",
        "collapseTitle": "关于推免的通知",
        "title": "关于<span style='color:red'>推免</span>的通知",
        "intro": "推免工作安排",
        "createDate": "2026-09-18 20:51:01",
        "url": "//xingong.muc.edu.cn/info/1041/6535.htm",
        "owner": "1499287359",
        "ownerName": "信息工程学院",
    }
    base.update(over)
    return base


def _service(**kwargs) -> AopSearchClient:
    return AopSearchClient(**{"page_delay": 0, **kwargs})


async def test_search_parses_dedupes_and_excludes():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["Authorization"] == "tourist"
        assert request.headers["owner"] == "1499287359"
        assert body["keyWord"] == "推免"
        records = [
            _record(),
            _record(),
            _record(
                id=6445,
                url="//xingong.muc.edu.cn/info/1041/6445.htm",
                collapseTitle="复试名单",
                title="复试<span>名单</span>",
                intro="名单公示",
            ),
        ]
        return httpx.Response(
            200, json={"data": {"page": {"total": 3, "records": records}}}
        )

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.search("xingong", "推免", exclude="名单", client=client)

    assert result.error == ""
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.title == "关于推免的通知"
    assert hit.link == "https://xingong.muc.edu.cn/info/1041/6535.htm"
    assert hit.published_at == datetime(2026, 9, 18, 20, 51, 1, tzinfo=CHINA_TZ)
    assert hit.column_name == "通知公告"
    assert hit.external_id == "1499287359:1041:6535"
    assert result.remote_total == 3
    assert result.scanned == 3
    assert result.truncated is False


async def test_search_respects_scan_limit_and_truncation():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        page = body["page"]["current"]
        records = [
            _record(id=page * 100 + i, url=f"//xingong.muc.edu.cn/info/1041/{page * 100 + i}.htm")
            for i in range(100)
        ]
        return httpx.Response(
            200, json={"data": {"page": {"total": 250, "records": records}}}
        )

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.search(
            "xingong", "推免", limit=100, scan_limit=100, client=client
        )

    assert result.scanned == 100
    assert len(result.hits) == 100
    assert result.remote_total == 250
    assert result.truncated is True


async def test_search_returns_error_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    service = _service()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.search("xingong", "推免", client=client)

    assert result.error.startswith("HTTPStatusError")
    assert result.hits == []


async def test_search_rejects_bad_date():
    service = _service()
    with pytest.raises(ValueError):
        await service.search("xingong", "推免", since="2026/09/01")
