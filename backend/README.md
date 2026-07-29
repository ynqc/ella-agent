## Setup

Create a local `.env` file in this folder with these values:

```env
SSC_CLOUD_API_KEY=your-api-key
SSNC_CASE_ID=your-case-id
SSNC_BASE_URL=https://api-ai-us.ssnc-corp.cloud/v1
SSNC_MODEL=Qwen/Qwen3-30B-A3B
SSNC_TEMPERATURE=0
ELLA_CHAT_SYSTEM_PROMPT=You are a helpful assistant.
FRONTEND_ORIGIN=http://localhost:5173
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
uvicorn main:app --reload --port 8000
```

Call the chat API:

```bash
curl -N -X POST http://localhost:8000/api/chat \
	-H 'Content-Type: application/json' \
	-d '{"session_id":"demo-001","message":"What are my Jira tasks today?"}'
```

Another example:

```bash
curl -N -X POST http://localhost:8000/api/chat \
	-H 'Content-Type: application/json' \
	-d '{"session_id":"demo-001","message":"Find release notes in Confluence."}'
```

If the client does not send `session_id`, the backend generates one and returns it in the `X-Session-Id` response header. The frontend should persist that value and reuse it for later turns in the same conversation.

Tool usage in chat:

```text
What are my Jira tasks today?
Find release notes in Confluence.
Show recent Teams messages from engineering.
```

The backend now exposes tool schemas to the LLM, lets the model choose a tool call,
executes that tool on the server, and then asks the LLM to produce the final answer
from the tool results.

Tool-call debug logs are emitted from [app/llm/client.py](app/llm/client.py) and include:

```text
chat request received
llm answered without tool call
llm selected tool calls: [...]
tool execution results: [...]
requesting final answer from llm with tool results
```