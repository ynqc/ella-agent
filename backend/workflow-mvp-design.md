# Workflow MVP Technical Design

## 1. Goal

Phase 4 introduces a workflow orchestration layer.

The purpose is not to improve chat quality. The purpose is to support deterministic multi-step execution such as:

- Meeting -> Transcript -> Summary -> Action Items -> Memo -> Send Teams
- Bug -> Analysis -> Root Cause -> Jira Comment

In this phase, the system moves from:

- one user message -> one assistant answer

to:

- one workflow input -> multiple ordered steps -> structured artifacts -> optional side effects


## 2. MVP Scope

The MVP should implement a minimal workflow engine and one concrete workflow: `MeetingWorkflow`.

Supported in MVP:

- fixed sequential steps
- synchronous execution
- structured step outputs
- optional side-effect step
- per-step status and timing
- full run result for debugging

Not supported in MVP:

- branching workflows
- loops or retries
- human approval gates
- background jobs
- workflow DSL or visual builder
- many workflow types at once


## 3. Design Principle

Workflow order must be defined by code, not by the LLM.

The LLM is useful inside a step, for example:

- summarize transcript
- extract action items
- compose memo
- analyze a bug
- draft a Jira comment

The LLM should not decide:

- which step runs next
- whether a step is skipped
- whether a side effect should happen

That control belongs to the workflow runner.


## 4. Why This Must Be Separate From Chat Runtime

The current chat runtime is optimized for a single request pipeline:

- capture user memory
- build prompt
- let the LLM decide whether to call tools
- produce one final answer

This is a good fit for conversational chat, but not for workflow execution.

Main mismatches:

1. The current runtime has one main output: `final_text`.
2. Workflow execution needs multiple first-class artifacts.
3. Tool calling is currently model-selected.
4. Workflow side effects should be system-controlled.
5. Current memory extraction is designed for durable user memory, not meeting artifacts or bug artifacts.

Conclusion:

Phase 4 should add a new workflow layer next to chat, not inside the existing chat runtime.


## 5. Reuse From Existing System

The workflow layer should reuse existing components where they already fit.

Reusable components:

- `app/llm/client.py`
  - use for LLM invocation inside workflow steps
- `app/llm/prompt_builder.py`
  - extend with workflow-specific prompt builders or add a separate workflow prompt builder
- `app/memory/memory_manager.py`
  - use only for explicit persistence operations
- `app/services/tool_dispatcher.py`
  - use for deterministic side-effect steps like Teams or Jira

Components that should not control workflow execution:

- `app/agent/runtime.py`
- `app/agent/chat_agent.py`
- `app/services/chat_service.py`


## 6. Core Abstractions

### 6.1 WorkflowDefinition

Represents one workflow type.

Suggested fields:

- `name`
- `description`
- `steps`


### 6.2 WorkflowContext

Represents the shared execution input and cross-step state.

Suggested fields for MVP:

- `workflow_id`
- `workflow_type`
- `session_id`
- `input_payload`
- `artifacts`
- `metadata`


### 6.3 WorkflowStep

Represents one executable unit in the workflow.

Suggested contract:

```python
class WorkflowStep(Protocol):
	name: str

	async def run(self, context: WorkflowContext) -> StepResult:
		...
```

Each step:

- reads from `context.input_payload` or `context.artifacts`
- writes one structured artifact
- does one thing only
- either succeeds or fails clearly


### 6.4 StepResult

Represents one step execution result.

Suggested fields:

- `step_name`
- `status`
- `artifact_key`
- `artifact`
- `error`
- `started_at`
- `completed_at`
- `duration_ms`


### 6.5 WorkflowRunResult

Represents the full workflow execution result.

Suggested fields:

- `workflow_id`
- `workflow_type`
- `status`
- `steps`
- `artifacts`
- `started_at`
- `completed_at`
- `error`


## 7. Artifact Model

Artifacts are the outputs passed between steps.

They should be structured whenever possible.

Suggested artifact keys for `MeetingWorkflow`:

- `transcript`
- `summary`
- `action_items`
- `memo`
- `memory_record`
- `teams_delivery`

Suggested artifact keys for future `BugWorkflow`:

- `bug_report`
- `analysis`
- `root_cause`
- `jira_comment`
- `jira_delivery`


## 8. MeetingWorkflow MVP

### 8.1 Input

MVP input should assume transcript text already exists.

Suggested request shape:

```json
{
  "workflow_type": "meeting",
  "session_id": "session-123",
  "input": {
    "transcript": "...",
    "meeting_title": "Weekly Sync",
    "channel": "engineering",
    "send_to_teams": false
  }
}
```

`Transcript` is input data, not necessarily a workflow step.


### 8.2 Step Order

```text
Input Transcript
-> SummaryStep
-> ActionItemStep
-> MemoStep
-> SaveArtifactStep
-> OptionalSendTeamsStep
```


### 8.3 SummaryStep

Purpose:

- convert transcript into a normalized meeting summary

Input:

- `transcript`

Output artifact:

```json
{
  "title": "Weekly Sync Summary",
  "summary": "...",
  "decisions": ["..."],
  "risks": ["..."],
  "open_questions": ["..."]
}
```

Why structured output matters:

- later steps can consume reliable fields instead of reparsing free text


### 8.4 ActionItemStep

Purpose:

- extract actionable tasks from transcript and summary

Input:

- `transcript`
- `summary`

Output artifact:

