"""REST API 的响应模型（OpenAPI schema 来源）。

这些模型只描述传输层返回结构，字段语义以 docs/guides/rest-api.md 为准。
新增/修改接口时必须同步这里，否则 /docs、/redoc、/openapi.json 会退化成空对象。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorOut(BaseModel):
    """通用错误响应。"""

    detail: str = Field(..., description="错误说明")


class NoticeOut(BaseModel):
    """单条通知（Notice.to_dict）。"""

    id: str = Field(..., description="source_key:sha1(source_key|link)，入库后稳定")
    title: str
    link: str
    source: str = Field(..., description="来源展示名")
    source_key: str
    category: str
    date: str = Field(..., description="YYYY-MM-DD HH:MM")
    pub_date: str = Field(..., description="RSS pubDate（RFC 822）")
    published_at: str = Field(..., description="ISO 8601（+08:00）")
    external_id: str = Field(
        "", description="门户 notice_id 或公开源 URL slug；仅用于详情/归档命名"
    )
    summary: str = Field("", description="摘要（门户正文前 80 字；公开源为空）")
    content: str = Field("", description="正文预览（最多 2000 字）")


class NoticeListOut(BaseModel):
    count: int
    items: list[NoticeOut]


class HealthArchiveOut(BaseModel):
    pending: int = Field(..., description="归档队列积压")
    total_bytes: int = Field(..., description="归档目录总大小（字节）")


class HealthOut(BaseModel):
    status: str
    source_count: int
    notice_count: int
    last_poll_at: str | None
    last_new_count: int
    server_time: str
    archive_enabled: bool
    archive: HealthArchiveOut | None = None


class SourceOut(BaseModel):
    key: str
    name: str
    category: str
    url: str
    requires_auth: bool = Field(..., description="true 表示门户源，需要登录配置")


class StatsRowOut(BaseModel):
    source_key: str
    source: str
    total: int
    pushed: int
    latest: str | None


class StatsOut(BaseModel):
    sources: list[StatsRowOut]


class SearchSiteOut(BaseModel):
    key: str
    name: str
    host: str
    owner: str = Field(..., description="VSB9 站点 ID，用于远端检索")


class SearchSitesOut(BaseModel):
    count: int
    sites: list[SearchSiteOut]


class SearchHitOut(BaseModel):
    title: str
    link: str
    published_at: str
    column: int
    column_name: str
    owner: str
    owner_name: str
    snippet: str = Field("", description="远端高亮摘要（已去 HTML 标签）")
    external_id: str


class SearchQueryOut(BaseModel):
    q: str
    match: str = Field(..., description="all=全部关键词，any=任意一个")
    scope: str = Field(..., description="all / title / content")
    order: str = Field(..., description="date=按时间，score=相关度")
    exclude: str = Field("", description="本地过滤词，空格分隔")
    since: str = ""
    until: str = ""


class SearchResultOut(BaseModel):
    site: SearchSiteOut
    remote_total: int = Field(..., description="远端命中总数")
    scanned: int = Field(..., description="实际扫描的远端条数（去重/排除前）")
    truncated: bool = Field(..., description="扫描到上限仍未凑满 limit")
    count: int = Field(..., description="本地过滤/截断后实际返回条数")
    hits: list[SearchHitOut]
    error: str = Field("", description="非空表示远端调用失败（HTTP 仍为 200）")
    query: SearchQueryOut


class CheckOut(BaseModel):
    new_count: int = Field(..., description="新增入库条数")
    items: list[NoticeOut]
    backfill: bool | None = Field(
        None, description="门户回填请求返回 true；普通轮询不返回该字段"
    )


class ArchiveQueuedOut(BaseModel):
    queued: str = Field(..., description="已入队的通知 id")


class NoticeFileOut(BaseModel):
    kind: str = Field(..., description="content / attachment / image")
    filename: str
    size: int
    sha1: str
    first_download_at: str
    last_access_at: str


class NoticeFilesOut(BaseModel):
    notice_id: str
    count: int
    items: list[NoticeFileOut]


class SubscriberOut(BaseModel):
    id: str
    url: str
    secret: str = Field("", description="webhook HMAC-SHA256 签名密钥，空串表示不签名")
    source_keys: str = Field("", description="逗号分隔；空串表示订阅全部来源")
    active: int
    created_at: str


class SubscriberRemovedOut(BaseModel):
    removed: str
