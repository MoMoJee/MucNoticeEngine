# 提交流程与 Commit 规范

## 开发流程（先计划 -> 实现 -> 说明）

1. **计划**：在 `docs/plans/` 新建 `NNNN-kebab-topic.md`，状态置 `approved`。
2. **实现**：代码 + 测试；改边界时同步 `docs/architecture.md`。
3. **说明**：在 `docs/changelog/` 写同编号文件，记录变更与验证。
4. **提交**：按下面格式，body 里引用计划与变更日志。

一个提交只做一件逻辑上的事。计划文档可以与实现同一次提交，也可以单独先提交。

## 提交与推送权限（重要）

- **允许提交**：开发期间，Agent 在完成一项工作后、或大型任务到达开发者指定的阶段点时，
  可以自主执行 `git commit`，无需每次单独确认。
- **禁止推送**：未经开发者**显式要求**，不得执行 `git push`，不得创建远程分支、PR 或打标签。
- 提交前仍须满足下面的检查清单；提交信息必须按本规范编写。

## Commit message 格式

```
<type>(<scope>): <subject>

<body：做了什么、为什么，必要时分点>

Plan: docs/plans/NNNN-kebab-topic.md
Changelog: docs/changelog/NNNN-kebab-topic.md
```

- `type`：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `build` / `ci`
- `scope`：可选，用模块名，如 `core/auth`、`core/storage`、`transport/api`、`docs`
- `subject`：中文，祈使句，不超过 50 字，结尾不加句号
- 破坏性变更：`type(scope)!: subject`，并在 body 写明迁移方式

### 首个提交（规范基准）

仓库第一次提交是本规范的参考样例：

```
feat: 初始化 MucNoticeEngine 核心引擎与 REST 服务

从 astrbot_plugin_MUC_Notices 剥离出与框架无关的通知抓取/存储/去重能力，
将原聊天命令、轮询与推送重写为 REST API + webhook 的常驻服务。

Plan: docs/plans/0001-bootstrap-engine.md
Changelog: docs/changelog/0001-bootstrap-engine.md
```

后续提交照此格式，`type` 与 `scope` 按实际改动替换。

## 示例

```
fix(core/auth): SM2 公钥解析失败时不再静默退回明文

登录页公钥轮换后正则可能不命中，命中失败时记录 error 并放弃登录，
避免把明文密码发给 CAS。

Plan: docs/plans/0002-auth-hardening.md
Changelog: docs/changelog/0002-auth-hardening.md
```

## 提交前检查

- [ ] `ruff check .` 通过
- [ ] `pytest` 通过
- [ ] 对应 changelog 已填写且 `Verification` 为真实命令
- [ ] 未提交 `config.toml`、`.env`、`data/`、Cookie 等敏感/运行时文件
