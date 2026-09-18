# 0007 RSS 响应补充 charset=utf-8

- Plan: 无（独立修复）
- Type: fix
- Date: 2026-09-19

## Summary

`/api/rss` 返回的 `Content-Type` 由 `application/rss+xml` 改为
`application/rss+xml; charset=utf-8`。文件本身一直是合法 UTF-8（含 XML 声明），
但不带 charset 时，部分浏览器/代理会按本地代码页（GBK）猜测导致显示乱码；
Feeder 因解析 XML 声明不受影响。

## Changes

- transport/api：`/api/rss` 的 `FileResponse` 显式声明 `charset=utf-8`。
- 文档：无。
- 测试：`test_rss_endpoint_declares_utf8_charset`（断言响应头 charset 与中文正文可读）。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 43 passed
- 部署机（10.60.43.8:8085，修复前）`curl -D - /api/rss` 实测：响应头为
  `Content-Type: application/rss+xml`，响应体严格 UTF-8 解码正常，确认乱码来自
  缺少 charset 的客户端猜测。
- 修复后响应头由 `test_rss_endpoint_declares_utf8_charset` 覆盖，断言
  `application/rss+xml; charset=utf-8` 且中文正文可读。
- 部署机（10.60.43.8）GitHub 不通，用增量 bundle 更新到 `b4f5c7e` 并
  `stop.sh`/`start.sh` 重启；`curl -D - /api/rss` 实测响应头为
  `application/rss+xml; charset=utf-8`，正文经 `iconv` UTF-8 校验通过，
  标题显示正常。

## Breaking changes

无。

## Follow-ups

无。
