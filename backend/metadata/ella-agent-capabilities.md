# Ella Agent 能力总结

## 拆分文档索引

当前总文档已按主题拆分为以下小文件，便于分别查看；本总文档继续保留，作为完整汇总版本：

- `ella-agent-capabilities-chat.md`
- `ella-agent-capabilities-memory.md`
- `ella-agent-capabilities-rag.md`
- `ella-agent-capabilities-rag-fault-tolerance.md`
- `ella-agent-capabilities-workflow-foundation.md`
- `ella-agent-capabilities-tools-and-runtime.md`
- `ella-agent-capabilities-cache-and-testing.md`
- `ella-agent-capabilities-status-and-gaps.md`

## 一、已有能力

### 1. Chat 与 Conversation

Ella Agent 当前已经具备完整的 chat request/response 链路：

- `POST /api/chat`
- `ChatService`
- `ChatAgent`
- `AgentRuntime`

当前 chat runtime 已经支持：

- 接收用户消息
- 生成或复用 `session_id`
- 保存用户和助手消息
- 基于 memory 构建上下文
- 暴露 tool schema 给 LLM 做 tool planning
- 支持流式输出最终回答
- 提供 `/api/chat/debug` 调试入口

标准 chat 路径当前仍然是：

1. 保存用户消息
2. 尝试抽取 durable memory
3. 组装 memory-aware prompt
4. 进行 tool planning
5. 如有需要执行 tool
6. 基于 tool result 生成最终回答
7. 保存助手回答

#### 普通 chat 分支当前的真实执行顺序

当消息没有被 planner 路由到 workflow 时，`ChatService.stream_response(...)` 会直接走普通 chat 分支，进入：

- `ChatAgent.stream_response(...)`
- `AgentRuntime.stream(...)`

这条普通 chat 路径当前的真实顺序是：

1. 先保存 user message
2. 调用 LLM 做 memory extraction
3. 将抽取出的 durable memory 写入 memory store
4. 从 conversation history 和长期 memory 构建 memory context
5. 调用 LLM 做 planning，判断是否需要调用 tool
6. 如果不需要 tool，直接把这次 planning 的文本作为最终回答
7. 如果需要 tool，后端执行 tool calls
8. 再调用 LLM，基于 tool result 流式生成最终回答
9. 保存 assistant message

#### 普通 chat 中 memory 在哪里发生

普通 chat 路径中的 memory 当前发生在三处：

1. 刚收到消息时，保存 conversation message
2. memory extraction 后，将结构化 memory 写入长期 memory
3. prompt build 时，读取最近对话和相关 memory 拼成上下文

因此普通 chat 的 memory 语义是：

- 会保存 user / assistant 对话消息
- 会尝试抽取 durable memory
- 会在正式 planning 前把 memory 注入 prompt

#### 普通 chat 中 tool 在哪里发生

普通 chat 中不是系统预先决定要不要调 tool，而是先让 LLM 做 planning。

当前顺序是：

1. 后端把 tool schema 暴露给 LLM
2. LLM 返回是否有 `tool_calls`
3. 如果有，后端通过 `ToolDispatcher` 逐个执行
4. 再把 tool result 交给 LLM 生成最终回答

因此普通 chat 的 tool calling 语义是：

- tool 是否执行由 LLM 决定
- tool 参数由后端校验与归一化
- tool 结果会进入第二轮 LLM final answer 生成

#### 普通 chat 中 LLM 在哪里发生

普通 chat 路径当前最多会发生三次 LLM 调用：

1. memory extraction：从用户消息中抽 durable memory
2. planning：决定直接回答还是触发 tool call
3. final answer：在 tool 执行后基于 tool result 流式生成最终回答

如果 planning 阶段没有产生 tool call，那么第三次 LLM 调用不会发生，系统会直接返回 planning 的文本结果。

### 2. WorkflowRegistry 与统一分发

系统当前已经具备 `WorkflowRegistry`，用于统一管理 workflow 类型、创建逻辑和 dispatch 边界。

当前已经注册的 workflow 类型包括：

- `meeting`
- `bug`

