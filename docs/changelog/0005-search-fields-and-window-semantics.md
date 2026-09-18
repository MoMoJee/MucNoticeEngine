# 0005 查询搜索字段、时间窗语义与 API 文档体系

- Plan: [0005](../plans/0005-search-fields-and-window-semantics.md)
- Type: feat
- Date: 2026-09-19

## Summary

`q` 从只匹配标题扩展为匹配**标题 / 摘要 / 正文预览**（转义 LIKE 通配符）；确认归档时间窗
`cutoff = max(floor, now - window)` 取**较晚者**并补显式测试；新增 `GET /` 引导页指向 `/docs`；
新增统一使用文档 `docs/guides/rest-api.md`，并建立「改接口必须同步文档」的机制。

## Changes

- core/storage.py：`q` 改为 `title/summary/content` 三字段 `LIKE ... ESCAPE '\'`，
  输入中的 `\` `%` `_` 按字面转义。
- core/engine.py：`archive_cutoff(now=None)` 支持注入当前时间（仅便于测试，行为不变）。
- transport/api.py：新增 `GET /` 引导页（链接 `/docs`、`/redoc`、`/health` 等）；
  `q` 参数描述改为「标题/摘要/正文预览」。
- 配置：无。
- 文档：
  - 新增 `docs/guides/rest-api.md`：接口速查、认证、查询/归档/回填语义、历史回填步骤、运维小抄。
  - `README.md`：接口表补齐（content/zip/files/archive/check 参数），来源 21，`.env` 说明，链接新文档。
  - `AGENTS.md`：「改哪里」表加「必须同步的文档」列；工作流加入文档同步要求。
  - `docs/conventions/docs.md`：新增「代码变更 → 文档同步矩阵」与防过期清单条目。
  - `docs/index.md`：登记 guides 文档与快速索引；`docs/changelog/README.md`、`docs/plans/README.md` 模板加入文档必填项。
  - `docs/architecture.md`：时间窗「取较晚者」措辞 + 指向使用文档。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 39 passed（新增 q 三字段/转义、cutoff 2030 场景、根路由用例）
- 部署机（10.60.43.8:8085，719 条库）实测：
  - `GET /` -> 200 且包含 `/docs`；`GET /docs` -> 200
  - `GET /api/notices?limit=500&q=智慧校园建设` -> 1
  - `GET /api/notices?limit=500&q=网络强国` -> 1
  - `GET /api/notices?limit=500&q=推免` -> 21
  - `GET /api/notices?limit=500&q=校长杯` -> 33（原仅标题 20）

## Breaking changes

无。`q` 是语义扩展（命中变多），参数与响应结构不变；无需迁移。

## Follow-ups

- 单表 >5 万行或查询 p95 >100ms 时评估 FTS5 全文索引。
- 部署机访问 GitHub 仍不通，`update.sh` 需修好代理或继续用 bundle。
- **保留期与回填冲突（待决策）**：`notice_retention_days`（默认 180 天）按 `published_at`
  清理，实测把手动回填的历史删除了（部署库 719→689，最早时间回到 2026-03-26）。
  可选方案：改为按 `first_seen_at` 清理、给回填条目豁免、或文档建议设 `0`（本次已在
  `docs/guides/rest-api.md` 记录注意事项，未改行为）。
