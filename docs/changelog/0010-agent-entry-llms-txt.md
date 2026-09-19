# 0010 Agent 入口：/llms.txt 与首页引导

- Plan: [0010](../plans/0010-agent-entry-llms-txt.md)
- Type: feat
- Date: 2026-09-19

## Summary

新增 `/llms.txt` 给 Agent / 自动化调用方指路（不复制文档、只指向），
首页 `/` 顶部显著提示「不了解规则时首次调用前必读」；`/llm.txt` 301 跳转兼容。

## Changes

- transport/llm_txt.py（新）：`llm_txt()` 入口索引，含「首次必读 / 按任务查 / 规则摘要 / 其他」，
  链接 rest-api、reference/aop-search、`/openapi.json`，动态带来源数与站点数。
- transport/api.py：
  - `GET /llms.txt` 返回纯文本（公开，不走 `api_token`）；`GET /llm.txt` 301 到 `/llms.txt`；
  - `/` 首页增加 Agent 提示块与 `/llms.txt` 链接。
- transport：无其他；core / 配置 / 数据：无。
- 文档：`docs/guides/rest-api.md`（接口表 + 认证例外）、`README.md`（接口表 + 引导语）；
  `docs/conventions/docs.md`（同步矩阵新增 `/llms.txt`、防过期检查清单、专节规则）、
  `AGENTS.md`（工作流与「改哪里」表）、`docs/index.md`（硬性规则第 3 条）。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 61 passed（新增 `/llms.txt`、`/llm.txt` 跳转、首页提示、
  配置 token 时 `/llms.txt` 仍公开）
- 生产机更新后 `curl -s https://muc-notice.unischedulersuper.cn/llms.txt` -> 200。

## Breaking changes

无。

## Follow-ups

接口/文档路径变化时，同步 `transport/llm_txt.py` 内的链接与一句话摘要。
