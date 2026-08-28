"""Mock GitHub MCP Server for development and testing."""

import json

from mcp.server import MCPServer

server = MCPServer(name="mock-github", version="0.1.0")


@server.tool(
    name="github_list_prs",
    description="List pull requests for a GitHub repository",
)
async def github_list_prs(repo: str = "org/repo", state: str = "open") -> str:
    prs = [
        {
            "number": 142,
            "title": "feat: add user authentication flow",
            "state": "open",
            "author": "alice",
            "created_at": "2026-08-15T09:30:00Z",
            "labels": ["feature", "auth"],
        },
        {
            "number": 141,
            "title": "fix: resolve memory leak in worker pool",
            "state": "open",
            "author": "bob",
            "created_at": "2026-08-14T14:20:00Z",
            "labels": ["bugfix", "performance"],
        },
        {
            "number": 140,
            "title": "chore: upgrade dependencies to latest",
            "state": "open",
            "author": "charlie",
            "created_at": "2026-08-13T11:00:00Z",
            "labels": ["dependencies"],
        },
    ]
    return json.dumps({"pull_requests": prs, "total": len(prs), "repo": repo, "state": state})


@server.tool(
    name="github_get_pr",
    description="Get details of a specific pull request",
)
async def github_get_pr(repo: str = "org/repo", pr_number: int = 142) -> str:
    pr = {
        "number": pr_number,
        "title": "feat: add user authentication flow",
        "state": "open",
        "author": "alice",
        "body": "This PR adds OAuth2 authentication with JWT tokens.\n\n## Changes\n- Login/logout endpoints\n- Token refresh middleware\n- User session management",
        "created_at": "2026-08-15T09:30:00Z",
        "updated_at": "2026-08-17T16:45:00Z",
        "mergeable": True,
        "additions": 342,
        "deletions": 28,
        "changed_files": 12,
        "labels": ["feature", "auth"],
        "reviewers": ["bob", "charlie"],
        "url": f"https://github.com/{repo}/pull/{pr_number}",
    }
    return json.dumps({"pull_request": pr})


@server.tool(
    name="github_create_issue",
    description="Create a new issue in a GitHub repository",
)
async def github_create_issue(
    repo: str = "org/repo",
    title: str = "New issue",
    body: str = "",
    labels: str = "",
) -> str:
    issue = {
        "number": 200,
        "title": title,
        "body": body,
        "state": "open",
        "labels": [l.strip() for l in labels.split(",") if l.strip()] if labels else [],
        "author": "ella-agent",
        "created_at": "2026-08-18T10:00:00Z",
        "url": f"https://github.com/{repo}/issues/200",
    }
    return json.dumps({"created": True, "issue": issue})


if __name__ == "__main__":
    import asyncio

    asyncio.run(server.run_stdio_async())