当前 service 层已经不再直接在主干中硬编码实例化 workflow，而是通过 registry 进行：

- workflow 类型查找
- workflow 实例创建
- 通用 `run_workflow(...)` 分发

### 3. Workflow API

当前 workflow API 已经有统一入口：

- `POST /api/workflows/run`

请求体形状已经统一为：

- `workflow_type`
- `session_id`
- `input`

当前已经移除旧的专用 workflow endpoint，统一只保留 `/api/workflows/run`。

### 4. Agent Planner 初版

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

### 5. Memory

Ella Agent 当前有两层 memory：

#### 短期会话记忆

按 session 保存在进程内存中，用于：

- 最近消息回放
- 当前对话上下文拼接

特征：

- 快
- 进程内
- 重启后丢失

当前这层短期 memory 由 `ConversationMemory` 维护。

它的行为是：

- 按 `session_id` 维护消息列表
- 每条消息保存 `role / content / timestamp`
- 默认最多保留最近 20 条消息
- 读取上下文时默认取最近 10 条

这层数据主要服务于当前进程内的 prompt 拼接，不是 durable memory。

#### conversation_messages 持久化会话表

除了进程内的 `ConversationMemory`，系统还会把对话消息持久化到数据库 `conversation_messages` 表。

当前保存字段包括：

- `session_id`
- `role`
- `content`
- `created_at`

普通 chat 路径中：

- `add_user_message(...)` 会同时写入进程内会话 memory 和 `conversation_messages`
- `add_assistant_message(...)` 也会同时写入这两处

因此当前 conversation message 是“双写”语义：

- 进程内副本用于快速取最近消息
- 数据库副本用于 durable conversation history

#### 长期数据库记忆

保存在数据库 `memories` 表中，用于：

- 用户偏好
- 用户 profile
- project facts
- constraints
- workflow 产生的 meeting memo

当前 `memories` 表保存字段包括：

- `session_id`
- `memory_type`
- `content`
- `keywords`
- `created_at`
- `updated_at`

这里存的是结构化 durable memory，不是整段对话消息。

chat 路径当前支持 memory extraction，当前可抽取的 memory type 包括：

- `preference`
- `profile`
- `project`
- `constraint`

这些 memory 已具备：

- 归一化
- 去重
- conflict key 处理
- 排序
- prompt 上下文注入

#### `store_extracted_memories(...)` 当前做了什么

普通 chat 路径做完 memory extraction 后，不会把 LLM 返回结果原样直接入库，而是先经过 `store_extracted_memories(...)`。

当前处理流程包括：

1. 过滤掉非法 memory 项
2. 归一化 `memory_type / content / keywords`
3. 在本批抽取结果内部先做一次去重
4. 到数据库里查同类型、同 conflict key 的旧 memory
5. 如果是完全重复项，则跳过不写
6. 如果是冲突项，则更新主记录并删除多余冲突记录
7. 如果没有冲突，则新建一条 memory

因此 `store_extracted_memories(...)` 的语义不是“盲写”，而是“规范化 + 去重 + 冲突合并后再持久化”。

#### `remember(...)` 当前做了什么

`remember(...)` 是显式写 durable memory 的入口。

它当前用于：

- chat 路径内部在需要时写 memory
- workflow 中的 `SaveMemoryStep` 写 `meeting_memo`

和 `store_extracted_memories(...)` 不同，`remember(...)` 本身不负责冲突合并，它更像是“明确知道要写什么内容时的直接持久化入口”。

也就是说：

- `store_extracted_memories(...)` 适合处理 LLM 抽取得到的 memory 列表
- `remember(...)` 适合处理系统显式决定要保存的一条 durable memory

#### memory 如何回流到 prompt

当前 memory 并不是“写完就结束”，还会在后续 chat 请求中回流到 prompt。

当前流程是：

1. 先取最近 conversation messages
2. 再按当前 user message 搜索相关 memories
3. 对命中的 memories 做排序和压缩去重
4. 拼成 `memory_context`
5. 注入 effective user message，交给 planning / final answer 阶段的 LLM

因此当前 memory 系统既承担：

- conversation replay
- durable fact retention
- prompt context augmentation

