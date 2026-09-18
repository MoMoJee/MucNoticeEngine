"""REST API 层（FastAPI）。

取代原 AstrBot 插件的聊天命令：查询/触发抓取/管理 webhook 订阅都改为 REST。
引擎通过 create_app 注入；本模块不反向依赖任何具体运行方式。
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..core.engine import NoticeEngine
from ..core.fetcher import CHINA_TZ, MucRssService
from ..core.models import Notice
from ..core.rendering import render_notices
from ..core.sources import SOURCES
from .publishers import SubscriberStore

logger = logging.getLogger(__name__)


class SubscriberIn(BaseModel):
    url: str = Field(..., description="接收通知的 webhook 地址")
    secret: str = Field("", description="可选，用于 HMAC-SHA256 签名")
    source_keys: list[str] = Field(
        default_factory=list, description="为空表示订阅全部来源"
    )


def create_app(
    *,
    engine: NoticeEngine,
    store,
    settings: Settings,
    fetcher: MucRssService,
    subscribers: SubscriberStore,
) -> FastAPI:
    app = FastAPI(
        title="MucNoticeEngine",
        version="0.1.0",
        description="中央民族大学多站点通知聚合 / 存储 / 去重引擎",
    )

    def require_token(authorization: str = Header(default="")) -> None:
        if not settings.api_token:
            return
        expected = f"Bearer {settings.api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid or missing token")

    auth = Depends(require_token)

    # ---------------- 基础 ----------------

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "source_count": len(SOURCES),
            "notice_count": await store.count(),
            "last_poll_at": engine.last_poll_at.isoformat()
            if engine.last_poll_at
            else None,
            "last_new_count": engine.last_new_count,
            "server_time": datetime.now(CHINA_TZ).isoformat(),
        }

    @app.get("/api/sources", dependencies=[auth])
    async def list_sources() -> list[dict]:
        return [
            {
                "key": s.get("key"),
                "name": s.get("name"),
                "category": s.get("category"),
                "url": s.get("url"),
                "requires_auth": bool(s.get("requires_auth", False)),
            }
            for s in SOURCES
        ]

    # ---------------- 通知查询 ----------------

    @app.get("/api/notices", dependencies=[auth])
    async def list_notices(
        source: str | None = Query(None, description="逗号分隔的 source_key"),
        category: str | None = None,
        since: datetime | None = None,
        q: str | None = Query(None, description="标题关键词"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict:
        source_keys = [s.strip() for s in source.split(",") if s.strip()] if source else None
        notices: list[Notice] = await store.query(
            source_keys=source_keys,
            category=category,
            since=since,
            q=q,
            limit=limit,
            offset=offset,
        )
        return {
            "count": len(notices),
            "items": [n.to_dict() for n in notices],
        }

    @app.get("/api/notices/{notice_id}", dependencies=[auth])
    async def get_notice(notice_id: str) -> dict:
        notice = await store.get(notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="notice not found")
        return notice.to_dict()

    @app.get("/api/stats", dependencies=[auth])
    async def stats() -> dict:
        return {"sources": await store.stats()}

    # ---------------- 触发抓取 ----------------

    @app.post("/api/check", dependencies=[auth])
    async def check_now() -> dict:
        """立即抓取一轮；返回本轮新推送的通知。"""
        fresh = await engine.poll_once()
        return {"new_count": len(fresh), "items": [n.to_dict() for n in fresh]}

    # ---------------- 卡片渲染（可选）----------------

    @app.get("/api/card.png", dependencies=[auth])
    async def card(
        source: str | None = None,
        limit: int = Query(5, ge=1, le=10),
    ):
        source_keys = [s.strip() for s in source.split(",") if s.strip()] if source else None
        notices = await store.query(source_keys=source_keys, limit=limit)
        if not notices:
            raise HTTPException(status_code=404, detail="no notices")
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="muc_card_")
        os.close(fd)
        try:
            render_notices([n.to_dict() for n in notices], tmp_path)
        except RuntimeError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        return FileResponse(tmp_path, media_type="image/png", filename="muc_notices.png")

    # ---------------- RSS ----------------

    @app.get("/api/rss", dependencies=[auth])
    async def rss():
        path = settings.rss_file_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="rss not generated yet")
        return FileResponse(path, media_type="application/rss+xml")

    # ---------------- Webhook 订阅管理 ----------------

    @app.get("/api/subscribers", dependencies=[auth])
    async def list_subscribers() -> list[dict]:
        return await subscribers.list()

    @app.post("/api/subscribers", dependencies=[auth], status_code=201)
    async def add_subscriber(body: SubscriberIn) -> dict:
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="url must be http(s)")
        return await subscribers.add(body.url, body.secret, body.source_keys)

    @app.delete("/api/subscribers/{subscriber_id}", dependencies=[auth])
    async def remove_subscriber(subscriber_id: str) -> JSONResponse:
        removed = await subscribers.remove(subscriber_id)
        if not removed:
            raise HTTPException(status_code=404, detail="subscriber not found")
        return JSONResponse({"removed": subscriber_id})

    return app
