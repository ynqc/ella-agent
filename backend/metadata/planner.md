                User
                  │
                  ▼
             ChatService
                  │
                  ▼
        WorkflowPlanner.plan()
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
 classify_intent()    pending clarification?
        │                   │
        ▼                   ▼
 workflow?            resolve_clarification()
        │
        ▼
 fill_workflow_slots()
        │
        ├──────────────┐
        ▼              ▼
WorkflowPlan     WorkflowClarification
        │              │
        ▼              ▼
 WorkflowService   ClarificationStore
        │
        ▼
 Workflow Runtime