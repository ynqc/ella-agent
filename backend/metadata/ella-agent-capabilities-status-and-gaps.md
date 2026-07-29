# Ella Agent 能力总结：落地状态与剩余缺口

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦 1-8 落地状态、剩余缺口和建议顺序。

## 二、Registry 之后的 1-8 落地状态

下面这 8 项是当前主干已经落地的顺序，不再只是 roadmap。

### 1. 统一 workflow 调用入口

已经完成。

当前主入口是：

- `WorkflowService.run_workflow(...)`
- `POST /api/workflows/run`

`ChatService` 在 workflow 分支中只调用统一的 `run_workflow(...)`，不会直接实例化 `MeetingWorkflow` 或 `BugWorkflow`。

### 2. 固定 workflow 输入输出契约

已经完成。

当前契约包括：

- `workflow_type`
- `session_id`
- `input_payload`
- 统一返回 `WorkflowRunResult`
- 每步统一返回 `WorkflowStepResult`
- artifact 命名在各 workflow 内保持稳定

API 层还额外通过 Pydantic 模型做输入校验：

- `MeetingWorkflowInput`
- `BugWorkflowInput`
- `WorkflowRunRequest`

### 3. 调用方迁移到统一入口

主干已经完成。

当前统一入口是 `/api/workflows/run`，旧的专用 workflow endpoint 已经删除。

### 4. workflow 语义保留在 WorkflowService

已经完成，这是当前架构的关键边界。

`WorkflowRegistry` 只负责：

- 注册 workflow
- 创建 workflow
- dispatch 到 runner

真正的 service 级语义仍然保留在 `WorkflowService`，例如：

- meeting cache hit 时跳过 `save_memory`
- meeting cache hit 时可按本次请求重放 `send_teams`
- bug cache hit 时复用内容 artifact
- bug cache hit 时可按本次请求重放 `post_jira_comment`

### 5. Planner 接入 chat 主路径

已经完成。

当前 chat 主路径已变成：

`User -> ChatService -> WorkflowPlanner -> chat / clarify / workflow`

也就是说，workflow 不再只是一个孤立 API，而是已经可以从自然语言 chat 入口进入。

### 6. Clarification continuation

已经完成。

当前已支持：

- 缺参时返回 `WorkflowClarification`
- `WorkflowClarificationStore` 按 `session_id` 暂存 pending 状态
- 下轮补参时调用 `resolve_clarification(...)`
- 只补新增字段也可以，service 层会 merge 已知 `input_payload`
- 用户切换话题时，旧 pending 会自动丢弃

### 7. Debug 与可观测性

已经完成最小闭环。

当前 `/api/chat/debug` 已可看到：

- `planning_text`
- `pending_workflow_clarification`
- tool planning / tool result
- memory 相关上下文
- 最终输出文本

对于 workflow 路径，还能在最终结果中看到：

- `workflow_type`
- cache hit / miss
- 关键 artifact 摘要

### 8. API / Service / Chat 集成测试

已经完成当前阶段所需的回归测试。

当前已覆盖：

- registry 分发
- unified `/api/workflows/run`
- legacy endpoint 兼容分发
- meeting cache 语义
- bug cache 语义
- planner -> clarify
- pending clarification merge
- topic switch 时清理 stale pending
- chat / workflow 主分流

## 三、当前真实剩余缺口

### 1. 外部工具仍是 mock 集成

Teams 与 Jira 当前验证的是编排与返回结构，不是真实外部投递。

仍未覆盖：

- 真实认证
- 真实 channel / issue 侧写
- 外部失败重试
- 幂等与追踪 id

### 2. workflow artifact 与 memory 还是两套查询模型

当前语义已经分开，但查询入口仍然分裂：

- chat memory 通过 `MemoryManager`
- workflow artifact 通过 cache service

后续如果要让 chat 更直接消费 workflow 产物，需要补统一查询视图。

### 3. planner 仍然是轻量路由器，不是任务协调器

当前 planner 已经支持 clarification continuation，但仍然只做：

- 识别 workflow 意图
- 抽取输入
- 缺参追问
- 继续补参

还没有进入更复杂的：

- 多任务拆解
- 子任务计划
- workflow graph 级编排

### 4. 更高层测试仍然缺失

当前测试已经能保主干回归，但还缺：

- planner prompt 回归集
- 真实外部依赖集成测试
- 端到端用户路径测试
- 前端联调级别的 streaming / session 行为测试

## 四、接下来的自然顺序

在 1-8 已经落地的前提下，下一步不建议再重复改 registry 主链路，建议按下面顺序推进：

1. 把 mock Teams / Jira 替换为真实外部集成
2. 明确 workflow artifact 与 long-term memory 的长期边界
3. 补 planner prompt 回归和更高层 E2E 测试
4. 只有当 workflow 复杂度显著上升后，再考虑 workflow graph

## 结论

Ella Agent 当前已经不只是“带 memory 和 tool 的 chat agent”，而是一个同时具备：

- memory-aware chat
- planner-based chat routing
- unified workflow dispatch
- deterministic meeting workflow
- deterministic bug workflow
- database-backed artifact cache
- cache hit 下的 side effect replay 语义

的 agent backend。

当前最自然的下一步，不是立刻做 workflow graph，而是继续把 planner 做深，把 chat 到 workflow 的自动路由从“可用”推进到“稳定、可澄清、可观测”。