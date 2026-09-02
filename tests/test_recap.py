import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

from meeting import Line, Meeting
from sprint_snapshot import Task
from recap import build_recap, save_recap, latest_recap

TASK_A = Task(
    key="NOVA-1", title="Дубли платежей", assignee="Дарья",
    status="В работе", updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
)
TASK_B = Task(
    key="NOVA-2", title="Экспорт в CSV", assignee="Максим",
    status="В работе", updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
)


def _meeting_with(lines: list[Line], done: list[str]) -> Meeting:
    meeting = Meeting()
    for line in lines:
        meeting.add_line(line)
    meeting.done = done
    return meeting


def test_build_recap_groups_lines_by_task_and_calls_get_hints_per_task():
    lines = [
        Line(t=1.0, who="Дарья", text="Дубли почти убраны", task="NOVA-1"),
        Line(t=5.0, who="Максим", text="Экспорт готов", task="NOVA-2"),
    ]
    meeting = _meeting_with(lines, done=["NOVA-1", "NOVA-2"])
    calls = []

    def fake_get_hints(task_lines, task, api_key, lookback_seconds=None):
        calls.append((task.key, [l.text for l in task_lines], lookback_seconds))
        return ([f"said about {task.key}"], None)

    with patch("recap.get_hints", side_effect=fake_get_hints):
        records = build_recap(meeting, [TASK_A, TASK_B], api_key="fake")

    assert records == [
        {"key": "NOVA-1", "title": "Дубли платежей", "said": ["said about NOVA-1"]},
        {"key": "NOVA-2", "title": "Экспорт в CSV", "said": ["said about NOVA-2"]},
    ]
    assert calls[0] == ("NOVA-1", ["Дубли почти убраны"], None)
    assert calls[1] == ("NOVA-2", ["Экспорт готов"], None)


def test_build_recap_skips_tasks_with_empty_said():
    lines = [Line(t=1.0, who="Дарья", text="...", task="NOVA-1")]
    meeting = _meeting_with(lines, done=["NOVA-1"])
    with patch("recap.get_hints", return_value=([], None)):
        records = build_recap(meeting, [TASK_A], api_key="fake")
    assert records == []


def test_build_recap_skips_a_done_key_not_present_in_agenda():
    lines = [Line(t=1.0, who="Дарья", text="...", task="GONE-1")]
    meeting = _meeting_with(lines, done=["GONE-1"])
    with patch("recap.get_hints", return_value=(["x"], None)) as mock_get_hints:
        records = build_recap(meeting, [TASK_A], api_key="fake")
    assert records == []
    mock_get_hints.assert_not_called()


def test_save_recap_writes_json_with_generated_at_and_tasks(tmp_path):
    records = [{"key": "NOVA-1", "title": "Дубли платежей", "said": ["..."]}]
    path = save_recap(records, dir=str(tmp_path))
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["tasks"] == records
    assert "generated_at" in data


def test_latest_recap_returns_none_when_dir_missing(tmp_path):
    assert latest_recap(dir=str(tmp_path / "nope")) is None


def test_latest_recap_returns_none_when_dir_empty(tmp_path):
    assert latest_recap(dir=str(tmp_path)) is None


def test_latest_recap_returns_most_recent_file(tmp_path):
    with open(tmp_path / "2026-09-01_10-00-00.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": "2026-09-01T10:00:00+00:00",
                    "tasks": [{"key": "OLD", "title": "Old", "said": ["x"]}]}, f)
    with open(tmp_path / "2026-09-02_10-00-00.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": "2026-09-02T10:00:00+00:00",
                    "tasks": [{"key": "NEW", "title": "New", "said": ["y"]}]}, f)
    result = latest_recap(dir=str(tmp_path))
    assert result["tasks"][0]["key"] == "NEW"
