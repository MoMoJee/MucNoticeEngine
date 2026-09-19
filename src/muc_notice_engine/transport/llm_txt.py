"""Agent / 自动化调用方的入口索引（`/llm.txt` 与 `/llms.txt`）。

只做指路：接口语义以 `docs/` 为准，这里不复制细则，避免两处维护。
"""

from __future__ import annotations

from ..core.aop import AOP_SITES
from ..core.sources import SOURCES

REPO_URL = "https://github.com/MoMoJee/MucNoticeEngine"
DOCS_BASE = f"{REPO_URL}/blob/master"


def llm_txt() -> str:
    return f"""# MucNoticeEngine

> 中央民族大学多来源通知的聚合 / 去重 / 存储服务，对外只有 REST API 与 webhook。
> 本文件（/llms.txt，/llm.txt 会跳转到此）是给 Agent / 自动化调用方的入口索引；
> 不了解站点规则时，首次调用前先读完本文件。

## 首次调用前必读（按顺序）

1. 接口语义与参数（权威，别猜参数）：
   GET /llm/rest-api.md（服务自托管 markdown；仓库路径 docs/guides/rest-api.md）
2. 机器可读 schema：GET /openapi.json （交互文档：GET /docs、GET /redoc）
3. 远程检索规则（用 /api/search 前必读）：
   GET /llm/aop-search.md（仓库路径 docs/reference/aop-search.md）

> 文档由本服务托管（`/llm/*.md`），Agent 不依赖 GitHub 也能读。
> 仅在服务不可用时用 GitHub 兜底：{DOCS_BASE}/docs/guides/rest-api.md
> 可选托管文档：/llm/index.md、/llm/portal-notice-types.md。

## 按任务查

- 本地已入库通知（搜 标题/摘要/正文前 2000 字）：
  GET /api/notices?q=&source=&since=&limit=&offset=
- 来源清单：GET /api/sources
- 远程全文检索（AOP，只读、不写库）：
  GET /api/search?site=<key>&q=&match=all|any&scope=all|title|content&order=date|score&since=&until=&limit=
  站点 key 目录：GET /api/search/sites（共 {len(AOP_SITES)} 个）
- 触发抓取（会写库，慎用）：POST /api/check
- 正文/附件：GET /api/notices/{{id}}/content、/content.zip、/files
- RSS：GET /api/rss ；健康检查（始终公开）：GET /health

## 规则摘要（完整语义见上面文档）

- 本地库只来自 {len(SOURCES)} 个来源；/api/notices 搜不到 ≠ 全校没有，可改用 /api/search。
- /api/search 是远端只读检索：不写库、不入 RSS、不触发 webhook；每次最多扫描 200 条。
- 分页上限：/api/notices limit<=500、/api/search limit<=100；用 offset/翻页，不要高频重试。
- 若 /api/* 返回 401，说明启用了 MNE_API_TOKEN：需 `Authorization: Bearer <token>`，
  token 向服务运维索取；/ 、/health、/docs、/llms.txt 始终公开。
- 不要用 /api/check 高频轮询；日常抓取由服务定时执行。

## 其他

- 文档托管：GET /llm/index.md、/llm/rest-api.md、/llm/aop-search.md、/llm/portal-notice-types.md
- 项目主页：{REPO_URL}
- 变更记录：{DOCS_BASE}/docs/changelog
"""
