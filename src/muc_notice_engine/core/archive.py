"""正文 / 附件归档：文件系统落盘 + 后台队列 + LRU 淘汰。

职责边界：
- `fetcher` 负责「发现」正文与附件（网络抓取，不碰文件系统）；
- 本模块负责「取回并落盘」并维护 `NoticeStore.assets` 表；
- `engine` 只依赖 `Archiver` 协议（`enqueue`），不关心下载细节。

目录布局（`archive_dir` 下）：
    <source_key>/<external_id>/
    ├── content.html
    ├── content.txt
    ├── meta.json
    └── files/            # 附件与内联图片
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from .auth import MucAuthService
from .fetcher import CHINA_TZ, DEFAULT_HEADERS, HostRateLimiter, MucRssService
from .models import Attachment, Notice, NoticeDetail
from .storage import NoticeStore

logger = logging.getLogger(__name__)

EVICT_MIN_INTERVAL_SECONDS = 60.0
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_UNSAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def safe_filename(name: str, fallback: str = "file") -> str:
    """文件/目录名安全化：去掉路径、控制字符与危险符号，限制长度。"""
    raw = Path(str(name or "")).name
    cleaned = _UNSAFE_NAME.sub("_", raw).strip("._")
    cleaned = cleaned[:120].strip("._")
    if not cleaned:
        cleaned = fallback
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def _html_to_text_fallback(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


class ArchiveStore:
    """一条通知的正文与附件落盘，以及超限淘汰。"""

    def __init__(
        self,
        settings: Settings,
        store: NoticeStore,
        auth_service: MucAuthService | None = None,
    ):
        self.settings = settings
        self.store = store
        self.auth_service = auth_service
        self.root = Path(settings.archive_dir)
        self._last_evict_at = 0.0
        self._host_limiter = HostRateLimiter()

    def notice_dir(self, notice: Notice) -> Path:
        source = safe_filename(notice.source_key, "source")
        external = safe_filename(notice.external_id or notice.id, "notice")
        return self.root / source / external

    # ---------------- 落盘 ----------------

    async def archive(self, detail: NoticeDetail) -> list[dict]:
        """落盘正文 + 附件 + meta.json，并原子替换 assets 记录。"""
        notice = detail.notice
        target = self.notice_dir(notice)
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)

        records: list[dict] = []
        html = detail.content_html or ""
        if html.strip():
            records.append(await self._write_text(target / "content.html", html, "content"))

        text = detail.plain_text or _html_to_text_fallback(html)
        if text.strip():
            records.append(await self._write_text(target / "content.txt", text, "content"))

        attachments = self._limit_attachments(detail.attachments)
        if attachments:
            files_dir = target / "files"
            await asyncio.to_thread(files_dir.mkdir, parents=True, exist_ok=True)
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.settings.request_timeout_seconds,
                headers=DEFAULT_HEADERS,
            ) as client:
                for index, attachment in enumerate(attachments, start=1):
                    record = await self._download(
                        client, attachment, index, files_dir, notice
                    )
                    if record is not None:
                        records.append(record)

        meta = {
            "notice": {
                "id": notice.id,
                "external_id": notice.external_id,
                "title": notice.title,
                "link": notice.link,
                "source_key": notice.source_key,
                "category": notice.category,
                "published_at": notice.published_at.isoformat(),
            },
            "files": [
                {
                    "kind": r["kind"],
                    "filename": r["filename"],
                    "remote_name": r.get("remote_name", ""),
                    "size": r["size"],
                    "sha1": r["sha1"],
                }
                for r in records
            ],
            "archived_at": datetime.now(CHINA_TZ).isoformat(),
        }
        records.append(
            await self._write_text(
                target / "meta.json",
                json.dumps(meta, ensure_ascii=False, indent=2),
                "content",
            )
        )

        await self.store.replace_assets(notice.id, records)
        await self.evict_to_limit()
        return records

    def _limit_attachments(self, attachments: list[Attachment]) -> list[Attachment]:
        """附件与图片分别受各自上限限制，同时保持原始顺序。"""
        max_files = max(0, self.settings.archive_max_per_notice)
        max_images = max(0, self.settings.archive_max_images_per_notice)
        selected: list[Attachment] = []
        files = images = 0
        for attachment in attachments:
            if attachment.kind == "image":
                if images >= max_images:
                    continue
                images += 1
            else:
                if files >= max_files:
                    continue
                files += 1
            selected.append(attachment)
        return selected

    async def _write_text(self, path: Path, text: str, kind: str) -> dict:
        data = text.encode("utf-8", errors="replace")
        return await asyncio.to_thread(self._write_bytes_sync, path, data, kind)

    def _write_bytes_sync(self, path: Path, data: bytes, kind: str) -> dict:
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return {
            "kind": kind,
            "filename": path.name,
            "local_path": path.relative_to(self.root).as_posix(),
            "size": len(data),
            "sha1": hashlib.sha1(data).hexdigest(),
        }

    async def _download(
        self,
        client: httpx.AsyncClient,
        attachment: Attachment,
        index: int,
        files_dir: Path,
        notice: Notice | None = None,
    ) -> dict | None:
        request_client = client
        if self.auth_service is not None and "my.muc.edu.cn" in attachment.url:
            auth_client = await self.auth_service.get_authenticated_client()
            if auth_client is None:
                return None
            request_client = auth_client

        size_limit = max(0, self.settings.archive_max_file_mb) * 1024 * 1024
        attempts = max(0, self.settings.archive_external_retries) + 1
        source_key = notice.source_key if notice is not None else ""
        buffer: bytearray | None = None
        for attempt in range(1, attempts + 1):
            buffer = None
            retry = False
            try:
                async with self._host_limiter.slot(
                    attachment.url, self.settings.archive_host_interval_ms
                ):
                    async with request_client.stream(
                        "GET", attachment.url
                    ) as response:
                        status = response.status_code
                        if status != 200:
                            logger.info(
                                "[ARCHIVE] 下载失败 source=%s stage=%s status=%s url=%s",
                                source_key,
                                attachment.kind,
                                status,
                                attachment.url,
                            )
                            retry = status >= 500 and attempt < attempts
                        else:
                            disposition = response.headers.get(
                                "content-disposition", ""
                            ).lower()
                            content_type = response.headers.get(
                                "content-type", ""
                            ).lower()
                            if attachment.kind == "file":
                                is_portal = "my.muc.edu.cn" in attachment.url
                                non_file_type = content_type.startswith(
                                    (
                                        "text/html",
                                        "text/plain",
                                        "application/xhtml",
                                        "application/json",
                                        "application/xml",
                                    )
                                )
                                if is_portal:
                                    rejected = "filename" not in disposition
                                else:
                                    rejected = non_file_type
                                if rejected:
                                    logger.info(
                                        "[ARCHIVE] 非附件响应（可能未登录或被重定向）"
                                        " source=%s url=%s content-type=%s",
                                        source_key,
                                        attachment.url,
                                        content_type,
                                    )
                                    return None
                            elif not content_type.startswith("image/"):
                                logger.info(
                                    "[ARCHIVE] 非图片响应 source=%s url=%s"
                                    " content-type=%s",
                                    source_key,
                                    attachment.url,
                                    content_type,
                                )
                                return None

                            buffer = bytearray()
                            async for chunk in response.aiter_bytes():
                                buffer.extend(chunk)
                                if size_limit and len(buffer) > size_limit:
                                    logger.warning(
                                        "[ARCHIVE] 超过单文件上限 %s MB，跳过 %s",
                                        self.settings.archive_max_file_mb,
                                        attachment.name,
                                    )
                                    return None
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "[ARCHIVE] 下载异常 source=%s stage=%s url=%s error=%s",
                    source_key,
                    attachment.kind,
                    attachment.url,
                    exc,
                )
                buffer = None
                retry = attempt < attempts

            if buffer is not None:
                break
            if not retry:
                return None
            await asyncio.sleep(0.5 * attempt)

        if buffer is None:
            return None

        base = safe_filename(attachment.name, f"file-{index}")
        filename = f"{index:02d}-{base}"
        record = await asyncio.to_thread(
            self._write_bytes_sync, files_dir / filename, bytes(buffer), "attachment"
        )
        record["remote_name"] = attachment.name
        return record

    # ---------------- 超限淘汰 ----------------

    async def evict_to_limit(self, force: bool = False) -> int:
        """按 last_access_at 升序删除，直到总量不超过 archive_total_limit_gb。"""
        now = time.monotonic()
        if not force and now - self._last_evict_at < EVICT_MIN_INTERVAL_SECONDS:
            return 0
        self._last_evict_at = now

        limit = max(0, self.settings.archive_total_limit_gb) * 1024**3
        if limit <= 0:
            return 0
        total = await self.store.total_asset_size()
        if total <= limit:
            return 0

        removed = 0
        for row in await self.store.list_assets_oldest(limit=5000):
            if total <= limit:
                break
            path = self.resolve_local(row.get("local_path", ""))
            if path is not None:
                try:
                    if await asyncio.to_thread(path.exists):
                        await asyncio.to_thread(path.unlink)
                except OSError as exc:
                    logger.warning("[ARCHIVE] 删除文件失败 %s: %s", path, exc)
            await self.store.delete_asset(int(row["id"]))
            total -= int(row.get("size") or 0)
            removed += 1

        if removed:
            logger.info(
                "[ARCHIVE] LRU 淘汰 %d 个文件，剩余 %.1f MB",
                removed,
                total / 1048576,
            )
        return removed

    def resolve_local(self, local_path: str) -> Path | None:
        """把 assets.local_path 解析为绝对路径；越界返回 None（防路径穿越）。"""
        if not local_path:
            return None
        root = self.root.resolve()
        candidate = (root / local_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            logger.warning("[ARCHIVE] 非法落盘路径 %s", local_path)
            return None
        return candidate


class ArchiveQueue:
    """后台归档队列：engine 以此作为 `Archiver`。"""

    def __init__(
        self,
        settings: Settings,
        store: NoticeStore,
        fetcher: MucRssService,
        archive_store: ArchiveStore,
    ):
        self.settings = settings
        self.store = store
        self.fetcher = fetcher
        self.archive_store = archive_store
        self._queue: asyncio.Queue[tuple[Notice, bool]] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._processed = 0
        self._skipped = 0
        self._failed = 0

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        return {
            "pending": self.pending,
            "processed": self._processed,
            "skipped": self._skipped,
            "failed": self._failed,
        }

    async def start(self) -> None:
        workers = max(1, self.settings.archive_workers)
        self._tasks = [
            asyncio.create_task(self._worker(i), name=f"archive-worker-{i}")
            for i in range(workers)
        ]
        logger.info("[ARCHIVE] 启动 %d 个归档 worker", workers)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def enqueue(self, notice: Notice, *, force: bool = False) -> None:
        self._queue.put_nowait((notice, force))

    async def enqueue_many(self, notices: list[Notice], *, force: bool = False) -> None:
        for notice in notices:
            self._queue.put_nowait((notice, force))

    async def join(self) -> None:
        await self._queue.join()

    async def _worker(self, index: int) -> None:
        while True:
            notice, force = await self._queue.get()
            try:
                archived = await self._process(notice, force)
                if archived:
                    self._processed += 1
                else:
                    self._skipped += 1
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                self._failed += 1
                logger.exception("[ARCHIVE] 归档失败 %s", notice.id)
            finally:
                self._queue.task_done()

    async def _process(self, notice: Notice, force: bool) -> bool:
        detail = await self.fetcher.fetch_detail(notice)
        if detail is None:
            logger.info("[ARCHIVE] 详情抓取失败，无可归档内容 %s", notice.id)
            return False
        has_content = bool((detail.content_html or "").strip())
        if not has_content and not detail.attachments:
            logger.info("[ARCHIVE] 无正文可归档 %s", notice.id)
            return False
        if has_content and not detail.attachments:
            logger.info("[ARCHIVE] 已归档正文但无图片/附件 %s", notice.id)
        records = await self.archive_store.archive(detail)
        if not (notice.content or "").strip() and detail.plain_text:
            await self.store.fill_content_preview(notice.id, detail.plain_text)
        logger.info(
            "[ARCHIVE] %s 落盘 %d 个文件%s",
            notice.id,
            len(records),
            "（手动）" if force else "",
        )
        return True