#### 数据分层说明：conversation_messages / memories / workflow cache

当前后端里有三类容易混在一起的数据层，但它们职责并不相同。

##### `conversation_messages`

这是对话消息历史层。

它存的内容是：

- user message
- assistant message
- 每条消息对应的 `session_id / role / content / created_at`

它的主要用途是：

- 回放最近对话
- 给普通 chat 构建 recent conversation context
- 作为 durable conversation history

它不负责：

- 存结构化用户事实
- 存 workflow 产物缓存

##### `memories`

这是结构化 durable memory 层。

它存的内容是：

- `preference`
- `profile`
- `project`
- `constraint`
- `meeting_memo`

每条记录当前有：

- `session_id`
- `memory_type`
- `content`
- `keywords`
- `created_at / updated_at`

它的主要用途是：

- 保存可复用的用户事实或项目事实
- 保存 workflow 显式产出的 durable memo
- 在后续 chat 请求里参与 memory search 与 prompt 注入

它不负责：

- 保存整段对话消息时间线
- 保存 workflow 的内容缓存命中结果

##### `workflow artifact cache`

这是 workflow 内容结果复用层。

它存的内容不是对话，也不是用户事实，而是 workflow 生成出的 content-only artifact。

当前包括：

- `meeting` 的 `summary / action_items / memo`
- `bug` 的 `analysis / root_cause / jira_comment`

它的主要用途是：

- 当规范化输入命中 cache key 时，避免重复跑 LLM 内容步骤
- 复用已有 workflow 产物
- 将 side effect 与内容缓存分离

它不负责：

- 保存 user / assistant 对话历史
- 保存长期用户事实
- 替代 `memories` 表承载 workflow durable memory

##### 三者的关系

可以把这三层理解成：

- `conversation_messages`：存“说过什么”
- `memories`：存“值得长期记住的结构化事实”
- `workflow artifact cache`：存“可复用的 workflow 内容产物”

因此同一条用户请求，可能会同时影响多层数据：

- 普通 chat：通常会写 `conversation_messages`，有时会写 `memories`
- meeting workflow cache miss：会写 workflow cache，也会写 `meeting_memo` 到 `memories`
- meeting workflow cache hit：会复用 workflow cache，但不会再次写 `meeting_memo`
- bug workflow：会写或读取 workflow cache，但当前不会写 `memories`

此外，`meeting workflow` 也已经具备显式写 memory 的能力。

`SaveMemoryStep` 会把生成出的 meeting memo 写入长期 memory，当前类型为：

- `meeting_memo`

#### workflow 写 memory 的当前语义

当前只有 `meeting workflow` 会主动写长期 memory。

具体时机是：

1. `transcript -> summary -> action_items -> memo` 这些内容步骤先成功完成
2. 随后执行 `SaveMemoryStep`
3. 将最终 memo 作为 `meeting_memo` 写入长期 memory

写入内容当前包括：

- memo 正文
- `meeting_title`，如果有
- 关键词，当前来自 `meeting_title` 与 `channel`

需要注意的是：

- 只有 cache miss 的首次完整执行会写入 memory
- 如果后续 workflow 因相同内容命中 cache，不会再次执行 `SaveMemoryStep`
- `bug workflow` 当前不会写长期 memory

### 6. Tool Calling

Ella Agent 当前已经具备后端 tool registry + dispatcher 模型。

现有 mock tools 覆盖：

- browser
- calendar
- confluence
- filesystem
- github
- jira
- teams

#### Chat 中的 tool calling

在 chat 路径中：

- tool schema 会暴露给 LLM
- LLM 决定是否调用工具
- 后端做参数校验
- 后端执行工具
- LLM 基于 tool result 输出最终回答

#### Workflow 中的 tool calling

在 workflow 路径中：

- 工具是否执行由系统决定
- step 顺序是确定性的
- side effect 明确属于 workflow step

当前已经接入的 side effect 工具包括：

- `send_teams_message`
- `post_jira_comment`

### 7. Workflow Runtime

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

#### 7.1 Meeting Workflow

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

#### 7.2 Bug Workflow

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

