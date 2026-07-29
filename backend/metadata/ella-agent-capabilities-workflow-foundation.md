# Ella Agent 能力总结：Workflow Foundation

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦 workflow 基础边界与入口。

## 2. WorkflowRegistry 与统一分发

系统当前已经具备 `WorkflowRegistry`，用于统一管理 workflow 类型、创建逻辑和 dispatch 边界。

当前已经注册的 workflow 类型包括：

- `meeting`
- `bug`

当前 service 层已经不再直接在主干中硬编码实例化 workflow，而是通过 registry 进行：

- workflow 类型查找
- workflow 实例创建
- 通用 `run_workflow(...)` 分发

## 3. Workflow API

当前 workflow API 已经有统一入口：

- `POST /api/workflows/run`

请求体形状已经统一为：

- `workflow_type`
- `session_id`
- `input`

当前已经移除旧的专用 workflow endpoint，统一只保留 `/api/workflows/run`。

## 4. Agent Planner 初版

系统当前已经有最小可用的 `Agent Planner`。

它的职责是：

- 判断用户消息应继续走普通 chat，还是应转入 workflow
- 在支持的 workflow 范围内识别 `workflow_type`
- 从用户自然语言中抽取 workflow 所需输入参数
- 将结构化参数转发给 `WorkflowService`

当前 planner 已经接在 `ChatService` 前面，因此 chat 请求现在具备：

- `User -> Planner -> Chat`
- `User -> Planner -> Workflow`

两条分流路径。

当前 planner 已支持的 workflow 意图包括：

- meeting summary / action items / memo / send Teams
- bug analysis / root cause / Jira comment / post Jira comment