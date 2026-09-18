# 部署与运维（生产机）

生产环境由开发者维护，整机状态以服务器上的 `/home/momojee/SERVER_INDEX.md` 为准；
本文只记录与本项目相关的部分，**不放任何密钥**（门户账号在服务器 `.env` 里）。

| 项 | 值 |
| --- | --- |
| 服务器 | 腾讯云 `49.232.15.53`（内网 `10.2.0.9`），SSH 用户 `momojee`（密钥登录） |
| 项目路径 | `/home/momojee/MucNoticeEngine/`（GitHub: `MoMoJee/MucNoticeEngine`，分支 `master`） |
| 运行方式 | `./start.sh`（nohup 后台）/ `./stop.sh`；**暂无 systemd 自启** |
| 监听 | `127.0.0.1:8085`，nginx 反代 → <https://muc-notice.unischedulersuper.cn> |
| 更新 | `./update.sh`（`git pull` + `uv sync` + 重启；服务器可直连 GitHub） |
| 日志 | `/home/momojee/MucNoticeEngine/logs/engine.log` |
| 数据 | `data/muc_notice.db`、`data/archive/`（`MNE_ARCHIVE_TOTAL_LIMIT_GB=8`，LRU 淘汰） |
| 配置 | 服务器 `.env`（`MUC_USERNAME`/`MUC_PASSWORD` 等，勿提交、勿外发） |
| 入口 | RSS `/api/rss`、健康检查 `/health`；API 当前**未设** `MNE_API_TOKEN` |

## 发布流程

1. 本地：`uv run ruff check .` + `uv run pytest`，提交并推送 `master`。
2. 更新生产机：

   ```bash
   ssh momojee@49.232.15.53
   cd ~/MucNoticeEngine && ./update.sh
   ```

3. 验证：

   ```bash
   curl -s https://muc-notice.unischedulersuper.cn/health
   curl -s 'https://muc-notice.unischedulersuper.cn/api/search/sites' | head -c 300
   tail -n 50 ~/MucNoticeEngine/logs/engine.log
   ```

## Git 更新（GitHub 不通时用 bundle 增量）

生产机到 GitHub 偶发失败（`Failure when receiving data from the peer`，实测 2026-09-19）。
此时在本地打包从服务器当前提交到 `master` 的增量，走 SCP：

```bash
# 本地（<server-head> 为服务器 git log 里的提交）
git bundle create /tmp/muc_update.bundle <server-head>..master
scp /tmp/muc_update.bundle momojee@49.232.15.53:~/SCP_TEMP/

# 服务器
cd ~/MucNoticeEngine
git pull ~/SCP_TEMP/muc_update.bundle master
~/.local/bin/uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
git checkout -- uv.lock
./stop.sh && ./start.sh
```

## 常用命令

```bash
cd ~/MucNoticeEngine
./stop.sh && ./start.sh          # 手动重启
tail -f logs/engine.log          # 看日志
uv run muc-notice-engine sources # 来源清单
```

## 风险与待办（摘自 SERVER_INDEX）

- `/api/subscribers`、`/api/check` 等写接口无认证，公网可写；建议设 `MNE_API_TOKEN`
  （注意 nginx/feeder 也要带 `Authorization`）或限制非 GET 方法。
- 靠 `start.sh` nohup 运行，重启后不自启；建议改 systemd。
- 无日志轮转；`engine.log` 持续增长，建议 logrotate。
