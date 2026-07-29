# Ella Agent 能力总结：Tools 与 Workflow Runtime

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦工具调用与 deterministic workflow runtime。

## 6. Tool Calling

Ella Agent 当前已经具备后端 tool registry + dispatcher 模型。

现有 mock tools 覆盖：

- browser
- calendar
- confluence
- filesystem
- github
- jira
- teams

### Chat 中的 tool calling

在 chat 路径中：

- tool schema 会暴露给 LLM
- LLM 决定是否调用工具
- 后端做参数校验
- 后端执行工具
- LLM 基于 tool result 输出最终回答

### Workflow 中的 tool calling

在 workflow 路径中：

- 工具是否执行由系统决定
- step 顺序是确定性的
- side effect 明确属于 workflow step

当前已经接入的 side effect 工具包括：

- `send_teams_message`
- `post_jira_comment`

## 7. Workflow Runtime

Ella Agent 当前已经具备 deterministic workflow runtime。

每次 workflow run 当前都有：

- 有序 step
- 结构化 artifact
- 每步状态
- 每步耗时
- workflow 最终结果
- 可选 side effect

当前 workflow 仍然是线性执行模型：

- 代码定义顺序
- 不依赖 LLM 决定编排
- 不做 graph 级分支与并行

### 7.1 Meeting Workflow

当前链路：

- `transcript`
- `summary`
- `action_items`
- `memo`
- `save_memory`
- `send_teams`

已经实现的能力：

- 根据 transcript 生成 meeting summary
- 提取 action items
- 生成可分享 memo
- 首次执行时保存 meeting memory
- 根据请求选择是否发送 Teams

### 7.2 Bug Workflow

当前链路：

- `bug_report`
- `analysis`
- `root_cause`
- `jira_comment`
- `post_jira_comment`

已经实现的能力：

- 对 bug report 做结构化分析
- 生成 root cause 假设
- 生成 Jira comment
- 根据请求选择是否真正执行 mock Jira post