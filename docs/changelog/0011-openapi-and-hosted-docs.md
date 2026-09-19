# 0011 OpenAPI 补全与服务自托管文档

- Plan: [0011](../plans/0011-openapi-and-hosted-docs.md)
- Type: feat
- Date: 2026-09-19

## Summary

给 `/docs`、`/redoc`、`/openapi.json` 补上真实的响应模型与错误响应，Agent 可直接消费；
新增 `GET /llm/{name}.md` 由服务托管语义文档，`/llms.txt` 首选指向服务自身，GitHub 仅兜底。

## Changes

- transport/schemas.py（新）：`NoticeOut`/`NoticeListOut`/`HealthOut`/`SourceOut`/`StatsOut`/
  `SearchSitesOut`/`SearchResultOut`/`CheckOut`/`NoticeFilesOut`/`SubscriberOut`/`ErrorOut` 等。
- transport/llm_docs.py（新）：`HOSTED_DOCS` 白名单（index / rest-api / aop-search /
  portal-notice-types），从部署目录 `docs/` 只读托管；缺失返回 404。
- transport/api.py：
  - JSON 接口加 `response_model` 与参数 description；文件/HTML 接口用 `responses=` 声明
    真实 content-type；统一 `err_404`/`err_409`/`err_501` 错误响应；
  - `POST /api/check` 用 `response_model_exclude_none` 保持普通轮询响应不变；
  - 新增 `GET /llm/{name}.md`。
- transport/llm_txt.py：首次必读改为 `/llm/rest-api.md`、`/llm/aop-search.md`，
  GitHub 只作兜底，并列出可托管文档。
- core / 配置 / 数据：无。
- 文档：`docs/conventions/docs.md`（新增「OpenAPI 与自托管文档」专节 + 同步矩阵 +
  检查清单）、`docs/guides/rest-api.md`（读取顺序、接口表）、`README.md`、
  `docs/index.md`（代码结构 + 硬性规则）、`AGENTS.md`（工作流 + 改哪里表）。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 63 passed（新增：openapi 含 `NoticeOut`/`SearchResultOut`、
  `/api/notices` 200 `$ref`、404/409 已声明；`/llm/rest-api.md`、`/llm/aop-search.md`
  返回 markdown，未知文档 404；`/llms.txt` 指向 `/llm/*.md`）
- 生产机更新后 `curl .../llm/rest-api.md`、`curl .../openapi.json` 人工复核。

## Breaking changes

无。`/api/check` 普通轮询响应与之前一致（不新增 `backfill: null`）。

## Follow-ups

- 生产机部署后复核 `/docs` 渲染与 `/llm/*.md`。
- 后续若加接口，按 conventions 的检查清单补 `response_model` 与自托管白名单。
