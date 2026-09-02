import json
import os
from datetime import datetime, timezone

from hints import get_hints
from meeting import Meeting
from sprint_snapshot import Task

RECAPS_DIR = "recaps"


def build_recap(meeting: Meeting, agenda: list[Task], api_key: str) -> list[dict]:
    """One record per task in meeting.done that has something to say.
    Sourced from meeting.lines (append-only, never overwritten) rather than
    the live meeting.said/meeting.ask fields, which get reset every time
    mark_recognized() moves to a new task — see
    docs/superpowers/specs/2026-09-02-daily-recap-design.md.
    """
    tasks_by_key = {task.key: task for task in agenda}
    records = []
    for key in meeting.done:
        task = tasks_by_key.get(key)
        if task is None:
            continue
        task_lines = [line for line in meeting.lines if line.task == key]
        said, _ask = get_hints(task_lines, task, api_key, lookback_seconds=None)
        if not said:
            continue
        records.append({"key": task.key, "title": task.title, "said": said})
    return records


def save_recap(records: list[dict], dir: str = RECAPS_DIR) -> str:
    os.makedirs(dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = os.path.join(dir, now.strftime("%Y-%m-%d_%H-%M-%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(), "tasks": records}, f, ensure_ascii=False, indent=2)
    return path


def latest_recap(dir: str = RECAPS_DIR) -> dict | None:
    if not os.path.isdir(dir):
        return None
    files = sorted(f for f in os.listdir(dir) if f.endswith(".json"))
    if not files:
        return None
    with open(os.path.join(dir, files[-1]), encoding="utf-8") as f:
        return json.load(f)
