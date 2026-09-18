# 架构

## 一句话

`core` 负责「抓取 -> 规范化 -> 去重 -> 存储 -> 发布事件」；`transport` 负责「怎么把事件送出去 / 怎么查询」。两者只通过一个协议耦合。

## 分层与硬性边界

```
        transport (api.py / publishers.py)
                 │  实现 Publisher 协议，调用 core
                 ▼
        core (engine.py 为调度中枢)
                 │
   auth / fetcher / storage / sources / parsers / models
```

**硬性规则**

- `core/*` **禁止** import `transport`，也禁止 import FastAPI/uvicorn 等 Web 框架。
- `transport/*` 可以 import `core`。
- 新增传输方式（MQ、SSE、消息平台……）时，不要改 `core`，只需实现：

```python
class MyPublisher:
    async def publish(self, notices: list[Notice]) -> None:
        ...
```

## 数据流

1. `NoticeEngine.run_forever()` 按 `poll_interval_minutes` 触发 `poll_once()`。
2. `MucRssService.fetch_notices()` 并发抓公开源（信号量限流），门户源串行 + 会话失效自动重登。
3. 结果规范化为 `Notice`，`storage.upsert_notices()` 用 `INSERT OR IGNORE` 判定新条目（去重）。
4. 新条目经 `push_max_age_days` 过滤后，交给所有 `Publisher`。
5. `WebhookPublisher` 按订阅者的 `source_keys` 过滤后 POST，支持 HMAC-SHA256 签名。

REST 不直接参与推送：查询走 `storage`，手动触发走 `engine.poll_once()`。

## 扩展点

| 想扩展 | 做法 |
| --- | --- |
| 新来源 | 在 `core/sources.py` 加一条；API 源用 `selector="api:..."` + `requires_auth` |
| 新推送目标 | 实现 `Publisher`，在 `cli.cmd_run` 里 `engine.add_publisher(...)` |
| 新查询维度 | `storage.query` 加条件 + `transport/api.py` 暴露参数 |
| 替换存储 | 保持 `NoticeStore` 的 async 方法签名即可（`engine` 只依赖这些方法） |

## 已知设计取舍

- **去重靠 `Notice.id = sha1(source_key|link)`**：链接变了会重新推送；门户通知用 `notice_id`，优于链接。
- **门户登录态**：CAS 票据 + comsys 会话会在两轮之间过期，`fetcher` 检测到 `error_comsys_session_invalid` 会原地重登重试。
- **加密降级**：`gmssl` 缺失或加密异常时 `auth._sm2_encrypt` 会退回明文密码并记 warning（兼容优先，非安全最优）。
- **公开源选择器写死**：学校改版会导致 `选择器未命中` 日志，需要更新 `sources.py`。
- **matplotlib 为可选依赖**：`rendering` 与 `/api/card.png` 在未安装时返回 501，不影响主流程。
