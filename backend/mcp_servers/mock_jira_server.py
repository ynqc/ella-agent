"""Mock Jira MCP Server for development and testing."""

import json

from mcp.server import MCPServer

server = MCPServer(name="mock-jira", version="0.1.0")


@server.tool(
    name="jira_search_issues",
    description="Search Jira issues by query string (JQL or keyword)",
)
async def jira_search_issues(query: str = "bug") -> str:
    results = [
        {
            "key": "ENG-1024",
            "summary": "Login page throws 500 on expired session",
            "status": "Open",
            "assignee": "alice@example.com",
            "priority": "High",
        },
        {
            "key": "ENG-1025",
            "summary": "Dashboard chart fails to render with empty data",
            "status": "In Progress",
            "assignee": "bob@example.com",
            "priority": "Medium",
        },
        {
            "key": "ENG-1030",
            "summary": "API timeout when fetching large datasets",
            "status": "Open",
            "assignee": None,
            "priority": "High",
        },
    ]
    return json.dumps({"issues": results, "total": len(results), "query": query})


@server.tool(
    name="jira_create_issue",
    description="Create a new Jira issue in the specified project",
)
async def jira_create_issue(
    project: str = "ENG",
    summary: str = "New issue",
    description: str = "",
    issue_type: str = "Bug",
    priority: str = "Medium",
) -> str:
    created = {
        "key": f"{project}-9999",
        "summary": summary,
        "description": description,
        "issue_type": issue_type,
        "priority": priority,
        "status": "Open",
        "url": f"https://jira.example.com/browse/{project}-9999",
    }
    return json.dumps({"created": True, "issue": created})


@server.tool(
    name="jira_add_comment",
    description="Add a comment to an existing Jira issue",
)
async def jira_add_comment(issue_key: str = "ENG-1024", comment: str = "") -> str:
    result = {
        "issue_key": issue_key,
        "comment_id": "comment-42",
        "body": comment,
        "author": "ella-agent",
        "created": "2026-08-18T10:00:00Z",
    }
    return json.dumps({"success": True, "comment": result})


if __name__ == "__main__":
    import asyncio

    asyncio.run(server.run_stdio_async())
