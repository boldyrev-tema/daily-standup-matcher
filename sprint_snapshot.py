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
        )
        for item in raw
    ]
