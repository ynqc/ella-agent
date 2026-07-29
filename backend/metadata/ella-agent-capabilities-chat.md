# Ella Agent 能力总结：Chat 与 Conversation

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦普通 chat 路径。

## 1. Chat 与 Conversation

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

### 普通 chat 分支当前的真实执行顺序

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

### 普通 chat 中 memory 在哪里发生

普通 chat 路径中的 memory 当前发生在三处：

1. 刚收到消息时，保存 conversation message
2. memory extraction 后，将结构化 memory 写入长期 memory
3. prompt build 时，读取最近对话和相关 memory 拼成上下文

因此普通 chat 的 memory 语义是：

- 会保存 user / assistant 对话消息
- 会尝试抽取 durable memory
- 会在正式 planning 前把 memory 注入 prompt

### 普通 chat 中 tool 在哪里发生

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

### 普通 chat 中 LLM 在哪里发生

普通 chat 路径当前最多会发生三次 LLM 调用：

1. memory extraction：从用户消息中抽 durable memory
2. planning：决定直接回答还是触发 tool call
3. final answer：在 tool 执行后基于 tool result 流式生成最终回答

如果 planning 阶段没有产生 tool call，那么第三次 LLM 调用不会发生，系统会直接返回 planning 的文本结果。