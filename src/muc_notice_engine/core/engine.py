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


class NoticeEngine:
    def __init__(
        self,
        settings: Settings,
        fetcher: MucRssService,
        store: NoticeStore,
        publishers: list[Publisher] | None = None,
    ):
        self.settings = settings
        self.fetcher = fetcher
        self.store = store
        self.publishers: list[Publisher] = list(publishers or [])

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

    def add_publisher(self, publisher: Publisher) -> None:
        self.publishers.append(publisher)

    # ---------------- 单次轮询 ----------------

    async def poll_once(self, source_keys: set[str] | None = None) -> list[Notice]:
        """抓取一轮，入库，返回「新且值得推送」的通知（已发布给 Publisher）。"""
        async with self._poll_lock:
            notices = await self.fetcher.fetch_notices(source_keys)
            if not notices:
                self._last_poll_at = datetime.now(CHINA_TZ)
                self._last_new_count = 0
                return []

            await self.fetcher.write_rss(notices)
            new_notices = await self.store.upsert_notices(notices)

            fresh: list[Notice] = []
            if new_notices:
                await self.store.mark_pushed([n.id for n in new_notices])
                fresh = self._pushable(new_notices)
                if fresh:
                    await self._publish(fresh)

            self._last_poll_at = datetime.now(CHINA_TZ)
            self._last_new_count = len(fresh)
            return fresh

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
