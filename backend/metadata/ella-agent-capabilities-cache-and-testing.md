# Ella Agent 能力总结：Artifact Cache 与测试

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦 workflow cache 和测试覆盖。

## 8. Artifact Cache

当前 `meeting workflow` 和 `bug workflow` 都已经支持数据库持久化的 artifact cache。

当前 cache 的核心目标是：

- 复用 workflow 的内容生成结果
- 避免重复跑 LLM 内容步骤
- 将 side effect 与内容缓存语义分离

### 当前 workflow 取 cache 的判断方式

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

### 当前 cache 存的不是整次运行原样结果

当前持久化到 cache 的是 content-only result，而不是整次 workflow 的全部 step 结果。

也就是说：

- `meeting` 只缓存 `summary / action_items / memo` 及其相关 artifact
- `bug` 只缓存 `analysis / root_cause / jira_comment` 及其相关 artifact

下列 side effect 结果不会直接作为可复用内容缓存：

- `save_memory`
- `send_teams`
- `post_jira_comment`

### 当前 meeting cache 语义

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

### 当前 bug cache 语义

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

## 9. 测试与验证

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