```json
[
  {
    "title": "Prepare release note draft",
    "owner": "Alice",
    "due_date": null,
    "priority": "medium",
    "notes": "Needed before Friday review"
  }
]
```


### 8.5 MemoStep

Purpose:

- produce the final human-readable memo for sharing and storage

Input:

- `summary`
- `action_items`
- optional metadata such as `meeting_title`

Output artifact:

- a final memo string or a structured memo payload with `title` and `body`

Suggested MVP output:

```json
{
  "title": "Weekly Sync Memo",
  "body": "..."
}
```


### 8.6 SaveArtifactStep

Purpose:

- persist the meeting result for later retrieval

Important note:

This should not reuse the current automatic user-memory extraction flow.

The current memory system is designed for durable user facts such as preference, profile, project, and constraint. Meeting memo output is a workflow artifact, not the same thing.

MVP recommendation:

- save workflow result explicitly
- do not depend on LLM-based memory extraction

Preferred MVP storage strategy:

- create a dedicated workflow artifact store later

Acceptable temporary strategy:

- explicitly save a memo record through a new persistence method


### 8.7 OptionalSendTeamsStep

Purpose:

- send the memo to Teams when the request explicitly asks for it

Input:

- `memo`
- `channel`
- `send_to_teams`

Behavior:

- if `send_to_teams` is false, mark step as skipped
- if `send_to_teams` is true, execute a deterministic Teams send action

Important note:

This should not be a model-chosen tool call.

The workflow runner should decide whether this step executes.


## 9. BugWorkflow After MVP

The same engine should support future workflow types.

Example:

```text
Bug Report
-> AnalysisStep
-> RootCauseStep
-> JiraCommentStep
-> OptionalPostJiraStep
```

This is why the MVP should build a reusable engine, not a meeting-only pipeline.


## 10. Recommended Module Layout

Suggested new package:

```text
app/
  workflows/
    __init__.py
    models.py
    runner.py
    registry.py
    base.py
    prompts.py
    meeting/
      __init__.py
      workflow.py
      steps.py
    bug/
      __init__.py
      workflow.py
      steps.py
```

Suggested responsibilities:

- `base.py`
  - workflow and step abstractions
- `models.py`
  - request, context, artifact, result models
- `runner.py`
  - sequential execution engine
- `registry.py`
  - workflow lookup by type
- `prompts.py`
  - workflow-specific prompt builders if needed
- `meeting/workflow.py`
  - meeting workflow definition
- `meeting/steps.py`
  - summary, action item, memo, save, Teams steps


## 11. API Recommendation

Do not overload the existing chat endpoint.

Recommended separate entry point:

- `POST /api/workflows/run`

Reason:

- workflow input shape is different from chat input
- workflow output shape is different from chat streaming output
- workflow semantics are task execution, not conversation turn handling

Suggested MVP response shape:

```json
{
  "workflow_id": "wf-001",
  "workflow_type": "meeting",
  "status": "completed",
  "artifacts": {
    "summary": {},
    "action_items": [],
    "memo": {}
  },
  "steps": [
    {"step_name": "summary", "status": "completed"},
    {"step_name": "action_items", "status": "completed"},
    {"step_name": "memo", "status": "completed"},
    {"step_name": "save", "status": "completed"},
    {"step_name": "send_teams", "status": "skipped"}
  ]
}
```


## 12. Execution Semantics

For MVP, use simple fail-fast behavior.

Rules:

- if a required step fails, stop the workflow
- mark workflow status as failed
- return completed step results plus the failure detail
- skipped optional steps should be explicit in the result

Recommended statuses:

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`


## 13. Observability

The workflow runner should expose first-class execution trace data.

At minimum:

- workflow type
- started and completed timestamps
- current step
- step durations
- step artifacts
- failure reason

This mirrors the current debug value of the chat runtime, but for multi-step execution.


## 14. Prompt Strategy

Do not reuse the current planning prompt as the workflow controller.

Instead, use step-specific prompts.

Examples:

- summary prompt
- action-item extraction prompt
- memo composition prompt
- bug analysis prompt
- root-cause prompt
- Jira comment prompt

This keeps each step narrow, testable, and easier to debug.


## 15. Storage Recommendation

There are two distinct concepts that should not be mixed long-term:

1. durable user memory
2. workflow artifacts

Therefore the long-term direction should be:

- user memory stays in the current memory subsystem
- workflow outputs get their own persistence model

For MVP, if time is tight, explicit temporary storage is acceptable, but the interface should be named around workflow artifacts, not generic memory extraction.


## 16. Implementation Order

Recommended order:

1. Define workflow models and base step interface.
2. Implement a sequential `WorkflowRunner`.
3. Implement `MeetingWorkflow` definition.
4. Implement `SummaryStep`.
5. Implement `ActionItemStep`.
6. Implement `MemoStep`.
7. Implement `SaveArtifactStep`.
8. Add a Teams send capability for deterministic delivery.
9. Add a dedicated workflow API endpoint.
10. Add a debug response for workflow runs.


## 17. MVP Success Criteria

Phase 4 MVP is successful if the system can:

- accept a transcript payload
- run ordered steps deterministically
- return structured summary output
- return structured action items
- return a final memo artifact
- persist the result explicitly
- optionally send the memo to Teams
- expose clear per-step run details


## 18. Final Recommendation

The right Phase 4 target is:

`Implement a minimal workflow engine, and use MeetingWorkflow as the first concrete workflow.`

That framing is important because it avoids building a one-off meeting feature and instead creates the execution layer needed for later workflows such as bug analysis and Jira comment generation.