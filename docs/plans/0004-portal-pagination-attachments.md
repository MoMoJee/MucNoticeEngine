# 0004 门户全量抓取、正文与附件归档

- Status: done（2026-09-18 交付，见 [changelog/0004](../changelog/0004-portal-pagination-attachments.md)）
- Owner: MoMoJee
- Created: 2026-09-18
- Related: [reference/portal-notice-types.md](../reference/portal-notice-types.md)、`core/fetcher.py`、`core/sources.py`

## 背景与目标

现状缺口：门户每类只抓第 1 页 20 条、只接入 `type=5/6/8/32`、公开源只存标题、正文与附件都不落盘。

目标：

1. 门户**翻页**抓取，并抓取**全部有效 type**。
2. 正文、附件、内联图片**落盘**到文件夹；数据库只存预览与文件索引。
3. 归档走**后台队列**，不阻塞轮询；设总量上限并按访问时间淘汰。
4. 支持**手动**按需抓取历史（绕过自动时间窗），自动/手动共用同一管线。

## 调研结论（2026-09-18 实测）

### 门户翻页：可行
- `datas.page` 提供 `total`（总条数）/`totalCounts`（总页数）/`currentPage`/`pageSize`；`currentPage` 翻页有效，超界返回空。例：type=11 total=2315。

### 官方 type 名称（字段 `notice_type_name`）
`1 新华网`、`3 民委要闻`、`4 时政头条`、`5 办公通知`、`6 教学通知`、`8 科研通知`、`9 校园新闻`、`10 就业信息`、`11 公示公告`、`32 学工通知`、`36 活动报道`。本次决定**全部抓取**。推免信息分散在 `6`（遴选/名额）与 `11`（名单/细则）。

### 正文：可行
- 门户 `notice_content` 为完整 HTML；公开源正文容器 `.v_news_content`/`#vsb_content` 抽样均命中（少数页面正文为空，需 fallback）。
- **bug**：`grs_yjszs` 的 `base_url` 指向站点根，导致链接 404（应在 `/yjsyzsw/`）。

### 附件：可行且普遍（需更正早前结论）
- **详情接口**：`POST /comsys-portal-notice-web/getNotice`（form `notice_id`）→ `datas.notice_info`，附件在 `notice_annext[]`：`notice_annex_id`(UUID)、`notice_annex_name`(文件名)、`notice_annex_path`、`suffix`、`type`。
- **下载**：`GET /comsys-portal-notice-web/download?id=<annex_id>&notice_id=<id>`，**需登录**；无 Cookie 返回 `200 text/html`（登录页），必须校验 `content-disposition`。
- 抽样 5 类 × 10 条：**44% 通知带文件附件**（type=6 8/10、type=11 6/10、type=32 6/10）。
- `notice_content` 内还有**内联图片** `<img>`，本次决定一并下载。

### 手动抓取/搜索能力：补充实测
- **不支持日期过滤**：尝试 `startTime/endTime`、`beginTime/endTime`、`startDate/endDate`、`releaseTimeStart/End`、`startReleaseTime/endReleaseTime`、`timeStart/timeEnd` 等 10 组参数，`total` 与返回结果均不变，参数也不回显。→ 历史抓取只能靠**翻页**。
- **支持关键词**：`searchValue=<kw>` 生效（实测 `推免` 过滤出相关通知），`page.searchValue` 回显。
- **认证边界 bug**：当 CAS 会话仍有效但 comsys 会话失效时，登录页 GET 返回 302，`_do_login` 把它当异常，导致登录失败（需清 Cookie 才能恢复）。

## 已确认决策（Decision Log）

