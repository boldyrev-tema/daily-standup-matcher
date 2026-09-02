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

    Lines are grouped by TIME SEGMENT between consecutive recognition
    points, not by exact line.task match. The matcher (see
    run_second_screen.py's _process_turn) only tags the ONE utterance whose
    own text triggered recognition — clarifications and follow-up chatter
    about the same task get line.task=None. A segment for a task starts at
    the timestamp of its first recognized line and runs up to the next
    task's first recognized line (or to the end of the meeting), so all the
    surrounding discussion is captured, not just the trigger line.
    """
    tasks_by_key = {task.key: task for task in agenda}

    recognized_at: dict[str, float] = {}
    for line in meeting.lines:
        if line.task is None:
            continue
        if line.task not in recognized_at:
            recognized_at[line.task] = line.t

    records = []
    for i, key in enumerate(meeting.done):
        task = tasks_by_key.get(key)
        if task is None:
            continue
        start = recognized_at.get(key)
        if start is None:
            continue

        end = None
        for later_key in meeting.done[i + 1:]:
            if later_key in recognized_at:
                end = recognized_at[later_key]
                break

        if end is None:
            task_lines = [line for line in meeting.lines if line.t >= start]
        else:
            task_lines = [line for line in meeting.lines if start <= line.t < end]

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
