# 0006 保留期改为按入库时间且默认关闭

- Plan: [0006](../plans/0006-retention-first-seen.md)
- Type: fix
- Date: 2026-09-19

## Summary

数据库保留期 `notice_retention_days` 默认从 180 改为 **0（不清理）**；启用时改按
**`first_seen_at`（入库时间）** 清理，手动回填的历史不再被按发布时间误删。顺带补上此前
缺失的 `MNE_NOTICE_RETENTION_DAYS` 与 `MNE_PUSH_MAX_AGE_DAYS` 环境变量映射。

## Changes

- core/config：`notice_retention_days` 默认 `0`；`_ENV_MAP` 新增两个缺失映射
  （此前文档提过 `MNE_NOTICE_RETENTION_DAYS`，但实际不可用）。
- core/storage：`purge_older_than_days` 的 WHERE 由 `published_at` 改为 `first_seen_at`。
- 配置：`config.example.toml` 改为 `0` 并注明语义；`.env.example` 增加两个变量示例。
- 文档：`docs/guides/rest-api.md` 回填注意事项改为「默认关闭；开启后按入库时间」。
- 测试：`test_purge_uses_first_seen_at`（回填场景存活、超期入库被清理、0 不清理）、
  默认值与 env 映射用例。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 42 passed
- 部署机（10.60.43.8:8085）实测：
  - 回填 `type=11` 5–6 页（`searchValue=推免`）新增 21 条 2021/2022 年历史，库 801→822；
  - 重启触发 `_safe_poll()` 清理路径后：库仍为 822，`published_at < 2026-03-23` 的 133 条
    全部存活（旧行为会按发布时间删掉这批）；2021/2022 年记录仍在；
  - `load_settings()` 实测 `retention=0, push_max_age=30`，`.env` 未显式配置（使用新默认值）。

## Breaking changes

- 行为变化（仅影响显式设置保留期的部署）：
  - 默认不再按时间清理，数据库会持续增长；需要清理可设 `MNE_NOTICE_RETENTION_DAYS>0`。
  - 清理基准由 `published_at` 改为 `first_seen_at`，回填条目按入库时刻计算。
- 无 schema 变更，无需清库。

## Follow-ups

- 若 DB 长期增长明显，可评估按行数上限或归档后删除原始记录（暂不做）。