1. **`rss_max_items` 只约束 RSS 输出**：`fetch_notices` 不再截断，改由 `write_rss` 内部截断。抓取/存储/归档/推送不受它限制。
2. **`Notice` 新增 `external_id`**：门户存 `notice_id`，公开源存文章标识；`fetch_detail` 用它调 `getNotice`（不再从 link 正则抠）。
3. **不做数据库迁移**：现有库无有用数据，直接删除 `data/muc_notice.db` 重建；文档注明改 schema 需清库。
4. **归档用后台队列**（`asyncio.Queue` + 若干 worker）。当前项目**没有任何现成队列机制**，本计划新建。
5. **统一 URL 拼接基准**：改用当前 `page_url` 做 `urljoin`，移除易错的硬编码 `base_url`（覆盖 `grs_yjszs` 及其它同风险来源）。
6. **门户抓取全部有效 type**（1/3/4/5/6/8/9/10/11/32/36），**不做关键词过滤**（type=11 的采购噪声一并入库）。
7. **自动归档时间窗**：`cutoff = max(2026-08-31T00:00:00+08:00, now - archive_window_days)`，二者取**较晚者**；`archive_window_days` 默认 **90**。仅 `published_at >= cutoff` 的通知被**自动**归档。
8. **手动抓取可绕过时间窗**：手动抓到的通知同样入库、可按需归档；**自动与手动共用同一 fetch→store→archive 管线**，仅触发方式与是否受窗口约束不同。
9. **`content` 保留为预览**：门户前 2000 字纯文本；完整原文/附件落盘。REST 返回预览。
10. **归档总量上限 64GB**（环境变量）；数据库维护**文件表**记录通知↔落盘文件（正文原文、附件）关系、**首次下载时间**、**最近访问时间**；超限时按**最近访问时间升序**淘汰。
11. **内联图片也下载**；正文接口提供两种输出：`纯 HTML（保留原始链接）` 与 `压缩包（HTML + 图片，链接不改写）`。
12. **`enrich_contents` 与 `fetch_detail` 合并**为单一正文抓取路径（废弃旧方法）。
13. 执行前述安全/运维项：`/files` 防路径穿越、未配置账号时匿名回退、下载与列表共用会话的失效处理。
14. **回填不推送（默认开启）**：**首次启动的首轮抓取**以及**手动抓取历史**视为「回填」，只入库 + 按时间窗归档，默认**不触发 webhook 推送**；可通过 `backfill_push`（默认 `false`）开启。正常轮询产生的新通知照常推送。回填状态需持久化（首轮标记），手动抓取在请求中显式标记为回填。
15. **手动历史抓取用页数区间**：list 接口**不支持日期过滤**（已实测），改用 `type` + `from_page`/`to_page`；同时接口支持 `searchValue` 关键词过滤，可用于手动定向抓取。
16. **修复认证边界 bug**：CAS 会话有效但 comsys 失效时登录页 302 被当异常。`_do_login` 需容忍 3xx（视为已认证或跟随重定向），列入 Phase 0。
17. **公开源归档范围（v1）**：门户做「正文 + 附件 + 内联图片」；公开源只存**正文 HTML/文本**，不下载图片/附件（后续再议）。
18. **目录与访问统计**：目录 `data/archive/<source_key>/<external_id>/`（门户 external_id = 原始 `notice_id`，公开源用文章路径 slug）；`assets.kind ∈ {content, attachment}`（内联图片归 `attachment`）；`last_access_at` 仅在访问 `GET /api/notices/{id}`、`/content`、`/content.zip`、`/files` 时更新（批量列表访问不算）；`evict_to_limit()` 在归档任务完成后触发并**节流**（≥60s 一次）。
19. **并发与限额默认值**：`archive_workers=2`、每轮入队上限 `archive_enqueue_limit_per_poll=50`、`archive_max_per_notice=50`、`archive_max_file_mb=50`；单个下载失败最多重试 2 次（5s/20s 退避）后跳过，不阻塞后续。

## 方案（设计）

> 职责拆分：发现附件（门户特有）留 fetcher；下载/落盘/淘汰（与来源无关）放 `core/archive.py`；引擎只入队编排。

- **模型**（`core/models.py`）：`Notice` 加 `external_id`；`Attachment(notice_id, annex_id, name, suffix, kind)`（`Attachment.kind` 表示来源类型 `∈ {file,image}`）；`NoticeDetail(notice, content_html, attachments)`。注意与落盘表 `assets.kind ∈ {content,attachment}` 区分：前者是「从网页发现的类型」，后者是「存到磁盘的类别」。
- **fetcher（发现，不碰文件系统）**：全量 type + 翻页；`fetch_detail(notice) -> NoticeDetail`；统一 urljoin。
- **新增 `core/archive.py`（取存 + 队列）**：
  - `ArchiveStore(settings, auth_service)`：目录布局、文件名安全化、单文件大小上限、sha1、原子写、`meta.json`。
  - **后台队列**：`asyncio.Queue` + `archive_workers` 个 worker，启动于 `initialize()`；`enqueue(notice, force=False)` 立即返回。
  - `archive(detail)`、`download(att, dest)`、`evict_to_limit()`（按 `last_access_at` 升序删到上限内）。
- **engine（编排）**：`poll_once` 去重后只**入队**（不 await 下载）；`Archiver` 协议与 `Publisher` 同款解耦；`archive_enable=False` 时不启用。
  - **回填标记**：区分「正常轮询」与「回填」（首轮持久化标记 / 手动请求标记）。回填只入库 + 按窗口归档，默认不推送；`backfill_push=True` 时才推送。
