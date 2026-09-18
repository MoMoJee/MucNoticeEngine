"""REST API 层（FastAPI）。

取代原 AstrBot 插件的聊天命令：查询/触发抓取/管理 webhook 订阅都改为 REST。
引擎通过 create_app 注入；本模块不反向依赖任何具体运行方式。
"""

from __future__ import annotations

import html
import logging
import os
import tempfile
import zipfile
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..core.aop import AOP_SITES, AopSearchClient, resolve_site
from ..core.archive import ArchiveStore, safe_filename
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


class CheckIn(BaseModel):
    source: str | None = Field(None, description="逗号分隔的 source_key")
    type: int | None = Field(None, description="门户 type；给了就按门户历史抓取")
    from_page: int = Field(1, ge=1)
    to_page: int = Field(1, ge=1)
    search_value: str | None = Field(None, description="门户 searchValue 关键词")
    backfill: bool = Field(True, description="仅普通轮询有效；回填默认不推送")


def create_app(
    *,
    engine: NoticeEngine,
    store,
    settings: Settings,
    fetcher: MucRssService,
    subscribers: SubscriberStore,
    archive_store: ArchiveStore | None = None,
    aop_client: AopSearchClient | None = None,
) -> FastAPI:
    app = FastAPI(
        title="MucNoticeEngine",
        version="0.1.0",
        description="中央民族大学多站点通知聚合 / 存储 / 去重引擎",
    )
    search_client = aop_client or AopSearchClient()

    def require_token(authorization: str = Header(default="")) -> None:
        if not settings.api_token:
            return
        expected = f"Bearer {settings.api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid or missing token")

    auth = Depends(require_token)

    def archived_path(notice: Notice, filename: str):
        if archive_store is None:
            return None
        path = archive_store.notice_dir(notice) / filename
        return path if path.is_file() else None

    # ---------------- 基础 ----------------

    @app.get("/")
    async def index() -> HTMLResponse:
        """首页引导：接口文档在 /docs（Swagger UI）。"""
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<title>MucNoticeEngine</title>"
            "<h1>MucNoticeEngine</h1>"
            "<p>中央民族大学多站点通知聚合 / 存储 / 去重引擎</p>"
            "<ul>"
            "<li><a href='/docs'>API 文档（Swagger UI）</a></li>"
            "<li><a href='/redoc'>API 文档（ReDoc）</a></li>"
            "<li><a href='/openapi.json'>OpenAPI schema</a></li>"
            "<li><a href='/health'>健康检查</a></li>"
            "<li><a href='/api/notices'>通知列表</a></li>"
            "<li><a href='/api/sources'>来源列表</a></li>"
            "</ul>"
            "<p>使用语义与历史回填见仓库 <code>docs/guides/rest-api.md</code>。</p>"
        )

    @app.get("/health")
    async def health() -> dict:
        payload = {
            "status": "ok",
            "source_count": len(SOURCES),
            "notice_count": await store.count(),
            "last_poll_at": engine.last_poll_at.isoformat()
            if engine.last_poll_at
            else None,
            "last_new_count": engine.last_new_count,
            "server_time": datetime.now(CHINA_TZ).isoformat(),
            "archive_enabled": archive_store is not None,
        }
        if archive_store is not None:
            payload["archive"] = {
                "pending": engine.archive_pending,
                "total_bytes": await store.total_asset_size(),
            }
        return payload

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
        q: str | None = Query(None, description="关键词，匹配标题/摘要/正文预览"),
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
        await store.touch_assets(notice_id)
        return notice.to_dict()

    # ---------------- 正文 / 附件 ----------------

    @app.get("/api/notices/{notice_id}/content", dependencies=[auth])
    async def get_notice_content(notice_id: str):
        notice = await store.get(notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="notice not found")
        await store.touch_assets(notice_id)

        path = archived_path(notice, "content.html")
        if path is not None:
            return FileResponse(path, media_type="text/html; charset=utf-8")

        if notice.content:
            body = (
                "<!doctype html><meta charset='utf-8'>"
                f"<h1>{html.escape(notice.title)}</h1>"
                f"<pre>{html.escape(notice.content)}</pre>"
            )
            return HTMLResponse(
                body, headers={"X-Muc-Content": "preview"}
            )
        raise HTTPException(status_code=404, detail="content not archived yet")

    @app.get("/api/notices/{notice_id}/content.zip", dependencies=[auth])
    async def get_notice_content_zip(notice_id: str):
        notice = await store.get(notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="notice not found")
        await store.touch_assets(notice_id)

        directory = archive_store.notice_dir(notice) if archive_store else None
        if directory is None or not (directory / "content.html").is_file():
            raise HTTPException(status_code=404, detail="content not archived yet")

        fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="muc_content_")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as bundle:
                for filename in ("content.html", "content.txt", "meta.json"):
                    candidate = directory / filename
                    if candidate.is_file():
                        bundle.write(candidate, arcname=filename)
                for asset in await store.get_assets(notice_id):
                    if asset.get("kind") != "attachment":
                        continue
                    asset_path = (
                        archive_store.resolve_local(asset.get("local_path", ""))
                        if archive_store
                        else None
                    )
                    if asset_path is not None and asset_path.is_file():
                        bundle.write(
                            asset_path, arcname=f"files/{asset['filename']}"
                        )
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        name = safe_filename(f"{notice.external_id or notice.id}.zip", "notice.zip")
        return FileResponse(tmp_path, media_type="application/zip", filename=name)

    @app.get("/api/notices/{notice_id}/files", dependencies=[auth])
    async def list_notice_files(notice_id: str, name: str | None = None):
        notice = await store.get(notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="notice not found")
        await store.touch_assets(notice_id)
        assets = await store.get_assets(notice_id)

        if name is not None:
            asset = next((a for a in assets if a.get("filename") == name), None)
            if asset is None:
                raise HTTPException(status_code=404, detail="file not found")
            path = (
                archive_store.resolve_local(asset.get("local_path", ""))
                if archive_store
                else None
            )
            if path is None or not path.is_file():
                raise HTTPException(status_code=404, detail="file missing on disk")
            return FileResponse(path, filename=asset["filename"])

        return {
            "notice_id": notice_id,
            "count": len(assets),
            "items": [
                {
                    "kind": a.get("kind"),
                    "filename": a.get("filename"),
                    "size": a.get("size"),
                    "sha1": a.get("sha1"),
                    "first_download_at": a.get("first_download_at"),
                    "last_access_at": a.get("last_access_at"),
                }
                for a in assets
            ],
        }

    @app.post("/api/notices/{notice_id}/archive", dependencies=[auth], status_code=202)
    async def archive_notice(notice_id: str) -> dict:
        notice = await store.get(notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="notice not found")
        if engine.archiver is None:
            raise HTTPException(status_code=409, detail="archive is disabled")
        await engine.archiver.enqueue(notice, force=True)
        return {"queued": notice_id}

    @app.get("/api/stats", dependencies=[auth])
    async def stats() -> dict:
        return {"sources": await store.stats()}

    # ---------------- 远程检索（AOP 智能搜索，不写库） ----------------

    @app.get("/api/search/sites", dependencies=[auth])
    async def search_sites() -> dict:
        return {"count": len(AOP_SITES), "sites": [site.to_dict() for site in AOP_SITES]}

    @app.get("/api/search", dependencies=[auth])
    async def remote_search(
        site: str = Query(..., description="站点 key（也接受 owner/host/名称），见 /api/search/sites"),
        q: str = Query(..., min_length=1, description="关键词，空格分隔"),
        match: str = Query("any", pattern="^(all|any)$", description="all=全部关键词，any=任意一个"),
        exclude: str | None = Query(None, description="空格分隔；标题/摘要命中任一词则本地排除"),
        scope: str = Query("all", pattern="^(all|title|content)$", description="检索范围"),
        order: str = Query("date", pattern="^(date|score)$", description="date=按时间，score=按相关度"),
        since: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
        until: str | None = Query(None, description="截止日期 YYYY-MM-DD"),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict:
        target = resolve_site(site)
        if target is None:
            raise HTTPException(status_code=404, detail=f"unknown site: {site}")
        try:
            result = await search_client.search(
                target,
                q,
                match=match,
                exclude=exclude,
                scope=scope,
                order=order,
                since=since,
                until=until,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = result.to_dict()
        payload["query"] = {
            "q": q,
            "match": match,
            "scope": scope,
            "order": order,
            "exclude": exclude or "",
            "since": since or "",
            "until": until or "",
        }
        return payload

    # ---------------- 触发抓取 ----------------

    @app.post("/api/check", dependencies=[auth])
    async def check_now(body: CheckIn | None = None) -> dict:
        """立即抓取。给了 `type` 就按门户历史（页数区间/关键词）抓取并视为回填。"""
        if body is not None and body.type is not None:
            from_page = max(1, body.from_page)
            to_page = max(from_page, body.to_page)
            notices = await engine.manual_fetch_portal(
                body.type,
                from_page=from_page,
                to_page=to_page,
                search_value=body.search_value,
            )
            return {
                "new_count": len(notices),
                "items": [n.to_dict() for n in notices],
                "backfill": True,
            }

        source_keys = (
            {s.strip() for s in body.source.split(",") if s.strip()}
            if body is not None and body.source
            else None
        )
        fresh = await engine.poll_once(
            source_keys, backfill=body.backfill if body is not None else None
        )
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
        return FileResponse(path, media_type="application/rss+xml; charset=utf-8")

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
