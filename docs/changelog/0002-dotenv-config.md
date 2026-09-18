# 0002 支持从 .env 读取配置

- Plan: [0002](../plans/0002-dotenv-config.md)
- Type: feat
- Date: 2026-09-18

## Summary

服务启动时自动读取当前目录（以及 config 同目录）的 `.env`，方便复用门户凭据，
且不覆盖真实环境变量。`.env` 已被 gitignore。

## Changes

- `config.py`：新增 `_load_dotenv`，`load_settings` 加载优先级变为
  默认值 < `config.toml` < `.env` < 真实环境变量。
- `.env.example`：更新说明（程序现在会解析 `.env`）。
- `.env`（本地，未提交）：写入门户账号密码用于复用。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 13 passed
- 仅依赖 `.env`（不内联环境变量）执行门户抓取，登录成功、抓到门户通知

## Breaking changes

无。

## Follow-ups

- 如需多环境配置，可支持 `MNE_CONFIG` 指定 config 路径（当前已支持 `--config`）。
