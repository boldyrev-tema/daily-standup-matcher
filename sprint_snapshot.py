import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime

from credentials import load_credential

JIRA_CREDENTIALS_PATH = "~/.credentials/jira_credentials.env"
DEFAULT_JQL_TEMPLATE = "project = {project_key} AND sprint in openSprints() ORDER BY updated DESC"


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    assignee: str
    status: str
    updated_at: datetime
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    created: datetime | None = None
    url: str | None = None
    # Jira's statusCategory.key ("new" / "indeterminate" / "done") — stable
    # across projects and locales, unlike status names. Optional: absent
    # when a snapshot predates this field, agenda.py then falls back to
    # matching status names against CLOSED_STATUSES.
    status_category: str | None = None


# Imported here, after Task is defined, not at the top of the file:
# jira_client.py does `from sprint_snapshot import Task`, which would be a
# circular import if this ran before Task existed in this module's
# namespace.
import jira_client  # noqa: E402


def load_sprint(path: str) -> list[Task]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [
        Task(
            key=item["key"],
            title=item["title"],
            assignee=item["assignee"],
            status=item["status"],
            updated_at=datetime.fromisoformat(item["updated_at"]),
            priority=item.get("priority"),
            labels=item.get("labels", []),
            created=datetime.fromisoformat(item["created"]) if item.get("created") else None,
            url=item.get("url"),
            status_category=item.get("status_category"),
        )
        for item in raw
    ]


def load_current_sprint(
    fixture_path: str, fallback_team: list[str], credentials_path: str = JIRA_CREDENTIALS_PATH
) -> tuple[list[Task], list[str]]:
    """The one entry point every run_*.py should call instead of
    load_sprint(fixture_path) directly. Rinat, real call, 3 сен: "нужно
    всегда заранее адженду разговора создавать иначе он не понимает о чём
    речь" — without this, a human had to hand-build a JSON snapshot before
    every call. Falls back to the local fixture + the caller's own
    hardcoded team whenever live Jira isn't set up or fails, so nothing
    without a credentials file (including this repo's own tests/demo) is
    affected. Never raises — a bad JQL, an expired token, a network blip
    degrades to the fixture with a stderr note, same philosophy as
    hints.py's degrade-on-error.
    """
    full_path = os.path.expanduser(credentials_path)
    if not os.path.exists(full_path):
        return load_sprint(fixture_path), fallback_team

    try:
        base_url = load_credential(credentials_path, "JIRA_BASE_URL")
        email = load_credential(credentials_path, "JIRA_EMAIL")
        api_token = load_credential(credentials_path, "JIRA_API_TOKEN")
        try:
            jql = load_credential(credentials_path, "JIRA_JQL")
        except ValueError:
            project_key = load_credential(credentials_path, "JIRA_PROJECT_KEY")
            jql = DEFAULT_JQL_TEMPLATE.format(project_key=project_key)
        team_raw = load_credential(credentials_path, "JIRA_TEAM")
        team = [name.strip() for name in team_raw.split(",") if name.strip()]

        tasks = jira_client.fetch_sprint_tasks(base_url, email, api_token, jql)
        return tasks, team
    except Exception as e:
        print(f"Live Jira fetch failed ({e}) — falling back to {fixture_path}", file=sys.stderr)
        return load_sprint(fixture_path), fallback_team
