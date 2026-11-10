# 0012 外链正文与图片归档

- Status: approved
- Owner: MucNoticeEngine
- Created: 2026-11-11
- Related: [USS-Maintain 002](../../../USS-Maintain/docs/plans/002-muc-notice-external-content.md)

## 背景与目标

门户信息流存在两类条目：一类 `notice_content` 自带完整 HTML；另一类 `notice_content`
为空、正文在 `notice_link` 指向的外站（微信、人民网、学院新闻、图书馆动态页等）。
当前 `_fetch_portal_detail()` 只读 `notice_content`，外链条目归档为空，导致
`/api/notices/{id}/content` 大量 404。

目标：门户正文为空且存在 `notice_link` 时自动回落抓取外链正文、图片与附件，写入现有
归档目录与 `assets` 表，保持 `/content`、`/content.zip`、LRU 淘汰语义不变。

验收：外链样本 `/content` 不再 404；微信 `data-src` 图片可入库；通知类来源零回归。

## 方案

- `MucRssService._fetch_portal_detail()`：`notice_content` 为空且 `notice_link` 为
  http(s) 时，复用公开正文抓取流程，合并门户附件与外链附件。
- 公开正文抓取抽出公共流程：选择器命中优先、`body` 兜底；图片识别
  `data-src` / `data-original` / `data-lazy-src` / `src`，`urljoin` 后按 URL 去重；
  `<a>` 按附件后缀识别；`lib.muc.edu.cn/engine2` 解析内嵌 `data` JSON 的 `content`。
- `_parse_portal_item()`：`link` 优先 `notice_link`，无外链保留打印页。
- `ArchiveStore`：文件与图片分别受 `archive_max_per_notice` /
  `archive_max_images_per_notice` 限制；下载支持 5xx/超时重试，同域限速；
  外链文件响应无 `content-disposition` 时按 content-type 判断（拒绝 HTML）。
- 可观测：正文/图片/附件失败日志带 `source`、`url`、`stage`、`status`。

## 影响面

- core：`fetcher.py`（外链回落、图片/附件抽取、lib JSON、重试与限速）、
  `archive.py`（图片上限、下载重试/限速、日志）、`models.py`（无 schema 变化）。
- transport：无接口变化；`/content` 自然由 404 变为 200。
- 配置：`archive_max_images_per_notice`、`archive_external_retries`、
  `archive_host_interval_ms`。
- 数据/schema：无迁移；沿用 `archive_dir/<source_key>/<external_id>/files` 与 `assets` 表。
- 文档：`docs/guides/rest-api.md`（正文/归档语义）、`docs/architecture.md`（数据流）、
  `README.md`（能力说明）、`docs/plans/README.md`、`docs/changelog/README.md`。

## 风险与备选

- 微信批量抓取触发限流：同域串行 + 请求间隔 + 失败退避；单篇图片数上限。
- 外站结构变化：选择器 + body 兜底，单条失败不阻塞队列。
- 图片体积膨胀：单文件上限、单篇图片上限、全库 LRU。
- 不引入无头浏览器，不执行第三方 JS；只抓 `http/https`，拒绝明显内网/回环地址。

## 验证方式

- `uv run ruff check .`
- `uv run pytest -q`（新增外链回落、`data-src`、lib JSON、`notice_link` 优先级、
  图片上限与下载重试用例）
- 生产机对 11-05 以来失败条目 `POST /api/notices/{id}/archive` 后复查 `/content`。

## 任务拆分

- [x] 计划与文档骨架
- [x] fetcher 外链回落与资源抽取
- [x] archive 图片上限/重试/限速
- [x] 配置与文档同步
- [x] 单测与 lint
