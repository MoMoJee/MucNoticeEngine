# 0008 理学院 / 信息工程学院公开来源接入

- Plan: [0008](../plans/0008-lxy-xingong-sources.md)
- Type: feat
- Date: 2026-09-19

## Summary

新增理学院 3 个、信息工程学院 8 个公开来源（共 11 个）；公开源支持从
`onclick="opennews('…')"` 取链；正文选择器补齐微信公众号容器。

## Changes

- core/sources.py：新增 11 个公开来源——`lxy_xydt`、`lxy_rcpy`、`lxy_kxyj`、
  `xg_tzgg`、`xg_kyjx`、`xg_jwdt`、`xg_dthd`、`xg_xyxw`、`xg_yjszs`、`xg_bksjx`、`xg_zyrz`；
  `SOURCES` 21 → 32（公开 10 → 21），新分类 `lxy` / `xingong`。
- core/fetcher.py：新增 `_resolve_link`——`href` 缺失或为 `javascript:` 时，
  取 `onclick` 内首个引号字符串再做 `urljoin`；`ARTICLE_SELECTORS` 增加 `#js_content`。
- transport：无（`/api/sources` 自动包含新来源）。
- 配置：无。
- 文档：`README.md`、`docs/index.md`、`docs/guides/rest-api.md` 的来源数量；
  `docs/reference/portal-notice-types.md` 新增两站结构与 AOP 搜索接口调研；
  `AGENTS.md` 命令注释；`docs/plans/README.md` 登记 0008。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 46 passed
- `uv run muc-notice-engine sources` -> 共 32 个来源
- `uv run muc-notice-engine poll --source lxy_xydt,lxy_rcpy,lxy_kxyj,xg_tzgg,xg_kyjx,xg_jwdt,xg_dthd,xg_xyxw,xg_yjszs,xg_bksjx,xg_zyrz`
  -> 入库 94 条（其中 17 条在推送时间窗内），RSS 写入 94 条；抽查标题/日期/链接正确，
  onclick 条目解析出真实 URL（如 `https://xingong.muc.edu.cn/info/1037/6525.htm`）。

## Breaking changes

无。

## Follow-ups

AOP 智能搜索接口（免登录）调研结论已写入 `docs/reference/portal-notice-types.md`；
是否作为新的检索/回填接口接入待确认，设计挂在 [plans/0008](../plans/0008-lxy-xingong-sources.md) 阶段二。
