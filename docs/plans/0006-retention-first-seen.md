# 0006 保留期改为按入库时间且默认关闭

- Status: done（2026-09-19 交付，见 [changelog/0006](../changelog/0006-retention-first-seen.md)）
- Owner: MoMoJee
- Created: 2026-09-19
- Related: [0005-search-fields-and-window-semantics.md](0005-search-fields-and-window-semantics.md)、`core/storage.py`、`config.py`、`docs/guides/rest-api.md`

## 背景与目标

`notice_retention_days`（默认 180）是初始化提交自带的工程默认值，不是需求：它每轮抓取后按
`published_at` 删除数据库记录，把手动回填的历史也清掉了（部署库实测 719→689，最早时间回到
2026-03-26）。开发者只要求过**归档文件的大小上限**（`archive_total_limit_gb=64`），
数据库这边未要求过时间限制。

决策（2026-09-19）：

1. `notice_retention_days` **默认改为 `0`（不清理）**；
2. 启用时改按 **`first_seen_at`（入库时间）** 计算，回填的历史从入库时刻起算 N 天，
   不会被按发布时间误删；
3. 补充缺失的环境变量映射：`MNE_NOTICE_RETENTION_DAYS` 与 `MNE_PUSH_MAX_AGE_DAYS`
   （此前文档提过前者但 `_ENV_MAP` 里没有，实际无法通过环境变量配置）。

## 方案

- `config.py`
  - `notice_retention_days: int = 0`，注释改为「按 `first_seen_at` 清理；0（默认）不清理」。
  - `_ENV_MAP` 增加 `MNE_NOTICE_RETENTION_DAYS`、`MNE_PUSH_MAX_AGE_DAYS`。
- `storage.purge_older_than_days`：`DELETE ... WHERE first_seen_at < ?`；`days<=0` 仍直接返回 0。
- `engine._safe_poll` 调用方式不变（默认 0 时是廉价空操作）。
- 示例文件：`config.example.toml` 改为 `0`；`.env.example` 增加两个变量示例。
- 文档：`docs/guides/rest-api.md` 的回填注意事项改为「默认关闭；开启后按入库时间」。
- 不做 schema 变更，不需要清库。

备选与否决：

- 维持 180 但文档提醒（否决：开发者要求默认只保留大小限制）。
- 给回填条目豁免（否决：需要额外标记字段，按入库时间已能覆盖场景）。

## 影响面

- core：`storage.py`（`_purge`、docstring）
- transport：无
- 配置：`config.py` + `config.example.toml` + `.env.example`
- 数据/schema：无
- 文档（按 [同步矩阵](../conventions/docs.md#代码变更--文档同步矩阵)）：
  `docs/guides/rest-api.md`、changelog/plan

## 风险与备选

- 默认关闭后数据库会持续增长；当前量级（几百到几万条、每条几 KB）可接受，
  需要时可设 `MNE_NOTICE_RETENTION_DAYS>0`。
- 行为变化仅影响「设置了保留期」的部署；未设置的用户由 180 天删除变为不删除。

## 验证方式

- 单元：入库时间新、发布时间旧的记录**不**被清理（回填场景）；入库时间超期后被清理；
  `days<=0` 返回 0；`Settings().notice_retention_days == 0`。
- 单元：`MNE_NOTICE_RETENTION_DAYS=365` 环境变量能覆盖默认值。
- 部署机：回填一页 2021 年的历史后跑一轮普通抓取，记录仍在（默认不再清理）；
  `/health` 正常。
- 回归：`ruff check` 通过，全部测试通过。

## 任务拆分

- [x] `config.py`：默认 0 + 两个环境变量映射
- [x] `storage.purge_older_than_days` 改按 `first_seen_at`
- [x] 示例文件与 `docs/guides/rest-api.md` 更新
- [x] 单元测试（purge 语义、默认值、env 覆盖）
- [x] changelog 0006 + 计划/README 状态
- [x] 推送 GitHub；更新 10.60.43.8 并验证回填存活
