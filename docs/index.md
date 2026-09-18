# 文档索引

本文件是**文档唯一入口**。新增任何文档都必须在下面登记，否则视为过期内容。

## 这个项目是什么

`MucNoticeEngine`：中央民族大学多站点通知的**聚合 / 规范化 / 去重 / 存储**引擎，
对外只提供 REST API 与 webhook 推送。它是一个**独立常驻服务**，不是聊天机器人插件。

数据来源与解析逻辑移植自 `reference/astrbot_plugin_MUC_Notices/`（原始 AstrBot 插件），
但已移除全部 AstrBot 依赖。

## 文档地图

| 文档 | 内容 | 何时需要更新 |
| --- | --- | --- |
| [index.md](index.md) | 文档入口、目录结构、阅读顺序 | 新增/删除文档时 |
| [architecture.md](architecture.md) | 模块边界、数据流、扩展点 | 模块边界或数据流变化时 |
| [conventions/docs.md](conventions/docs.md) | 文档命名、计划/变更日志写作规范、防过期规则 | 规范本身变化时 |
| [conventions/git.md](conventions/git.md) | 提交流程、commit message 规范（参照首次提交） | 流程变化时 |
| [plans/](plans/README.md) | 开发计划（先计划后实现） | 每个功能开发前 |
| [changelog/](changelog/README.md) | 已交付变更说明 | 每次交付时 |

阅读顺序建议：`README.md` -> `docs/index.md` -> `docs/architecture.md` -> 规范。

## 代码结构

```
src/muc_notice_engine/
├── config.py            # Settings 数据类 + config.toml/环境变量加载
├── cli.py               # argparse 入口：run / poll / sources / rss
├── core/                # 核心引擎（禁止 import transport / 第三方 Web 框架）
│   ├── models.py        # Notice / SourceConfig
│   ├── sources.py       # 14 个来源配置（新增来源改这里）
│   ├── parsers.py       # HTML -> 标题 解析函数
│   ├── auth.py          # SM2 登录 + Cookie 持久化
│   ├── fetcher.py       # 抓取 HTML/API，生成 Notice 与 RSS
│   ├── storage.py       # SQLite 存储 + 去重
│   ├── engine.py        # 轮询调度 + Publisher 协议
│   └── rendering.py     # 可选：matplotlib 卡片图
└── transport/           # 传输层（可 import core，反向禁止）
    ├── api.py           # FastAPI 路由
    └── publishers.py    # WebhookPublisher + 订阅者存储

reference/astrbot_plugin_MUC_Notices/   # 只读参考副本，不要修改
docs/                                   # 本目录
tests/                                  # pytest
```

## 快速索引：我要做什么

| 需求 | 去处 |
| --- | --- |
| 新增/修改一个通知来源 | `core/sources.py`，然后拆解析函数到 `core/parsers.py` |
| 改抓取规则/日期解析 | `core/fetcher.py` |
| 改去重、查询、存储字段 | `core/storage.py`（改 schema 需同步 changelog 的迁移说明） |
| 改轮询或新增事件消费者 | `core/engine.py`（实现 `Publisher` 协议） |
| 加 REST 接口 | `transport/api.py` |
| 改 webhook 负载/签名 | `transport/publishers.py` |
| 改配置项 | `config.py` + `config.example.toml` + `_conf` 文档同步 |

## 保持文档不过期（硬性）

1. **先计划后实现**：功能开发前先在 `docs/plans/` 建计划，见 [plans/README.md](plans/README.md)。
2. **交付必写变更日志**：每次交付在 `docs/changelog/` 建条目，见 [changelog/README.md](changelog/README.md)。
3. **只写可验证内容**：命令必须能直接复制运行；与代码冲突时以代码/`config.example.toml` 为准。
4. **不重复叙述**：能从代码或配置看出的，不搬到文档里；文档只解释「为什么」和「怎么用」。
5. **改边界同步 architecture**：`core`/`transport` 边界变化必须更新 `architecture.md`。