- **storage**：新增文件表 `assets(notice_id, kind, filename, local_path, size, sha1, first_download_at, last_access_at)`，`kind ∈ {content, attachment}`（内联图片归 `attachment`）；仅在访问通知详情/正文/附件接口时更新 `last_access_at`；**不存正文全文**。
- **transport**：
  - `GET /api/notices/{id}/content`（HTML，原始链接）
  - `GET /api/notices/{id}/content.zip`（HTML + 图片）
  - `GET /api/notices/{id}/files`（清单/单文件下载，防路径穿越）
  - `POST /api/notices/{id}/archive`（手动强制归档）
  - `POST /api/check` 支持参数（`source`/`type`/`from_page`/`to_page`/`searchValue`）用于手动抓取历史；**不支持日期过滤**（见决策 15）
- **配置**（遵循现有 `MNE_` 环境变量映射）：
  - `portal_page_limit`（默认 3）
  - `archive_enable`、`archive_dir`（默认 `data/archive`）
  - `archive_workers`（默认 2）、`archive_max_file_mb`（默认 50）、`archive_max_per_notice`（默认 50）、`archive_enqueue_limit_per_poll`（默认 50）
  - `archive_window_days`（`MNE_ARCHIVE_WINDOW_DAYS`，默认 90）
  - `archive_floor_date`（`MNE_ARCHIVE_FLOOR_DATE`，默认 `2026-08-31`）
  - `archive_total_limit_gb`（`MNE_ARCHIVE_TOTAL_LIMIT_GB`，默认 64）
  - `backfill_push`（`MNE_BACKFILL_PUSH`，默认 `false`）
- **目录结构**：

```
data/archive/<source_key>/<external_id>/
├── content.html      # 原始 HTML（保留原始链接）
├── content.txt       # 纯文本
├── meta.json         # 元数据 + 附件清单
└── files/            # 附件与内联图片
```

## 影响面

- core：**新增 `archive.py`**；改 `fetcher.py`、`engine.py`、`models.py`、`storage.py`、`sources.py`、`config.py`
- transport：`api.py`
- 配置：`config.example.toml`
- 文档：`docs/architecture.md`（新增归档模块/队列/数据流）
- 数据：删除旧库重建；新增 `assets` 表

## 风险与备选

- 全量 type 数据量大（type=4 时政 12806 条）：靠时间窗 + 页数上限 + 后台队列限速控制。
- 下载可能非常多：队列限速、单文件/单通知上限、64GB 总量 LRU。
- 附件版权与隐私：仅个人内网使用，不公开传播。
- 备选：正文只存纯文本。否决：会丢失附件与格式。

## 验证方式

- 单元：翻页解析 `page`；`fetch_detail` 解析 `notice_annext`；`ArchiveStore` 用 mock HTTP + 离线 fixture 验证落盘、文件名安全化、HTML 响应判失败；`evict_to_limit` 按 `last_access_at` 淘汰。
- 集成：`notice_id=358513` → 下载 `【0906更新-公示】附件5：理学院拟推荐名单.xlsx`（带 Cookie 200 + `content-disposition`）。
- 集成：自动窗口（cutoff）下旧通知不入队；手动 `POST /api/notices/{id}/archive` 可强制归档。
- 集成：手动抓取用 `from_page`/`to_page` 翻历史页；`searchValue=推免` 定向取相关通知（实测可用）。
- 集成：首轮回填与手动抓取**默认不触发 webhook**；`MNE_BACKFILL_PUSH=true` 时才推送。
- REST：`/content`、`/content.zip`、`/files` 正常返回；访问后 `last_access_at` 更新。

## 任务拆分

- [x] 修复认证边界 bug（CAS 有效但 comsys 失效时登录页 302 被当异常）
- [x] 统一 URL 拼接基准（移除硬编码 `base_url`）
- [x] `Notice.external_id` + 全量 type + 门户翻页
- [x] `fetch_detail`（`getNotice` → HTML + 附件/图片）并合并 `enrich_contents`
- [x] `core/archive.py`：`ArchiveStore` + 后台队列 + LRU 淘汰
- [x] `rss_max_items` 改为只约束 `write_rss`
- [x] engine 入队编排 + `Archiver` 协议
- [x] 回填标记（首轮持久化 / 手动请求）+ 推送抑制（`backfill_push`）
- [x] storage `assets` 表 + `last_access_at` 维护
- [x] REST：content / content.zip / files / 手动 archive / 手动 check（`from_page`/`to_page`/`searchValue`；防路径穿越）
- [x] 配置项 + `.env.example` / `config.example.toml`
- [x] 测试与文档（changelog、architecture、规范编号说明）
