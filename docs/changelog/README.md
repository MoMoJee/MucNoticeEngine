# 变更日志

每次交付写一条，位置 `NNNN-kebab-topic.md`，编号与 `docs/plans/` 对应。
规范见 [../conventions/docs.md](../conventions/docs.md)。

## 命名

`NNNN-kebab-topic.md`：与触发它的计划同编号；无对应计划的独立修复也用下一个递增编号。

## 已有条目

| 编号 | 标题 | 类型 |
| --- | --- | --- |
| [0001](0001-bootstrap-engine.md) | 初始化独立通知引擎与 REST 服务 | feat |
| [0002](0002-dotenv-config.md) | 支持从 .env 读取配置 | feat |
| [0003](0003-portal-type-enumeration.md) | 枚举信息门户通知 type 并归类 | docs |
| [0004](0004-portal-pagination-attachments.md) | 门户翻页、补齐 type、正文与附件落盘 | feature |
| [0005](0005-search-fields-and-window-semantics.md) | q 搜索字段扩展、归档时间窗语义与 API 文档体系 | feat |
| [0006](0006-retention-first-seen.md) | 保留期改为按入库时间且默认关闭 | fix |
| [0007](0007-rss-utf8-charset.md) | RSS 响应补充 charset=utf-8 | fix |
| [0008](0008-lxy-xingong-sources.md) | 理学院 / 信息工程学院公开来源接入 | feat |
| [0009](0009-aop-search-api.md) | AOP 智能搜索接口（远程检索） | feat |
| [0010](0010-agent-entry-llms-txt.md) | Agent 入口：/llms.txt 与首页引导 | feat |

## 模板

```markdown
# NNNN 标题

- Plan: [NNNN](../plans/NNNN-kebab-topic.md)
- Type: feat | fix | refactor | docs | chore
- Date: YYYY-MM-DD

## Summary

一句话说明这次交付解决了什么。

## Changes

- core/<module>：
- transport/<module>：
- 配置：
- 文档（README / docs/guides/…，无则写「无」）：

## Verification

实际执行过的命令与结果，例如：
- `uv run pytest` -> 11 passed
- `uv run muc-notice-engine poll --source muc_tzgg` -> 抓到 N 条

## Breaking changes

无 / 说明迁移方式。

## Follow-ups

遗留问题与建议的下一步。
```
