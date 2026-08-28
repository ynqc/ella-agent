# Ella Agent 能力总结：RAG（知识检索增强）

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦 RAG 能力的当前实现状态。

## 一、架构概览

当前 RAG 采用 **外部委托模式**，将所有知识管理（文档索引、embedding、向量检索）委托给外部 FastGPT 服务，本地只负责：

1. 发起检索请求
2. 接收检索结果
3. 将结果注入 LLM prompt

```
用户消息
  │
  ▼
AgentRuntime.stream()
  │
  ├── MEMORY_CAPTURE（抽取持久记忆）
  │
  ├── KNOWLEDGE_RETRIEVAL
  │       │
  │       ▼
  │   KnowledgeService.retrieve_knowledge(query)
  │       │
  │       ▼
  │   HTTP POST → FastGPT /api/v1/chat
  │       │
  │       ▼
  │   state.knowledge_context = 检索结果
  │
  ├── PROMPT_BUILD（合并 memory + knowledge → 有效消息）
  │
  ├── PLANNING（LLM 决定回复 / 工具调用）
  │
  └── RESPONDING（流式输出最终回答）
```

## 二、核心组件

### 1. KnowledgeService

**文件：** `backend/app/services/knowledge_service.py`

职责：

- 通过 HTTP 调用外部 FastGPT 的 `/chat` 端点
- 发送用户 query，获取检索到的文档片段
- 优先使用 `data.retrieved_docs` 作为上下文
- 如果没有显式文档返回，降级使用 FastGPT 的 LLM 生成回答作为上下文
- API Key 未配置时优雅跳过（返回空字符串，记录 warning）

关键行为：

- 使用固定 `chatId: "ella-agent-rag"`
- 使用 `httpx.AsyncClient` 异步调用
- 超时和网络异常均有 try/except 兜底

### 2. AgentRuntime 集成

**文件：** `backend/app/agent/runtime.py`

`KNOWLEDGE_RETRIEVAL` 是 pipeline 中的独立阶段：

```
RECEIVED → MEMORY_CAPTURE → KNOWLEDGE_RETRIEVAL → PROMPT_BUILD → PLANNING → ...
```

- 阶段触发条件：`KnowledgeService` 已注入
- 检索结果存入 `state.knowledge_context`

### 3. Prompt 组装

**文件：** `backend/app/agent/runtime.py`（PROMPT_BUILD 阶段）

组装逻辑：

- Memory context 标记为 `"User Memory:"`
- Knowledge context 标记为 `"External Knowledge:"`
- 格式：`[Memory Context]...\n[User Message]...`

### 4. AgentState

**文件：** `backend/app/agent/state.py`

- `AgentPhase.KNOWLEDGE_RETRIEVAL` — pipeline 中的一级阶段
- `AgentState.knowledge_context: str | None` — 存储检索结果
- 已在 `to_debug_dict()` 中序列化

### 5. ChatAgent 注入

**文件：** `backend/app/agent/chat_agent.py`

- `ChatAgent.__init__()` 接受可选的 `knowledge_service` 参数
- 默认创建 `KnowledgeService()` 实例
- 传递给 `AgentRuntime`

## 三、配置

**文件：** `backend/config.py`

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `FASTGPT_API_KEY` | `""` | FastGPT API 密钥，为空时 RAG 自动关闭 |
| `FASTGPT_BASE_URL` | `http://localhost:3000/api/v1` | FastGPT 服务地址 |

## 四、依赖

- `httpx>=0.27.0` — 用于异步 HTTP 调用 FastGPT

无本地向量数据库依赖（无 chromadb / faiss / pinecone / weaviate）。

## 五、已实现 vs 未实现

### 已实现

- [x] 知识检索服务（KnowledgeService）
- [x] Pipeline 中 KNOWLEDGE_RETRIEVAL 阶段
- [x] 检索结果注入 prompt
- [x] AgentState 中 knowledge_context 字段
- [x] 环境变量配置
- [x] 无 API Key 时优雅降级
- [x] 异常兜底（网络错误、超时）—— service 层 + runtime 层双层防护，详见 `ella-agent-capabilities-rag-fault-tolerance.md`

### 未实现（依赖外部 FastGPT）

- [ ] 文档上传 / 处理 API
- [ ] 文本分块（chunking）
- [ ] Embedding 生成
- [ ] 本地向量数据库
- [ ] 索引管理（创建 / 更新 / 删除）
- [ ] 文档元数据管理
- [ ] 混合搜索（keyword + semantic）
- [ ] 检索结果排序 / 重排（reranking）

## 六、已知限制

1. `knowledge_context` 未暴露在 `AgentStateDebugResponse` Pydantic schema 中，debug API 当前不返回此字段
2. 固定 `chatId` 意味着所有用户共享同一个 FastGPT 会话上下文
3. 无检索质量评估或 relevance scoring
4. Confluence 工具（`backend/app/tools/confluence.py`）是独立的 mock 实现，不走 RAG pipeline

## 七、后续演进方向

1. 将 `knowledge_context` 加入 debug API response schema
2. 按 session_id 区分 FastGPT chatId
3. 增加检索结果的 relevance 过滤
4. 考虑本地向量库作为 FastGPT 的备选方案
5. Confluence 工具从 mock 转为真实集成，可选择接入 RAG pipeline
