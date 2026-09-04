import json
import os
from datetime import datetime, timezone

import requests

from hints import MODEL_CHAIN, OPENROUTER_ENDPOINT, get_hints
from meeting import Meeting
from sprint_snapshot import Task

RECAPS_DIR = "recaps"

OVERVIEW_SYSTEM_PROMPT = (
    "Ты анализируешь транскрипт рабочего дейлика (утренней встречи команды). "
    "Сначала одной фразой обобщи, о чём вообще был весь разговор целиком. "
    "Затем выдели короткий список тем, которые реально обсуждались — "
    "не только то, что привязано к конкретным задачам в Jira, а вообще всё "
    "содержательное.\n\n"
    "Верни СТРОГО JSON-объект вида:\n"
    '{"gist": "одна фраза-обобщение всего разговора", '
    '"topics": ["короткая тема 1", "короткая тема 2"]}\n\n'
    "Правила:\n"
    "- gist — ровно одно предложение, не длиннее 150 знаков, обобщающее "
    "разговор целиком (не первая тема, а именно сводка всего).\n"
    "- Не пересказывай светскую беседу (приветствия, посторонние темы).\n"
    "- Каждая тема в topics — одна короткая фраза, не длиннее 80 знаков.\n"
    "- Не более 5 тем.\n"
    "- Если содержательного обсуждения не было — верни "
    '{"gist": "", "topics": []}.\n'
    "- Не придумывай ничего, чего не было в разговоре."
)


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


_EMPTY_OVERVIEW = {"gist": "", "topics": []}


def build_overview(meeting: Meeting, api_key: str) -> dict:
    """General "what was this daily about" — gist (one sentence) + topics
    (short list), independent of whether any task got recognized. The
    Granola/Fireflies-style whole-call summary, shown as a block on top of
    (not instead of) the per-task recap below it (per-task 'said' stays
    exact/task-anchored; this is coarser but survives even when nothing
    matched the agenda). Returns {"gist": str, "topics": list[str]}.

    Best-effort like get_hints() itself: any failure (network, parsing,
    schema) falls through to the next model in the chain, and _EMPTY_OVERVIEW
    on total failure rather than raising — a missing overview must never
    block the per-task recap that _save_recap_on_close already builds.
    """
    text = "\n".join(f"{line.who or '?'}: {line.text}" for line in meeting.lines)
    if not text.strip():
        return dict(_EMPTY_OVERVIEW)

    base_payload = {
        "messages": [
            {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"Транскрипт дейлика:\n{text}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    for model, extra in MODEL_CHAIN:
        payload = {**base_payload, "model": model, **extra}
        try:
            resp = requests.post(
                OPENROUTER_ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            topics = parsed.get("topics", [])
            gist = parsed.get("gist", "")
            if not isinstance(topics, list) or not isinstance(gist, str):
                continue
            return {
                "gist": gist,
                "topics": [t for t in topics if isinstance(t, str) and t][:5],
            }
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError):
            continue
    return dict(_EMPTY_OVERVIEW)


def save_recap(records: list[dict], overview: dict | None = None, dir: str = RECAPS_DIR) -> str:
    os.makedirs(dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = os.path.join(dir, now.strftime("%Y-%m-%d_%H-%M-%S") + ".json")
    data = {"generated_at": now.isoformat(), "overview": overview or dict(_EMPTY_OVERVIEW), "tasks": records}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _format_recap_label(filename: str) -> str:
    stem = filename[:-len(".json")] if filename.endswith(".json") else filename
    try:
        date_part, _, time_part = stem.partition("_")
        hh, mm, _ss = time_part.split("-")
        return f"{date_part} {hh}:{mm}"
    except ValueError:
        return stem


def list_recaps(dir: str = RECAPS_DIR) -> list[dict]:
    """All saved recaps, newest first — [{"filename", "label"}], for the
    picker in second_screen.html's panel (Granola/Fireflies-style: browse
    past dailies by date, not just the single most recent one)."""
    if not os.path.isdir(dir):
        return []
    files = sorted((f for f in os.listdir(dir) if f.endswith(".json")), reverse=True)
    return [{"filename": f, "label": _format_recap_label(f)} for f in files]


def read_recap(filename: str, dir: str = RECAPS_DIR) -> dict | None:
    """One recap by filename, as picked from list_recaps(). Path-traversal
    guarded the same way meeting_copilot's live_copilot_poc read_summary()
    is — filename comes from the JS/pywebview bridge, never trust it as a
    bare path component."""
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        return None
    path = os.path.join(dir, filename)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
