import json
from dataclasses import dataclass, field
from datetime import datetime


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
