"""抓取引擎：公开站点 HTML + 门户 API，输出规范化 Notice 并生成 RSS。

移植自 astrbot_plugin_MUC_Notices/rss_service.py，去掉 AstrBot 依赖，
用 Settings 取代原 config dict，用 Notice dataclass 取代 TypedDict。
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..config import Settings
from .auth import (
    AJAX_HEADERS,
    NOTICE_DETAIL_URL,
    NOTICE_DOWNLOAD_URL,
    PORTAL_BASE_URL,
    MucAuthService,
)
from .models import Attachment, Notice, NoticeDetail, SourceConfig
from .sources import PORTAL_TYPES, SOURCES, SOURCES_BY_KEY

logger = logging.getLogger(__name__)

CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
DATE_PATTERN_FULL = re.compile(
    r"(?P<year>\d{4})\s*(?:年|[-/.])\s*(?P<month>\d{1,2})\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
)
DATE_PATTERN_SHORT = re.compile(
    r"(?P<month>\d{1,2})\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
)
# 门户翻页时的礼貌间隔，避免连续请求过快。
PORTAL_PAGE_DELAY = 0.2

# 文章正文里常见的容器（民大各站基本是织梦/CMS 那套）
ARTICLE_SELECTORS = (
    ".v_news_content",
    ".content",
    ".article-content",
    ".TRS_Editor",
    "#vsb_content",
    ".wp_articlecontent",
    "#zoom",
    ".news_content",
    "article",
)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class SessionInvalidError(Exception):
    """门户 comsys 会话已失效，需要重新登录后重试。"""


class MucRssService:
    """通知抓取器。可独立于 HTTP 服务运行：只依赖 httpx / bs4。"""

    def __init__(self, settings: Settings, auth_service: MucAuthService | None = None):
        self.settings = settings
        self._auth_service = auth_service
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    @property
    def rss_file_path(self):
        return self.settings.rss_file_path

    async def fetch_notices(
        self, source_keys: set[str] | None = None
    ) -> list[Notice]:
        timeout_sec = self.settings.request_timeout_seconds
        selected_sources = [
            source
            for source in SOURCES
            if source_keys is None or source["key"] in source_keys
        ]
        if source_keys is not None and not selected_sources:
            logger.info("[RSS] 未找到匹配来源 source_keys=%s", sorted(source_keys))

        public_sources = [
            s for s in selected_sources if not s.get("requires_auth", False)
        ]
        auth_sources = [s for s in selected_sources if s.get("requires_auth", False)]

        auth_client = None
        if auth_sources and self._auth_service:
            auth_client = await self._auth_service.get_authenticated_client()
            if auth_client is None:
                logger.warning(
                    "[RSS] %d 个需认证来源跳过（未配置账号或登录失败）", len(auth_sources)
                )
                auth_sources = []
            else:
                logger.info("[RSS] 认证客户端就绪，抓取 %d 个门户来源", len(auth_sources))

        async def _fetch_all():
            async with httpx.AsyncClient(
                timeout=timeout_sec,
                follow_redirects=True,
                headers=DEFAULT_HEADERS,
            ) as client:

                async def _fetch_limited(source):
                    async with self._semaphore:
                        return await self._fetch_source_notices(client, source)

                pub_results = await asyncio.gather(
                    *(_fetch_limited(source) for source in public_sources),
                    return_exceptions=True,
                )

            async def _fetch_one_auth(client_for_auth, source):
                async with httpx.AsyncClient(
                    timeout=timeout_sec, follow_redirects=True
                ) as ac:
                    if hasattr(client_for_auth, "cookies"):
                        ac.cookies = client_for_auth.cookies
                    return await self._fetch_source_notices(ac, source)

            auth_results = []
            invalid_idx: list[int] = []
            if auth_client and auth_sources:
                for idx, source in enumerate(auth_sources):
                    try:
                        auth_results.append(await _fetch_one_auth(auth_client, source))
                    except SessionInvalidError:
                        auth_results.append([])
                        invalid_idx.append(idx)
                    except Exception as e:  # noqa: BLE001
                        auth_results.append(e)

                if invalid_idx and self._auth_service:
                    logger.info(
                        "[RSS] %d 个门户来源会话失效，重新登录后重试", len(invalid_idx)
                    )
                    self._auth_service.invalidate()
                    fresh_client = await self._auth_service.get_authenticated_client()
                    if fresh_client:
                        for idx in invalid_idx:
                            try:
                                auth_results[idx] = await _fetch_one_auth(
                                    fresh_client, auth_sources[idx]
                                )
                            except Exception as e:  # noqa: BLE001
                                logger.info(
                                    "[RSS] API 来源 %s 重试后仍失败: %s",
                                    auth_sources[idx]["key"],
                                    e,
                                )
                                auth_results[idx] = e
                    else:
                        logger.warning("[RSS] 重新登录失败，门户来源本轮跳过")

            return pub_results + auth_results

        results = await _fetch_all()
        all_selected = public_sources + auth_sources

        notices: list[Notice] = []
        for source, result in zip(all_selected, results, strict=True):
            if isinstance(result, Exception):
                logger.info(
                    "[RSS] 抓取来源失败 %s %s: %s", source["key"], source["url"], result
                )
                continue
            notices.extend(result)

        deduped: dict[str, Notice] = {}
        for item in notices:
            deduped[item.link] = item

        ordered = sorted(
            deduped.values(),
            key=lambda item: (item.published_at, item.source),
            reverse=True,
        )
        return ordered

    async def write_rss(self, notices: list[Notice]) -> None:
        now_str = datetime.now(CHINA_TZ).strftime("%a, %d %b %Y %H:%M:%S +0800")

        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = self.settings.rss_title
        ET.SubElement(channel, "link").text = "https://www.muc.edu.cn/tzgg.htm"
        ET.SubElement(channel, "description").text = "中央民族大学多来源通知聚合"
        ET.SubElement(channel, "lastBuildDate").text = now_str

        for notice in notices[: self.settings.rss_max_items]:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = f"[{notice.source}] {notice.title}"
            ET.SubElement(item, "link").text = notice.link
            ET.SubElement(item, "guid").text = notice.id
            ET.SubElement(item, "pubDate").text = notice.pub_date
            ET.SubElement(item, "description").text = (
                f"来源：{notice.source} | 分类：{notice.category} | 日期：{notice.date}"
            )

        xml_data = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
        path = self.rss_file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, xml_data)
        logger.info(
            "[RSS] RSS 文件已更新 %s items=%d（上限 %d）",
            path,
            min(len(notices), self.settings.rss_max_items),
            self.settings.rss_max_items,
        )

    async def _fetch_source_notices(
        self, client: httpx.AsyncClient | None, source: SourceConfig
    ) -> list[Notice]:
        selector = source.get("selector", "")
        if selector.startswith("api:"):
            return await self._fetch_api_source_notices(client, source)

        if client is None:
            return []

        page_urls = [source["url"], *source.get("extra_urls", [])]
        notices: list[Notice] = []
        seen_links: set[str] = set()

        for page_url in page_urls:
            response = await client.get(
                page_url, headers=self._request_headers(source, page_url)
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            tags = soup.select(source["selector"])
            if not tags:
                logger.info(
                    "[RSS] 选择器未命中 %s %s selector=%s",
                    source["key"],
                    page_url,
                    source["selector"],
                )
                continue

            for tag in tags:
                if not isinstance(tag, Tag):
                    continue

                href = (tag.get("href") or "").strip()
                if not href:
                    continue

                title = source["parser"](tag).strip()
                if not title:
                    continue

                full_url = urljoin(page_url, href)
                if full_url in seen_links:
                    continue

                published_at = self._extract_published_at(tag, source)
                notices.append(
                    Notice(
                        id=self._make_notice_id(source["key"], full_url),
                        title=title,
                        link=full_url,
                        source=source["name"],
                        source_key=source["key"],
                        category=source["category"],
                        date=published_at.strftime("%Y-%m-%d %H:%M"),
                        pub_date=published_at.strftime(
                            "%a, %d %b %Y %H:%M:%S +0800"
                        ),
                        published_at=published_at,
                        external_id=self._make_external_id(full_url),
                    )
                )
                seen_links.add(full_url)

        if not notices:
            logger.info("[RSS] 来源无有效条目 %s urls=%s", source["key"], page_urls)
        return notices

    async def _fetch_api_source_notices(
        self, client: httpx.AsyncClient | None, source: SourceConfig
    ) -> list[Notice]:
        if client is None:
            logger.info("[RSS] API 来源 %s 无认证客户端", source["key"])
            return []

        api_params = source.get("api_params", {})
        type_id = _as_int(api_params.get("type"))
        page_size = _as_int(api_params.get("pageSize")) or 20
        try:
            return await self._fetch_portal_pages(
                client,
                source,
                type_id,
                from_page=1,
                to_page=max(1, self.settings.portal_page_limit),
                page_size=page_size,
            )
        except SessionInvalidError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info("[RSS] API 来源 %s 失败: %s", source["key"], exc)
            return []

    async def fetch_portal_type(
        self,
        type_id: int,
        *,
        from_page: int = 1,
        to_page: int = 1,
        search_value: str | None = None,
    ) -> list[Notice]:
        """手动抓取门户指定 type 的页数区间（历史回填用，不受 portal_page_limit 限制）。"""
        source = SOURCES_BY_KEY.get(PORTAL_TYPES.get(type_id, ""))
        if source is None:
            logger.info("[RSS] 未知门户 type=%s", type_id)
            return []
        if self._auth_service is None:
            logger.warning("[RSS] 手动抓取门户失败：未配置认证服务")
            return []

        page_size = _as_int(source.get("api_params", {}).get("pageSize")) or 20

        async def _attempt() -> list[Notice]:
            client = await self._auth_service.get_authenticated_client()
            if client is None:
                return []
            return await self._fetch_portal_pages(
                client,
                source,
                type_id,
                from_page=from_page,
                to_page=to_page,
                page_size=page_size,
                search_value=search_value,
            )

        try:
            return await _attempt()
        except SessionInvalidError:
            logger.info("[RSS] 手动抓取门户会话失效，重新登录后重试")
            self._auth_service.invalidate()
            try:
                return await _attempt()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RSS] 手动抓取门户重试仍失败: %s", exc)
                return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RSS] 手动抓取门户失败: %s", exc)
            return []

    async def _fetch_portal_pages(
        self,
        client: httpx.AsyncClient,
        source: SourceConfig,
        type_id: int,
        *,
        from_page: int,
        to_page: int,
        page_size: int,
        search_value: str | None = None,
    ) -> list[Notice]:
        notices: list[Notice] = []
        page = max(1, from_page)
        last_page = max(page, to_page)
        while page <= last_page:
            if page > max(1, from_page):
                await asyncio.sleep(PORTAL_PAGE_DELAY)
            data: dict[str, Any] = {
                "currentPage": page,
                "pageSize": page_size,
                "type": type_id,
            }
            if search_value:
                data["searchValue"] = search_value
            response = await client.post(
                source["url"], data=data, headers=AJAX_HEADERS
            )
            response.raise_for_status()
            if "error_comsys_session_invalid" in response.text[:200]:
                raise SessionInvalidError(source["key"])
            payload = response.json()
            datas = payload.get("datas") or {}
            tables = datas.get("tables") or []
            if not tables:
                break
            for item in tables:
                parsed = self._parse_portal_item(source, item, type_id)
                if parsed is not None:
                    notices.append(parsed)

            total_pages = _as_int((datas.get("page") or {}).get("totalCounts"))
            if total_pages and page >= total_pages:
                break
            page += 1
        return notices

    def _parse_portal_item(
        self, source: SourceConfig, item: dict, type_id: int
    ) -> Notice | None:
        title = str(item.get("notice_title", "")).strip()
        if not title:
            return None
        notice_id = str(item.get("notice_id", ""))
        link = (
            "https://my.muc.edu.cn/page/11#/print?"
            f"type={type_id}&notice_id={notice_id}&show_type=1"
        )
        published_at = datetime(2000, 1, 1, tzinfo=CHINA_TZ)
        time_val = item.get("notice_release_time")
        if time_val:
            published_at = self._parse_api_time(time_val, published_at)

        raw_content = item.get("notice_content", "")
        summary_text = ""
        content_text = ""
        if raw_content:
            try:
                soup = BeautifulSoup(raw_content, "html.parser")
                plain = soup.get_text(separator=" ", strip=True)
                plain = re.sub(r"\s+", " ", plain).strip()
                summary_text = plain[:80] + ("..." if len(plain) > 80 else "")
                content_text = plain[:2000]
            except Exception:  # noqa: BLE001
                pass

        return Notice(
            id=self._make_notice_id(source["key"], notice_id),
            title=title,
            link=link,
            source=source["name"],
            source_key=source["key"],
            category=source["category"],
            date=published_at.strftime("%Y-%m-%d %H:%M"),
            pub_date=published_at.strftime("%a, %d %b %Y %H:%M:%S +0800"),
            published_at=published_at,
            external_id=notice_id,
            summary=summary_text,
            content=content_text,
        )

    # ---------------- 正文 / 附件（详情） ----------------

    async def fetch_detail(self, notice: Notice) -> NoticeDetail | None:
        """抓取一条通知的完整正文与附件（门户走 getNotice，公开源抓文章页）。"""
        source = SOURCES_BY_KEY.get(notice.source_key)
        if source is not None and source.get("requires_auth", False):
            return await self._fetch_portal_detail(notice)
        return await self._fetch_public_detail(notice)

    async def _fetch_portal_detail(self, notice: Notice) -> NoticeDetail | None:
        if self._auth_service is None or not notice.external_id:
            return None

        async def _attempt() -> NoticeDetail | None:
            client = await self._auth_service.get_authenticated_client()
            if client is None:
                return None
            resp = await client.post(
                NOTICE_DETAIL_URL,
                data={"notice_id": notice.external_id},
                headers=AJAX_HEADERS,
            )
            if "error_comsys_session_invalid" in resp.text[:200]:
                raise SessionInvalidError(notice.source_key)
            resp.raise_for_status()
            payload = resp.json()
            info = (payload.get("datas") or {}).get("notice_info") or {}
            content_html = str(info.get("notice_content") or "")
            return NoticeDetail(
                notice=notice,
                content_html=content_html,
                attachments=self._parse_portal_attachments(
                    notice, info, content_html
                ),
                plain_text=_html_to_text(content_html),
            )

        try:
            return await _attempt()
        except SessionInvalidError:
            logger.info("[RSS] 获取正文时会话失效 %s，重登后重试", notice.id)
            self._auth_service.invalidate()
            try:
                return await _attempt()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RSS] 重试获取正文仍失败 %s: %s", notice.id, exc)
                return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RSS] 获取门户正文失败 %s: %s", notice.id, exc)
            return None

    def _parse_portal_attachments(
        self, notice: Notice, info: dict, content_html: str
    ) -> list[Attachment]:
        attachments: list[Attachment] = []
        for idx, raw in enumerate(info.get("notice_annext") or []):
            if not isinstance(raw, dict):
                continue
            annex_id = str(raw.get("notice_annex_id") or "").strip()
            name = str(raw.get("notice_annex_name") or "").strip() or f"attachment-{idx}"
            attachments.append(
                Attachment(
                    annex_id=annex_id,
                    name=name,
                    url=(
                        f"{NOTICE_DOWNLOAD_URL}?id={quote(annex_id)}"
                        f"&notice_id={quote(notice.external_id)}"
                    ),
                    suffix=str(raw.get("suffix") or "").strip(),
                    kind="file",
                )
            )

        seen: set[str] = set()
        soup = BeautifulSoup(content_html, "html.parser")
        for idx, img in enumerate(soup.find_all("img")):
            src = str(img.get("src") or "").strip()
            if not src:
                continue
            url = urljoin(PORTAL_BASE_URL, src)
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            name = Path(urlparse(url).path).name or f"image-{idx}.png"
            attachments.append(
                Attachment(annex_id="", name=name, url=url, suffix="", kind="image")
            )
        return attachments

    async def _fetch_public_detail(self, notice: Notice) -> NoticeDetail | None:
        if not (notice.link or "").startswith("http"):
            return None
        timeout = min(self.settings.request_timeout_seconds, 15)
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=timeout, headers=DEFAULT_HEADERS
            ) as client:
                async with self._semaphore:
                    resp = await client.get(notice.link)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[RSS] 抓正文失败 %s: %s", notice.link, exc)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        node = None
        for sel in ARTICLE_SELECTORS:
            node = soup.select_one(sel)
            if node:
                break
        node = node or soup.body or soup
        for bad in node.select("script, style, nav, header, footer"):
            bad.decompose()
        content_html = "".join(str(child) for child in node.children).strip()
        plain = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        return NoticeDetail(
            notice=notice,
            content_html=content_html,
            attachments=[],
            plain_text=plain,
        )

    def _parse_api_time(self, time_val, default: datetime) -> datetime:
        try:
            if isinstance(time_val, (int, float)) or (
                isinstance(time_val, str) and time_val.isdigit()
            ):
                ts = float(time_val)
                if ts > 1e11:
                    ts /= 1000.0
                return datetime.fromtimestamp(ts, tz=CHINA_TZ)
            if isinstance(time_val, str):
                clean_time = time_val.split(".")[0].strip()
                if len(clean_time) >= 19 and "-" in clean_time:
                    return datetime.strptime(
                        clean_time[:19], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=CHINA_TZ)
                if len(clean_time) >= 16 and "-" in clean_time:
                    return datetime.strptime(
                        clean_time[:16], "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=CHINA_TZ)
                if len(clean_time) >= 10 and "-" in clean_time:
                    return datetime.strptime(
                        clean_time[:10], "%Y-%m-%d"
                    ).replace(tzinfo=CHINA_TZ)
                parsed = self._parse_date(time_val)
                if parsed:
                    return parsed
        except Exception:  # noqa: BLE001
            pass
        return default

    def _extract_published_at(self, tag: Tag, source: SourceConfig) -> datetime:
        candidates = [
            tag.get("title", ""),
            tag.get_text(" ", strip=True),
            *self._iter_ancestor_texts(tag, depth=5),
            self._collect_sibling_text(tag),
        ]
        for text in candidates:
            if not text:
                continue
            extracted = self._parse_date(str(text))
            if extracted is not None:
                return extracted
        return datetime(2000, 1, 1, tzinfo=CHINA_TZ)

    def _iter_ancestor_texts(self, tag: Tag, depth: int) -> Iterable[str]:
        current = tag.parent
        steps = 0
        while isinstance(current, Tag) and steps < depth:
            text = current.get_text(" ", strip=True)
            if text:
                yield text
            current = current.parent
            steps += 1

    def _collect_sibling_text(self, tag: Tag) -> str:
        texts: list[str] = []
        for sibling in list(tag.previous_siblings)[:2]:
            text = self._node_text(sibling)
            if text:
                texts.append(text)
        for sibling in list(tag.next_siblings)[:2]:
            text = self._node_text(sibling)
            if text:
                texts.append(text)
        return " ".join(texts)

    def _node_text(self, node: object) -> str:
        if isinstance(node, Tag):
            return node.get_text(" ", strip=True)
        return str(node).strip()

    def _parse_date(self, text: str) -> datetime | None:
        if not text:
            return None

        match = DATE_PATTERN_FULL.search(text)
        if match:
            try:
                return datetime(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                    tzinfo=CHINA_TZ,
                )
            except ValueError:
                pass

        match = DATE_PATTERN_SHORT.search(text)
        if match:
            try:
                now = datetime.now(CHINA_TZ)
                month = int(match.group("month"))
                day = int(match.group("day"))
                year = now.year
                if month > now.month:
                    year -= 1
                return datetime(year, month, day, tzinfo=CHINA_TZ)
            except ValueError:
                pass

        return None

    def _make_notice_id(self, source_key: str, link: str) -> str:
        digest = sha1(f"{source_key}|{link}".encode()).hexdigest()
        return f"{source_key}:{digest}"

    def _make_external_id(self, link: str) -> str:
        """公开源的文章标识：取 URL 路径 slug；过短则退回链接哈希。"""
        path = urlparse(link).path.strip("/")
        slug = re.sub(r"[^0-9A-Za-z._-]+", "-", path).strip("-.")
        if slug:
            return slug[:120].rstrip("-.")
        return sha1(link.encode()).hexdigest()[:16]

    def _request_headers(
        self, source: SourceConfig, request_url: str | None = None
    ) -> dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = request_url or source["url"]
        return headers

def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
