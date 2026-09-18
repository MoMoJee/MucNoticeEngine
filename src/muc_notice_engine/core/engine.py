"""核心调度：拉取 -> 去重 -> 存储 -> 通知发布者。

这是整个系统的「单一事实源」。它不认识 FastAPI / webhook，
只通过下面这个极小的协议把新通知交给外部：
    async def publish(self, notices: list[Notice]) -> None

任何传输方式（webhook、消息队列、日志……）实现该协议即可接入。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from ..config import Settings
from .fetcher import CHINA_TZ, MucRssService
from .models import Notice
from .storage import NoticeStore

logger = logging.getLogger(__name__)


@runtime_checkable
class Publisher(Protocol):
    """新通知的消费者。实现方不应回抛异常给引擎。"""

    async def publish(self, notices: list[Notice]) -> None: ...


@runtime_checkable
class Archiver(Protocol):
    """正文/附件归档的消费者。实现方不应回抛异常给引擎。"""

    async def enqueue(self, notice: Notice, *, force: bool = False) -> None: ...


class NoticeEngine:
    def __init__(
        self,
        settings: Settings,
        fetcher: MucRssService,
        store: NoticeStore,
        publishers: list[Publisher] | None = None,
        archiver: Archiver | None = None,
    ):
        self.settings = settings
        self.fetcher = fetcher
        self.store = store
        self.publishers: list[Publisher] = list(publishers or [])
        self.archiver = archiver

        self._stop = asyncio.Event()
        self._poll_lock = asyncio.Lock()
        self._last_poll_at: datetime | None = None
        self._last_new_count = 0

    # ---------------- 状态 ----------------

    @property
    def last_poll_at(self) -> datetime | None:
        return self._last_poll_at

    @property
    def last_new_count(self) -> int:
        return self._last_new_count

    @property
    def archive_pending(self) -> int:
        return int(getattr(self.archiver, "pending", 0) or 0)

    def add_publisher(self, publisher: Publisher) -> None:
        self.publishers.append(publisher)

    # ---------------- 单次轮询 ----------------

    async def poll_once(
        self,
        source_keys: set[str] | None = None,
        *,
        backfill: bool | None = None,
    ) -> list[Notice]:
        """抓取一轮，入库，返回「新且值得推送」的通知（已发布给 Publisher）。

        `backfill=None`：首轮自动视为回填（首轮标记持久化在 meta 表）。
        """
        async with self._poll_lock:
            if backfill is None:
                backfill = await self._is_initial_poll()
            notices = await self.fetcher.fetch_notices(source_keys)
            new_notices, fresh = await self._ingest(
                notices, backfill=backfill, write_rss=True
            )
            if notices and backfill:
                await self.store.set_meta(
                    "initial_poll_done", datetime.now(CHINA_TZ).isoformat()
                )

            self._last_poll_at = datetime.now(CHINA_TZ)
            self._last_new_count = len(fresh)
            return fresh

    async def manual_fetch_portal(
        self,
        type_id: int,
        *,
        from_page: int = 1,
        to_page: int = 1,
        search_value: str | None = None,
    ) -> list[Notice]:
        """手动抓取门户历史（按页数区间 / 关键词），视为回填，不写 RSS。"""
        async with self._poll_lock:
            notices = await self.fetcher.fetch_portal_type(
                type_id,
                from_page=from_page,
                to_page=to_page,
                search_value=search_value,
            )
            new_notices, _ = await self._ingest(
                notices, backfill=True, write_rss=False
            )
            self._last_poll_at = datetime.now(CHINA_TZ)
            self._last_new_count = len(new_notices)
            return new_notices

    async def _ingest(
        self, notices: list[Notice], *, backfill: bool, write_rss: bool
    ) -> tuple[list[Notice], list[Notice]]:
        """入库 -> 标记 -> 归档入队 -> （非回填时）推送。返回 (新增, 已推送)。"""
        if not notices:
            return [], []
        if write_rss:
            await self.fetcher.write_rss(notices)

        new_notices = await self.store.upsert_notices(notices)
        if not new_notices:
            return [], []

        await self.store.mark_pushed([n.id for n in new_notices])
        await self._enqueue_archive(new_notices)

        if backfill and not self.settings.backfill_push:
            return new_notices, []

        fresh = self._pushable(new_notices)
        if fresh:
            await self._publish(fresh)
        return new_notices, fresh

    async def _is_initial_poll(self) -> bool:
        return (await self.store.get_meta("initial_poll_done")) is None

    async def _enqueue_archive(self, notices: list[Notice]) -> None:
        if self.archiver is None:
            return
        cutoff = self.archive_cutoff()
        selected = [
            n for n in notices if n.published_at.year > 2000 and n.published_at >= cutoff
        ]
        limit = max(0, self.settings.archive_enqueue_limit_per_poll)
        if limit:
            selected = selected[:limit]
        if selected:
            await self.archiver.enqueue_many(selected)

    def archive_cutoff(self, now: datetime | None = None) -> datetime:
        """自动归档时间窗：max(floor_date, now - window_days)，即二者取较晚者。"""
        now = now or datetime.now(CHINA_TZ)
        window = now - timedelta(days=max(0, self.settings.archive_window_days))
        floor = self._parse_floor_date()
        return max(floor, window) if floor is not None else window

    def _parse_floor_date(self) -> datetime | None:
        raw = (self.settings.archive_floor_date or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            logger.warning("[ENGINE] archive_floor_date 无法解析：%s", raw)
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CHINA_TZ)
        return parsed

    def _pushable(self, notices: list[Notice]) -> list[Notice]:
        """过滤掉解析失败（2000 年占位）和过旧的通知，避免首次启动刷屏。"""
        threshold = datetime.now(CHINA_TZ) - timedelta(
            days=self.settings.push_max_age_days
        )
        return [
            n
            for n in notices
            if n.published_at.year > 2000 and n.published_at >= threshold
        ]

    async def _publish(self, notices: list[Notice]) -> None:
        for publisher in self.publishers:
            try:
                await publisher.publish(notices)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[ENGINE] Publisher %s 推送失败", type(publisher).__name__
                )

    # ---------------- 常驻循环 ----------------

    async def run_forever(self) -> None:
        interval_seconds = max(1, self.settings.poll_interval_minutes) * 60
        if self.settings.poll_on_start:
            await self._safe_poll()

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval_seconds)
                break
            except TimeoutError:
                pass
            await self._safe_poll()

    async def _safe_poll(self) -> None:
        try:
            await self.poll_once()
        except Exception:  # noqa: BLE001
            logger.exception("[ENGINE] 轮询失败")
        try:
            removed = await self.store.purge_older_than_days(
                self.settings.notice_retention_days
            )
            if removed:
                logger.info("[ENGINE] 清理过期通知 %d 条", removed)
        except Exception:  # noqa: BLE001
            logger.exception("[ENGINE] 清理过期通知失败")

    def stop(self) -> None:
        self._stop.set()
