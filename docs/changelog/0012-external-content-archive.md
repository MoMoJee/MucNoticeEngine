# 0012 外链正文与图片归档

- Plan: [0012](../plans/0012-external-content-archive.md)
- Type: feat
- Date: 2026-11-11

## Summary

门户详情 `notice_content` 为空时自动回落 `notice_link` 抓取外链正文、图片与附件，
修复聚合外链来源 `/api/notices/{id}/content` 大量 404。

## Changes

- core/fetcher.py：`_fetch_portal_detail()` 外链回落并合并门户附件；
  `_fetch_public_detail()` 抽出公共外链抓取；图片识别 `data-src` / `data-original` /
  `data-lazy-src` / `src`；`<a>` 按后缀识别附件；支持 `lib.muc.edu.cn/engine2`
  内嵌 `data` JSON 正文；`_parse_portal_item()` 的 `link` 优先 `notice_link`；
  外链请求按域名串行限速，5xx/网络异常重试，失败日志带来源/URL/阶段/状态码。
- core/archive.py：附件与图片分别按 `archive_max_per_notice` /
  `archive_max_images_per_notice` 限制；下载复用同域限速与重试；外链文件无
  `content-disposition` 时按 content-type 判断（仍拒绝 HTML/文本响应）。
- transport：无接口变化；`/content` 对外链条目自然由 404 变为 200。
- 配置：新增 `archive_max_images_per_notice`、`archive_external_retries`、
  `archive_host_interval_ms`（含环境变量映射）。
- 文档：`docs/guides/rest-api.md`（正文/归档语义）、`docs/architecture.md`（数据流）、
  `README.md`（能力说明）、`docs/plans/README.md`、`docs/changelog/README.md`、
  `config.example.toml`、`.env.example`。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 69 passed（新增：外链回落、`notice_link` 优先级、
  `data-src` 图片、engine2 内嵌 JSON、图片上限、5xx 重试）

## Breaking changes

无。归档目录结构、`assets` 表、`/content`、`/content.zip`、LRU 淘汰保持兼容，
无需数据迁移。已有外链条目可 `POST /api/notices/{id}/archive` 重新归档。

## Follow-ups

- 生产机重启后对 11-05 以来失败条目触发重新归档，核对正文/图片数量。
- 观察微信域名请求间隔与失败率，必要时调大 `archive_host_interval_ms`。
