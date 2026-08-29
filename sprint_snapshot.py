import json
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    assignee: str
    status: str
    updated_at: datetime


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
        )
        for item in raw
    ]
