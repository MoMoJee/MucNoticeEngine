# 0004 门户翻页、全量 type、正文与附件归档

- Plan: [0004-portal-pagination-attachments](../plans/0004-portal-pagination-attachments.md)
- Type: feature
- Date: 2026-09-18

## Summary

门户从「4 个 type 各抓第 1 页 20 条」升级为**全部 11 个有效 type、支持翻页**；新增
`fetch_detail` 统一抓正文（门户 `getNotice` / 公开源文章页），新增 `core/archive.py`
把正文、附件与内联图片落盘为文件树并记入 `assets` 表；引擎只入队不等待，后台 worker
下载，超限按 `last_access_at` 升序淘汰；首轮回填与手动回填默认不推送 webhook。
同时修复 CAS 302 认证边界与 `grs_yjszs` 链接 404。

## Changes

- `core/auth.py`：CAS 会话有效时登录页 302 改为跟随跳转并校验（原直接报错）；收紧
  `_verify_login`；新增 `NOTICE_DETAIL_URL` / `NOTICE_DOWNLOAD_URL` 常量。
- `core/models.py`：`Notice.external_id`（门户=`notice_id`，公开源=URL slug）；
  新增 `Attachment`（`kind ∈ {file,image}`）与 `NoticeDetail`。
- `core/sources.py`：来源 14 → 21（4 个门户来源扩展为全部 11 个 type）；移除
  `base_url`，链接与 Referer 统一以当前页面 URL 为准（修复 `grs_yjszs` 404）。
- `core/fetcher.py`：门户翻页（受 `portal_page_limit` 约束，读 `page.totalCounts`）；
  `fetch_portal_type(type_id, from_page, to_page, search_value)` 用于手动历史抓取；
  `fetch_detail()` 取代 `enrich_contents`；公开源只抓正文，不下载图片/附件。
- `core/archive.py`（新增）：`ArchiveStore` 落盘 `content.html` / `content.txt` /
  `meta.json` / `files/`（原子写、文件名安全化、单文件上限、sha1），LRU 淘汰（节流
  60s）；`ArchiveQueue` 后台队列，实现 `Archiver` 协议。
- `core/engine.py`：`Archiver` 协议；`poll_once` 只入队；归档时间窗
  `cutoff = max(archive_floor_date, now - archive_window_days)`；首轮持久化
  `initial_poll_done`，回填默认不推送（`backfill_push` 可开）；新增
  `manual_fetch_portal()`。
- `core/storage.py`：`notices.external_id`；新增 `assets`（kind/文件/大小/sha1/首次
  下载/最近访问）与 `meta` 表；`fill_content_preview`、`touch_assets`、
  `replace_assets`、淘汰辅助方法。
- `config.py`：新增 `portal_page_limit`、`archive_*`、`backfill_push`（含 `MNE_`
  映射与 `.env.example` / `config.example.toml`）。
- `transport/api.py`：新增 `GET /api/notices/{id}/content`、`/content.zip`、
  `/files`（清单与单文件下载，防路径穿越）、`POST /api/notices/{id}/archive`；
  `POST /api/check` 支持 `type/from_page/to_page/searchValue`；详情与文件接口更新
  `last_access_at`。
- `cli.py`：`run` 按 `archive_enable` 启动/停止归档队列。
- 测试：新增 `test_auth` / `test_fetcher` / `test_archive` / `test_engine`，扩展
  `test_api`（35 passed）。

## Verification

- `uv run ruff check .` 通过；`uv run pytest -q` 35 passed。
- 真实门户（2026-09-18）：`type=11` 翻 3 页共 60 条；`searchValue=推免` 抓到 2021 年历史；
  `notice_id=358513` 正文 + 附件 `xlsx`（27391 字节）落盘成功。
- 端到端：首轮入库 20 条、推送 0（回填抑制）、归档 1 条（4 个文件 / 无正文的条目记 skipped）。
- 抽查 `GET /health`：`source_count=21`，`archive_enabled=true`。

## Breaking changes

- **需删除旧数据库**：`notices` 新增 `external_id`，SQLite 无迁移框架，直接
  `Remove-Item data/muc_notice.db` 后重启（旧库仅测试数据）。
- 来源数量 14 → 21，`/api/sources` 与订阅 `source_keys` 可见新 key。
- 旧 `my_*` 四个门户 key 保留，新增 `my_xhw/my_mzyw/my_sztt/my_xyxw/my_jyxx/my_gsgg/my_hdbd`。

## Follow-ups

- 公开源正文中的内联图片 v1 不下载（按决策 17，后续再议）。
- `type=11` 招标采购噪声与 `type=1/9` 重复内容未做过滤（按决策 6，全部保留）。
