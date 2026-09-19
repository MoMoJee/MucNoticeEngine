# 0009 AOP 智能搜索接口（远程检索）

- Plan: [0009](../plans/0009-aop-search-api.md)
- Type: feat
- Date: 2026-09-19

## Summary

新增免登录的远端全文检索能力：`core/aop.py` + `GET /api/search`、`GET /api/search/sites`，
覆盖全校 34 个 VSB9 站点；附 CLI `search`。不写库，不改动现有轮询/推送/本地查询。

## Changes

- core/aop.py（新）：
  - 34 个站点目录（owner 快照，`AOP_SITES`）与 `resolve_site`（key/owner/host/名称）；
  - `build_query` 参数映射：`match`（all/any→AND/OR）、`scope`（title/content/all）、
    `order`（date/score）、`since`/`until`（custom 日期）；
  - `AopSearchClient.search`：分页（单页 100、扫描上限默认 200）、`//` 协议相对 URL 规范化、
    高亮标签剥离、`YYYY-MM-DD` 日期解析、按链接去重、`exclude` 本地过滤、失败降级为 `error`。
- transport/api.py：新增 `GET /api/search/sites`、`GET /api/search`；未知站点 404、
  非法参数 422；沿用 `api_token` 认证；引导页 `/` 增加可检索站点目录入口。
- cli.py：新增 `search` 子命令；不带 `--site` 时列出可检索站点。
- 配置：无（搜索主机为 `core/aop.py` 常量）。
- 数据/schema：无（不写库、不入 RSS、不触发 webhook）。
- 文档：新建 `docs/reference/aop-search.md`（协议/限制/站点 owner 目录）、
  `docs/guides/deployment.md`（生产机运维）；更新 `docs/guides/rest-api.md`、
  `README.md`、`docs/index.md`、`docs/architecture.md`、`AGENTS.md`。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 60 passed（新增 tests/test_aop.py 与 API 用例；引导页含新入口断言）
- `uv run muc-notice-engine search` -> 共 34 个可检索站点
- `uv run muc-notice-engine search --site xingong --keyword 推免 --match all --exclude 名单 --limit 5`
  -> 共 5 条（远端 26 条，扫描 9 条，结果被截断）；结果中无「名单」类条目
- `uv run muc-notice-engine search --site lxy --keyword 推免 --scope title --since 2026-09-01 --until 2026-09-30 --limit 3`
  -> 共 3 条，标题检索与日期范围生效
- 生产机（49.232.15.53，bundle 更新到 `31751af` 后重启）：
  - `/health` -> `source_count=32`；启动轮询后 `notice_count` 1371 → 1465（11 个新来源入库 94 条）
  - `/api/stats` -> 11 个新来源均有数据（lxy_* / xg_*）
  - `/api/search/sites` -> `count=34`；`/api/search?site=xingong&q=推免&match=all` -> 正常返回

## Breaking changes

无。

## Follow-ups

- 后续可把远程检索并入 `/api/notices?q=`（如 `remote=1`），`/api/search` 保持兼容。
- `/api/*` 尚未配置 `MNE_API_TOKEN`（SERVER_INDEX 记为中风险）。
- 生产机到 GitHub 偶发不通，本次用本地 bundle 增量更新，流程见 `docs/guides/deployment.md`。
