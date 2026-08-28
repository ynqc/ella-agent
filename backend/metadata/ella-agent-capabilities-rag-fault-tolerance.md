# Ella Agent 能力总结：RAG 容错（FastGPT 调用失败降级）

本文档是总文档 `ella-agent-capabilities.md` 的拆分子文档，聚焦本阶段完成的 **FastGPT 调用容错** 实现。

## 一、本阶段目标

保证 **FastGPT（RAG 知识检索）调用失败时不影响后续 chat 流程**。

即：知识检索是「增强项」而非「必需项」，任何 FastGPT 相关的失败都必须被隔离在 `KNOWLEDGE_RETRIEVAL` 阶段内，让 pipeline 能够继续走到：

```
PROMPT_BUILD → PLANNING → TOOL_EXECUTION → RESPONDING → COMPLETED
```

## 二、失败隔离的两层防护

### 第一层：KnowledgeService 内部兜底

**文件：** `backend/app/services/knowledge_service.py`

`retrieve_knowledge()` 方法内部已对以下情况做兜底，均返回空字符串 `""`：

- API Key 未配置 → 记录 warning，跳过检索
- `httpx.HTTPStatusError`（4xx / 5xx）→ 记录 error，返回空
- 其它任意异常（连接拒绝、超时、JSON 解析失败等）→ 记录 error，返回空

```python
try:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        ...
except httpx.HTTPStatusError as exc:
    logger.error(...)
    return ""
except Exception as exc:
    logger.error(...)
    return ""
```

### 第二层：AgentRuntime 调用点兜底

**文件：** `backend/app/agent/runtime.py`（`KNOWLEDGE_RETRIEVAL` 阶段）

在 runtime 调用 `retrieve_knowledge()` 处再包一层 `try/except`，作为最后防线，防止任何未被 service 层捕获的异常向上冒泡中断 pipeline：

```python
if self._knowledge_service:
    self._logger.info("Retrieving knowledge from FastGPT...")
    try:
        state.knowledge_context = await self._knowledge_service.retrieve_knowledge(
            state.user_message, session_id=state.session_id
        )
    except Exception as exc:
        self._logger.warning(
            "FastGPT knowledge retrieval failed, continuing without RAG: %s", exc
        )
        state.knowledge_context = ""
    ...
```

## 三、失败后的行为

| 场景 | 结果 |
|------|------|
| FastGPT 未配置 API Key | `knowledge_context = ""`，流程正常继续 |
| FastGPT 返回 HTTP 错误 | 记录 error 日志，`knowledge_context = ""`，流程继续 |
| FastGPT 网络超时 / 连接失败 | 记录日志，`knowledge_context = ""`，流程继续 |
| service 层意外未捕获的异常 | runtime 层捕获，记录 warning，流程继续 |

失败时用户仍能正常得到回答，只是回答**不包含 RAG 知识增强**。

## 四、可观测性

- `KNOWLEDGE_RETRIEVAL` 阶段会通过 progress event 向前端反馈：
  - 检索成功：`检索到 N 字符的相关知识`
  - 检索为空 / 失败：`未检索到相关知识`
  - 未配置：`知识库未配置，跳过`
- 失败原因记录在后端日志（warning / error），不会以错误形式返回给用户。

## 五、设计原则

- **RAG 是可选增强，不是关键路径**：检索失败绝不能让整个 chat 请求失败。
- **双层防护**：service 层负责已知失败的优雅降级，runtime 层负责兜底未知异常。
- **降级而非中断**：失败时以「空知识上下文」继续，而不是抛错或中止。