### 8. Artifact Cache

当前 `meeting workflow` 和 `bug workflow` 都已经支持数据库持久化的 artifact cache。

当前 cache 的核心目标是：

- 复用 workflow 的内容生成结果
- 避免重复跑 LLM 内容步骤
- 将 side effect 与内容缓存语义分离

#### 当前 workflow 取 cache 的判断方式

workflow 进入 `WorkflowService` 后，不是直接开始跑 step，而是先查 cache。

当前判断流程是：

1. 先对原始输入做规范化
2. 对规范化后的内容计算 `input_hash`
3. 同时构造 `cache_scope`
4. 用 `workflow_type + input_hash + cache_scope` 去数据库查缓存记录

也就是说，当前不是“只要 hash 一样就命中”，而是这三个条件都相同才命中。

当前各 workflow 的 cache key 语义是：

- `meeting`
	- `input_hash` 基于规范化后的 `transcript`
	- `cache_scope` 当前包含 `meeting_title`
- `bug`
	- `input_hash` 基于规范化后的 `bug_report`
	- `cache_scope` 当前包含 `issue_key`

当前 `channel / send_to_teams / post_to_jira` 不参与内容缓存命中判断；它们影响的是命中后的 side effect replay。

#### 当前 cache 存的不是整次运行原样结果

当前持久化到 cache 的是 content-only result，而不是整次 workflow 的全部 step 结果。

也就是说：

- `meeting` 只缓存 `summary / action_items / memo` 及其相关 artifact
- `bug` 只缓存 `analysis / root_cause / jira_comment` 及其相关 artifact

下列 side effect 结果不会直接作为可复用内容缓存：

- `save_memory`
- `send_teams`
- `post_jira_comment`

#### 当前 meeting cache 语义

缓存未命中时：

- 正常执行内容步骤
- 写入 artifact cache
- 执行 `SaveMemoryStep`
- 根据请求决定是否 `send_teams`

也就是说，首次完整执行会同时产生两类持久化效果：

- 内容 artifact 写入 workflow cache
- memo 写入长期 memory

缓存命中时：

- 复用 `summary / action_items / memo`
- 不重跑 `save_memory`
- 根据当前请求重新执行 `send_teams`

因此对于 meeting workflow，命中 cache 后：

- 不会再次写 `meeting_memo`
- 但如果这次请求要求发送 Teams，仍会基于缓存 memo 重新发送

#### 当前 bug cache 语义

缓存未命中时：

- 正常执行 `analysis / root_cause / jira_comment`
- 写入 artifact cache
- 根据请求决定是否 `post_jira_comment`

缓存命中时：

- 复用 `analysis / root_cause / jira_comment`
- 根据当前请求重新执行 `post_jira_comment`

因此对于 bug workflow，命中 cache 后：

- 不会重新跑 LLM 内容步骤
- 但如果这次请求要求 post Jira，仍会基于缓存 `jira_comment` 重新执行 side effect

因此当前 cache 已经明确是：

- 内容结果复用
- side effect 按当前请求重放

### 9. 测试与验证

当前已经有正式的定向测试资产，覆盖范围包括：

- `WorkflowService` registry 分发
- `meeting workflow` cache hit/miss 语义
- `bug workflow` cache hit/miss 语义
- cache hit 下 side effect replay
- 统一 workflow API `/api/workflows/run`
- 旧兼容 endpoint 的统一分发行为
- `ChatService` 的 planner 分流逻辑

当前已验证的主要行为包括：

- generic workflow dispatch 不绕开 meeting cache 语义
- bug workflow cache hit 会重放 Jira post side effect
- chat 请求可以自动分流到 workflow 执行路径

---

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

---

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

---

## 四、接下来的自然顺序

在 1-8 已经落地的前提下，下一步不建议再重复改 registry 主链路，建议按下面顺序推进：

1. 把 mock Teams / Jira 替换为真实外部集成
2. 明确 workflow artifact 与 long-term memory 的长期边界
3. 补 planner prompt 回归和更高层 E2E 测试
4. 只有当 workflow 复杂度显著上升后，再考虑 workflow graph

---

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
