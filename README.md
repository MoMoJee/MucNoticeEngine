# MucNoticeEngine

中央民族大学多站点通知的**聚合 / 去重 / 存储引擎**。独立常驻服务，对外只提供
REST API 与 webhook 推送，不依赖任何聊天机器人框架。

抓取逻辑移植自 [astrbot_plugin_MUC_Notices](https://github.com/KardeniaPoyu/astrbot_plugin_MUC_Notices)，
已移除全部 AstrBot 依赖，并重写命令解析、轮询与推送机制。

## 特性

- 21 个来源：10 个公开站点 + 信息门户全部 11 个有效栏目（type）。
- 门户 SM2 国密加密登录 + Cookie 持久化 + 会话失效自动重登；支持翻页与历史回填。
- SQLite 存储与去重（`INSERT OR IGNORE`，`Notice.id` 为主键）；关键词匹配标题/摘要/正文预览。
- 正文与附件归档：门户抓 `getNotice` 下载附件与内联图，公开源抓文章正文；
  落盘 `data/archive/<source_key>/<external_id>/`，超限按最近访问时间淘汰。
- 定时轮询；新通知通过 webhook 推送，支持 HMAC-SHA256 签名与来源过滤；回填默认不推送。
- REST API 查询/搜索/归档，Swagger UI 在 `/docs`。
- 可选：matplotlib 生成通知卡片图。

## 快速开始

需要 Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra dev
cp config.example.toml config.toml      # 按需修改
cp .env.example .env                    # 凭证放这里（优先级高于 config.toml）

uv run muc-notice-engine sources        # 查看来源
uv run muc-notice-engine poll           # 抓取一轮并打印新通知
uv run muc-notice-engine run            # 启动服务（默认 http://127.0.0.1:8080）
```

门户通知需在 `config.toml` 或 `.env` 填 `muc_username` / `muc_password`
（`MUC_USERNAME` / `MUC_PASSWORD`）；不填则只抓公开站点。

## REST API

启动后浏览器打开 **`/`** 有引导页，**`/docs`** 是 Swagger UI。
完整参数、语义与历史回填步骤见 **[docs/guides/rest-api.md](docs/guides/rest-api.md)**。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 引导页（链接到 `/docs`） |
| GET | `/health` | 健康检查 + 归档队列（始终公开） |
| GET | `/api/sources` | 来源列表 |
| GET | `/api/notices` | 查询通知：`source` `category` `since` `q` `limit` `offset` |
| GET | `/api/notices/{id}` | 单条通知 |
| GET | `/api/notices/{id}/content` | 正文 HTML（归档原文或预览） |
| GET | `/api/notices/{id}/content.zip` | 正文 + 附件打包 |
| GET | `/api/notices/{id}/files` | 落盘文件清单 / 单文件下载 |
| POST | `/api/notices/{id}/archive` | 强制归档一条（绕过时间窗） |
| GET | `/api/stats` | 按来源统计 |
| POST | `/api/check` | 立即抓取一轮；带 `type` 时按门户历史回填 |
| GET | `/api/card.png` | 渲染最近通知卡片（需 `[render]`） |
| GET | `/api/rss` | 返回生成的 RSS 文件 |
| GET/POST/DELETE | `/api/subscribers` | webhook 订阅管理 |

设置 `api_token` 后，除 `/`、`/health`、`/docs` 等文档页外都需要
`Authorization: Bearer <token>`。

### Webhook 负载

```json
{
  "event": "notices.new",
  "count": 2,
  "generated_at": "2026-09-18T10:00:00+08:00",
  "notices": [ { "id": "...", "title": "...", "link": "...", "source_key": "..." } ]
}
```

配置 `secret` 后附带 `X-MUC-Signature: sha256=<hmac>`。

## 文档

- 文档入口：[docs/index.md](docs/index.md)
- 接口参考与历史回填：[docs/guides/rest-api.md](docs/guides/rest-api.md)
- 架构与边界：[docs/architecture.md](docs/architecture.md)
- 开发规范：[docs/conventions/](docs/conventions/docs.md)
- 计划 / 变更日志：[docs/plans/](docs/plans/README.md) · [docs/changelog/](docs/changelog/README.md)

## 开发

```bash
uv run ruff check .
uv run pytest
```

提交前请先阅读 [docs/conventions/git.md](docs/conventions/git.md)。

## License

MIT
