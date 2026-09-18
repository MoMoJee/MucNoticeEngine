"""Webhook 推送 + 订阅者持久化。

WebhookPublisher 实现 `core.engine.Publisher` 协议：引擎只负责说「有新通知」，
具体怎么发（HTTP POST、签名、重试）都由本模块决定。两者互不知道对方存在。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from ..config import Settings
from ..core.fetcher import CHINA_TZ
from ..core.models import Notice

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    secret      TEXT NOT NULL DEFAULT '',
    source_keys TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
"""


class SubscriberStore:
    """webhook 订阅者的 SQLite 存储。source_keys 为空表示订阅全部来源。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    async def list(self) -> list[dict]:
        return await asyncio.to_thread(self._list)

    def _list(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM subscribers ORDER BY created_at"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    async def get_active(self) -> list[dict]:
        return [s for s in await self.list() if s["active"]]

    async def add(
        self, url: str, secret: str = "", source_keys: list[str] | None = None
    ) -> dict:
        return await asyncio.to_thread(
            self._add, url, secret, source_keys or []
        )

    def _add(self, url: str, secret: str, source_keys: list[str]) -> dict:
        sub = {
            "id": uuid.uuid4().hex[:12],
            "url": url,
            "secret": secret,
            "source_keys": ",".join(source_keys),
            "active": 1,
            "created_at": datetime.now(CHINA_TZ).isoformat(),
        }
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO subscribers (id, url, secret, source_keys, active, created_at) "
                "VALUES (:id, :url, :secret, :source_keys, :active, :created_at)",
                sub,
            )
        return _row_to_dict(sub)

    async def remove(self, subscriber_id: str) -> bool:
        return await asyncio.to_thread(self._remove, subscriber_id)

    def _remove(self, subscriber_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM subscribers WHERE id = ?", (subscriber_id,)
            )
            return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


class WebhookPublisher:
    """把新通知 POST 给所有订阅者。可选 HMAC-SHA256 签名。"""

    def __init__(self, subscribers: SubscriberStore, settings: Settings):
        self.subscribers = subscribers
        self.settings = settings

    async def publish(self, notices: list[Notice]) -> None:
        subs = await self.subscribers.get_active()
        if not subs:
            return

        async with httpx.AsyncClient(
            timeout=self.settings.webhook_timeout_seconds
        ) as client:
            await asyncio.gather(
                *(self._send(client, sub, notices) for sub in subs),
                return_exceptions=True,
            )

    def _filter(self, sub: dict, notices: list[Notice]) -> list[Notice]:
        keys = {k for k in sub.get("source_keys", "").split(",") if k}
        if not keys:
            return notices
        return [n for n in notices if n.source_key in keys]

    async def _send(
        self, client: httpx.AsyncClient, sub: dict, notices: list[Notice]
    ) -> None:
        selected = self._filter(sub, notices)
        if not selected:
            return

        payload = {
            "event": "notices.new",
            "count": len(selected),
            "generated_at": datetime.now(CHINA_TZ).isoformat(),
            "notices": [n.to_dict() for n in selected],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-MUC-Event": "notices.new"}
        signature = _sign(body, sub.get("secret", ""))
        if signature:
            headers["X-MUC-Signature"] = f"sha256={signature}"

        try:
            resp = await client.post(sub["url"], content=body, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "[WEBHOOK] %s 返回 %s", sub["url"], resp.status_code
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WEBHOOK] 推送 %s 失败: %s", sub["url"], exc)


def _sign(body: bytes, secret: str) -> str:
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _row_to_dict(row) -> dict:
    data = dict(row)
    data["active"] = bool(data.get("active", 1))
    return data
