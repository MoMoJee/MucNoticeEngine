"""AOP 智能搜索（远程全文检索）。

VSB9（博达）站点自带一套免登录 JSON 搜索接口：
    POST {host}/aop_component/webber/search/search/search/queryPage
请求头只需 ``Authorization: tourist`` 与 ``owner: <站点ID>``；同一主机可查询任意 owner。
本模块只做「远端检索 → 规范化命中」，不写库、不参与轮询与推送。

调研结论（2026-09-19）见 docs/reference/aop-search.md。
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from .fetcher import CHINA_TZ, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

# 任意 VSB9 站点主机都能查询全部 owner；固定用主站，避免依赖院系域名。
SEARCH_HOST = "https://www.muc.edu.cn"
SEARCH_PATH = "/aop_component/webber/search/search/search/queryPage"
PAGE_SIZE = 100
DEFAULT_SCAN_LIMIT = 200
PAGE_DELAY = 0.2

MATCH_OPERATORS = {"all": 1, "any": 0}
SCOPE_VALUES = {"title": 1, "content": 2, "all": 3}
ORDER_VALUES = {"date": "date", "score": "score"}

_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AopSite:
    """一个可检索站点的 owner 与展示信息。"""

    key: str
    name: str
    host: str
    owner: str

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "name": self.name,
            "host": self.host,
            "owner": self.owner,
        }


# owner 提取方法：站点首页 HTML 中的 _jsq_(...) / _showDynClickBatch(...) 末位参数。
AOP_SITES: list[AopSite] = [
    AopSite("www", "中央民族大学（主站）", "www.muc.edu.cn", "1775585708"),
    AopSite("news", "民大新闻", "news.muc.edu.cn", "1775596343"),
    AopSite("grs", "研究生院", "grs.muc.edu.cn", "1499287447"),
    AopSite("rsc", "人事处", "rsc.muc.edu.cn", "1499289493"),
    AopSite("cwc", "财务处", "cwc.muc.edu.cn", "1698027629"),
    AopSite("xiaoyou", "校友网", "xiaoyou.muc.edu.cn", "1499288180"),
    AopSite("msy", "民族学与社会学学院", "msy.muc.edu.cn", "1834816456"),
    AopSite("scemll", "中国民族语言文字应用研究院", "scemll.muc.edu.cn", "1607202447"),
    AopSite("sla", "文学院", "sla.muc.edu.cn", "1632946457"),
    AopSite("history", "历史文化学院", "history.muc.edu.cn", "1499283708"),
    AopSite("phil", "哲学与宗教学学院", "phil.muc.edu.cn", "1694118460"),
    AopSite("xinchuan", "新闻与传播学院", "xinchuan.muc.edu.cn", "1577114110"),
    AopSite("sfs", "外国语学院", "sfs.muc.edu.cn", "1499286850"),
    AopSite("marxism", "马克思主义学院", "marxism.muc.edu.cn", "2077420629"),
    AopSite("eco", "经济学院", "eco.muc.edu.cn", "1499285060"),
    AopSite("ms", "管理学院", "ms.muc.edu.cn", "2012564501"),
    AopSite("law", "法学院", "law.muc.edu.cn", "1779811220"),
    AopSite("cles", "生命与环境科学学院", "cles.muc.edu.cn", "1499286151"),
    AopSite("yxy", "药学院", "yxy.muc.edu.cn", "2110912796"),
    AopSite("lxy", "理学院", "lxy.muc.edu.cn", "1686112499"),
    AopSite("xingong", "信息工程学院", "xingong.muc.edu.cn", "1499287359"),
    AopSite("yyxy", "音乐学院", "yyxy.muc.edu.cn", "2008922769"),
    AopSite("wd", "舞蹈学院", "wd.muc.edu.cn", "1739305935"),
    AopSite("art", "美术学院", "art.muc.edu.cn", "1681929250"),
    AopSite("sport", "体育学院", "sport.muc.edu.cn", "1499288004"),
    AopSite("edu", "教育学院", "edu.muc.edu.cn", "1499283932"),
    AopSite("cie", "国际教育学院", "cie.muc.edu.cn", "1499285259"),
    AopSite("muchnic", "海南国际学院", "muchnic.muc.edu.cn", "1972009796"),
    AopSite("sce", "继续教育学院", "sce.muc.edu.cn", "1815067731"),
    AopSite("myzx", "中国少数民族研究中心", "myzx.muc.edu.cn", "1499284099"),
    AopSite("gjaqyjy", "国家安全研究院", "gjaqyjy.muc.edu.cn", "1824114434"),
    AopSite("vbep", "中国兴边富民战略研究院", "vbep.muc.edu.cn", "1636520272"),
    AopSite("mmsi", "质谱成像与系统生物学研究中心", "mmsi.muc.edu.cn", "1790691648"),
    AopSite("nmlr", "国家语言资源监测与研究民族语言中心", "nmlr.muc.edu.cn", "1507633105"),
]

SITES_BY_KEY: dict[str, AopSite] = {site.key: site for site in AOP_SITES}
SITES_BY_OWNER: dict[str, AopSite] = {site.owner: site for site in AOP_SITES}


@dataclass(slots=True)
class AopSearchHit:
    """一条远程检索命中（已规范化，字段对齐 Notice 的子集）。"""

    title: str
    link: str
    published_at: datetime
    column: int
    column_name: str
    owner: str
    owner_name: str
    snippet: str = ""
    external_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "link": self.link,
            "published_at": self.published_at.isoformat(),
            "column": self.column,
            "column_name": self.column_name,
            "owner": self.owner,
            "owner_name": self.owner_name,
            "snippet": self.snippet,
            "external_id": self.external_id,
        }


@dataclass(slots=True)
class AopSearchResult:
    """一次检索的完整结果；error 非空表示远端调用失败（hits 可能为空）。"""

    site: AopSite
    hits: list[AopSearchHit] = field(default_factory=list)
    remote_total: int = 0
    scanned: int = 0
    truncated: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site.to_dict(),
            "remote_total": self.remote_total,
            "scanned": self.scanned,
            "truncated": self.truncated,
            "count": len(self.hits),
            "hits": [hit.to_dict() for hit in self.hits],
            "error": self.error,
        }


def resolve_site(query: str) -> AopSite | None:
    """按 key / owner / host 精确匹配，再按名称模糊匹配（不唯一返回 None）。"""
    text = (query or "").strip()
    if not text:
        return None
    if text in SITES_BY_KEY:
        return SITES_BY_KEY[text]
    if text in SITES_BY_OWNER:
        return SITES_BY_OWNER[text]
    lowered = text.casefold()
    host_hits = [
        site
        for site in AOP_SITES
        if site.host.casefold() == lowered or site.base_url.casefold() == lowered
    ]
    if len(host_hits) == 1:
        return host_hits[0]
    name_hits = [site for site in AOP_SITES if lowered in site.name.casefold()]
    if len(name_hits) == 1:
        return name_hits[0]
    return None


def build_query(
    site: AopSite,
    keyword: str,
    *,
    match: str = "any",
    scope: str = "all",
    order: str = "date",
    since: str = "",
    until: str = "",
    page: int = 0,
    size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """构造 queryPage 请求体；非法枚举值抛 ValueError。"""
    if match not in MATCH_OPERATORS:
        raise ValueError("match 只能是 all 或 any")
    if scope not in SCOPE_VALUES:
        raise ValueError("scope 只能是 title、content 或 all")
    if order not in ORDER_VALUES:
        raise ValueError("order 只能是 date 或 score")
    normalized = " ".join(keyword.split())
    if not normalized:
        raise ValueError("keyword 不能为空")
    return {
        "aliasName": "article",
        "keyWord": normalized,
        "lastkeyWord": normalized,
        "searchKeyWord": False,
        "orderType": ORDER_VALUES[order],
        "searchType": "text",
        "searchScope": SCOPE_VALUES[scope],
        "searchOperator": MATCH_OPERATORS[match],
        "searchDateType": "custom" if (since or until) else "",
        "searchDateName": "",
        "beginDate": since,
        "endDate": until,
        "showId": "",
        "auditing": ["1"],
        "owner": site.owner,
        "token": "tourist",
        "urlPrefix": "/aop_component/",
        "page": {
            "current": max(0, page),
            "size": max(1, size),
            "pageSizes": [size],
            "total": 0,
            "totalPage": 0,
            "indexs": [],
        },
        "advance": False,
        "advanceKeyWord": "",
        "lang": "i18n_zh_CN",
    }


class AopSearchClient:
    """远程检索客户端。不持连接：每次 search 临时建 client（可用参数注入便于测试）。"""

    def __init__(
        self,
        host: str = SEARCH_HOST,
        *,
        timeout: float = 20.0,
        page_delay: float = PAGE_DELAY,
    ):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.page_delay = page_delay

    async def search(
        self,
        site: AopSite | str,
        keyword: str,
        *,
        match: str = "any",
        exclude: str | None = None,
        scope: str = "all",
        order: str = "date",
        since: str | datetime | date | None = None,
        until: str | datetime | date | None = None,
        limit: int = 20,
        scan_limit: int = DEFAULT_SCAN_LIMIT,
        client: httpx.AsyncClient | None = None,
    ) -> AopSearchResult:
        """检索一个站点；网络/解析失败返回带 error 的结果，不向上抛异常。"""
        if isinstance(site, str):
            resolved = resolve_site(site)
            if resolved is None:
                raise ValueError(f"未知站点：{site}")
            site = resolved
        assert isinstance(site, AopSite)

        since_text = _coerce_date(since, "since")
        until_text = _coerce_date(until, "until")
        limit = max(1, int(limit))
        scan_limit = max(limit, int(scan_limit))
        exclude_terms = [t for t in (exclude or "").split() if t]

        result = AopSearchResult(site=site)
        owned_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=DEFAULT_HEADERS
            )
        seen: set[str] = set()
        page = 0
        try:
            while len(result.hits) < limit and result.scanned < scan_limit:
                payload = build_query(
                    site,
                    keyword,
                    match=match,
                    scope=scope,
                    order=order,
                    since=since_text,
                    until=until_text,
                    page=page,
                )
                response = await client.post(
                    f"{self.host}{SEARCH_PATH}",
                    params={"r": f"{page}-{len(result.hits)}"},
                    json=payload,
                    headers={"Authorization": "tourist", "owner": site.owner},
                )
                response.raise_for_status()
                page_info = ((response.json().get("data") or {}).get("page")) or {}
                result.remote_total = _as_int(page_info.get("total"))
                records = page_info.get("records") or []
                if not records:
                    break

                for record in records:
                    if result.scanned >= scan_limit or len(result.hits) >= limit:
                        break
                    result.scanned += 1
                    hit = self._parse_hit(site, record)
                    if hit is None or hit.link in seen:
                        continue
                    seen.add(hit.link)
                    if exclude_terms and _is_excluded(hit, exclude_terms):
                        continue
                    result.hits.append(hit)

                page += 1
                if len(records) < PAGE_SIZE:
                    break
                if len(result.hits) < limit and result.scanned < scan_limit:
                    await asyncio.sleep(self.page_delay)
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            logger.warning("[AOP] 检索失败 site=%s q=%s: %s", site.key, keyword, exc)
        finally:
            if owned_client:
                await client.aclose()

        result.truncated = result.remote_total > result.scanned
        return result

    def _parse_hit(self, site: AopSite, record: dict) -> AopSearchHit | None:
        if not isinstance(record, dict):
            return None
        title = _clean_text(record.get("collapseTitle") or record.get("title"))
        link = _normalize_url(record.get("url"), site)
        if not title or not link:
            return None
        column = _as_int(record.get("column"))
        record_id = str(record.get("id") or "").strip()
        external_id = (
            f"{site.owner}:{column}:{record_id}"
            if record_id
            else link.strip("/").split("/")[-1].split("?")[0]
        )
        return AopSearchHit(
            title=title,
            link=link,
            published_at=_parse_create_date(record.get("createDate")),
            column=column,
            column_name=_clean_text(record.get("columnName"))[:80],
            owner=str(record.get("owner") or site.owner),
            owner_name=_clean_text(record.get("ownerName")) or site.name,
            snippet=_truncate(_clean_text(record.get("intro") or record.get("content"))),
            external_id=external_id,
        )


def _is_excluded(hit: AopSearchHit, terms: list[str]) -> bool:
    haystack = f"{hit.title} {hit.snippet}".casefold()
    return any(term.casefold() in haystack for term in terms)


def _coerce_date(value: str | datetime | date | None, field_name: str) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} 需为 YYYY-MM-DD：{text}") from exc


def _normalize_url(raw: Any, site: AopSite) -> str:
    url = str(raw or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{site.base_url}{url}"
    return url


def _parse_create_date(value: Any) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CHINA_TZ)
        except ValueError:
            continue
    return datetime(2000, 1, 1, tzinfo=CHINA_TZ)


def _clean_text(value: Any) -> str:
    text = html.unescape(_TAG_PATTERN.sub("", str(value or "")))
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _truncate(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else f"{text[:limit]}..."


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
