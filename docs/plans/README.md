# 开发计划

**规则：功能开发前先在这里建计划，计划获批（`Status: approved`）后再写代码。**
规范见 [../conventions/docs.md](../conventions/docs.md)。

## 命名

`NNNN-kebab-topic.md`：四位递增编号，不复用，与 `docs/changelog/` 同编号对应。

## 已有计划

| 编号 | 标题 | 状态 |
| --- | --- | --- |
| [0001](0001-bootstrap-engine.md) | 从 AstrBot 插件剥离独立通知引擎 | done |

## 模板

新建文件时复制以下内容；删除注释后填写。

```markdown
# NNNN 标题

- Status: draft
- Owner: <你的名字>
- Created: YYYY-MM-DD
- Related: <相关 issue / 文件>

## 背景与目标

为什么做、要解决什么问题、明确的验收标准。

## 方案

整体思路与关键取舍。列出会新增/修改的模块。

## 影响面

- core：
- transport：
- 配置：
- 数据/schema：

## 风险与备选

有哪些不确定性，为什么不选其它方案。

## 验证方式

实现后准备用什么命令/测试证明它工作。

## 任务拆分

- [ ] 任务 1
- [ ] 任务 2
```
