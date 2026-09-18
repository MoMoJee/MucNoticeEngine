# 0002 支持从 .env 读取配置

- Status: done
- Owner: MoMoJee
- Created: 2026-09-18
- Related: `config.py`、`.env.example`

## 背景与目标

门户账号密码在测试时通过内联环境变量传入，不方便复用。允许把凭据放进已被 gitignore 的
`.env`，服务启动时自动读取，避免每次手动设置或写进可能被提交的文件。

验收标准：

1. 当前目录存在 `.env` 时，`MUC_USERNAME` / `MUC_PASSWORD` 等被自动加载。
2. `.env` 不覆盖真实环境变量。
3. `.env` 不会被提交。

## 方案

在 `config.load_settings()` 中，读取 `.env`（当前目录，以及 config 文件所在目录），
仅写入 `os.environ` 中尚不存在的键。优先级：默认值 < `config.toml` < `.env` < 真实环境变量。

不引入 `python-dotenv` 依赖，用约 10 行解析即可，避免为一个简单格式加依赖。

## 影响面

- core：无。
- transport：无。
- 配置：`config.py` 新增 `_load_dotenv`，`load_settings` 调用；`.env.example` 说明更新。
- 数据/schema：无。

## 风险与备选

- 风险：`.env` 含明文密码。缓解：已在 `.gitignore`；文档警告不要提交。
- 备选：用 `python-dotenv`。否决：格式简单，无需额外依赖。

## 验证方式

```bash
# 只依赖 .env，不内联任何环境变量
uv run muc-notice-engine poll --source my_bgtz
uv run ruff check .
uv run pytest
```

## 任务拆分

- [x] config.py 支持 .env
- [x] 同步 .env.example 说明
- [x] 用门户登录验证 .env 生效
