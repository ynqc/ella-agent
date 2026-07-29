# Ella Agent 能力总结：Memory

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦 memory 分层与读写语义。

## 5. Memory

Ella Agent 当前有两层 memory。

### 短期会话记忆

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

### conversation_messages 持久化会话表

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

### 长期数据库记忆

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

### `store_extracted_memories(...)` 当前做了什么

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

### `remember(...)` 当前做了什么

`remember(...)` 是显式写 durable memory 的入口。

它当前用于：

- chat 路径内部在需要时写 memory
- workflow 中的 `SaveMemoryStep` 写 `meeting_memo`

和 `store_extracted_memories(...)` 不同，`remember(...)` 本身不负责冲突合并，它更像是“明确知道要写什么内容时的直接持久化入口”。

也就是说：

- `store_extracted_memories(...)` 适合处理 LLM 抽取得到的 memory 列表
- `remember(...)` 适合处理系统显式决定要保存的一条 durable memory

### memory 如何回流到 prompt

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

### 数据分层说明：conversation_messages / memories / workflow cache

当前后端里有三类容易混在一起的数据层，但它们职责并不相同。

#### `conversation_messages`

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

#### `memories`

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

#### `workflow artifact cache`

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

#### 三者的关系

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

### workflow 写 memory 的当前语义

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