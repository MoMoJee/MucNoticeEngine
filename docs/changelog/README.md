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
