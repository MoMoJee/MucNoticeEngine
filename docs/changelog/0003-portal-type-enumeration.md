# 0003 枚举信息门户通知 type 并归类

- Plan: 无（分析型文档，非功能开发）
- Type: docs
- Date: 2026-09-18

## Summary

对门户 `getNoticeByPage` 的 `type` 参数从 1 到 80 逐类探测，找出全部有效分类并采样，
输出 CSV 和归类结论，作为后续接入 `type=11`、翻页抓取的依据。

## Changes

- `docs/reference/portal-notice-types.csv`：11 个有效 type 的汇总表（名称、归类、是否已接入、样本）。
- `docs/reference/portal-notice-types.md`：探测方法、归类与接入建议。
- `docs/index.md`：登记 reference 文档。

## Verification

- 探测 `type=1..80`，有效类型：`1,3,4,5,6,8,9,10,11,32,36`；其余返回空。
- 每个有效类型采样前 5 页（150 条），共 ~1650 条标题用于归类。
- 关键发现：`type=9` 与 `type=1` 完全重复；推免校内遴选/名额在 `type=6`，名单公示/细则在 `type=11`。

## Breaking changes

无。

## Follow-ups

- 接入 `type=11`（按关键词过滤，避免招标采购噪声）。
- 门户来源支持翻页抓取（当前仅第 1 页 20 条）。
