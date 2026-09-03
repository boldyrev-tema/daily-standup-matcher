"""Read-only Jira Cloud client. Rinat's techspec, rule 8: «В Jira ничего не
изменено» — this file makes exactly one kind of call, a search, and MUST
NEVER grow a write path (issue update/transition/comment). If you're adding
a call here, it should be a GET-shaped read, even though the search
endpoint itself is a POST.

The old GET /rest/api/3/search is fully removed from Jira Cloud (confirmed
3 сен 2026) — this uses the current POST /rest/api/3/search/jql, which
paginates via `nextPageToken` in the request/response body instead of the
old `startAt`/`total`. Auth is HTTP Basic with (email, API token), same
shape already working in the sibling meeting_copilot project's
jira_client.py (which writes tickets — this one only ever reads).
"""
from datetime import datetime

import requests

from sprint_snapshot import Task

SEARCH_PATH = "/rest/api/3/search/jql"
FIELDS = ["summary", "assignee", "status", "updated", "created", "priority", "labels"]
PAGE_SIZE = 100


def search_issues(base_url: str, email: str, api_token: str, jql: str) -> list[dict]:
    """Raw paginated issue search. Returns Jira's own issue dicts
    (fields.summary/assignee/status/... shape), unmapped."""
    issues: list[dict] = []
    body = {"jql": jql, "fields": FIELDS, "maxResults": PAGE_SIZE}
    while True:
        resp = requests.post(f"{base_url}{SEARCH_PATH}", json=body, auth=(email, api_token), timeout=30)
        resp.raise_for_status()
        page = resp.json()
        issues.extend(page["issues"])
        next_token = page.get("nextPageToken")
        if page.get("isLast", True) or not next_token:
            break
        body = {**body, "nextPageToken": next_token}
    return issues


def _task_from_issue(base_url: str, issue: dict) -> Task:
    f = issue["fields"]
    assignee = f["assignee"]
    priority = f["priority"]
    return Task(
        key=issue["key"],
        title=f["summary"],
        assignee=assignee["displayName"] if assignee else "",
        status=f["status"]["name"],
        updated_at=datetime.fromisoformat(f["updated"]),
        priority=priority["name"] if priority else None,
        labels=f.get("labels") or [],
        created=datetime.fromisoformat(f["created"]) if f.get("created") else None,
        url=f"{base_url}/browse/{issue['key']}",
        status_category=f["status"]["statusCategory"]["key"],
    )


def fetch_sprint_tasks(base_url: str, email: str, api_token: str, jql: str) -> list[Task]:
    return [_task_from_issue(base_url, issue) for issue in search_issues(base_url, email, api_token, jql)]
