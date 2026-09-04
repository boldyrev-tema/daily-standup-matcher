import json
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests

from meeting import Line, Meeting
from sprint_snapshot import Task
from recap import build_overview, build_recap, save_recap, list_recaps, read_recap

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


def test_build_recap_includes_untagged_lines_between_recognition_points():
    # Real matching pipeline: only the ONE utterance whose own text matched
    # gets .task set (see run_second_screen.py's _process_turn) — the
    # conversational follow-up around it doesn't. A recap that only kept
    # .task-tagged lines would see just the trigger line and miss the
    # actual discussion.
    lines = [
        Line(t=1.0, who="Дарья", text="Дубли платежей почти убраны", task="NOVA-1"),
        Line(t=3.0, who="Максим", text="Отлично, когда сможешь смёржить?", task=None),
        Line(t=4.0, who="Дарья", text="Сегодня вечером", task=None),
        Line(t=10.0, who="Максим", text="Экспорт в CSV готов", task="NOVA-2"),
    ]
    meeting = _meeting_with(lines, done=["NOVA-1", "NOVA-2"])
    calls = []

    def fake_get_hints(task_lines, task, api_key, lookback_seconds=None):
        calls.append((task.key, [l.text for l in task_lines]))
        return ([f"said about {task.key}"], None)

    with patch("recap.get_hints", side_effect=fake_get_hints):
        build_recap(meeting, [TASK_A, TASK_B], api_key="fake")

    assert calls[0] == ("NOVA-1", [
        "Дубли платежей почти убраны",
        "Отлично, когда сможешь смёржить?",
        "Сегодня вечером",
    ])
    assert calls[1] == ("NOVA-2", ["Экспорт в CSV готов"])


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
    assert data["overview"] == {"gist": "", "topics": []}
    assert "generated_at" in data


def test_save_recap_includes_overview_when_given(tmp_path):
    overview = {"gist": "Обсудили релиз и отчёты", "topics": ["Обсудили релиз"]}
    path = save_recap([], overview=overview, dir=str(tmp_path))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["overview"] == overview


def _mock_openrouter_response(content_dict):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}]
    }
    return mock_resp


def test_build_overview_returns_empty_overview_for_empty_meeting():
    meeting = Meeting()
    assert build_overview(meeting, api_key="fake") == {"gist": "", "topics": []}


@patch("recap.requests.post")
def test_build_overview_returns_gist_and_topics_from_response(mock_post):
    mock_post.return_value = _mock_openrouter_response(
        {
            "gist": "Обсудили релиз и договорились про митинг",
            "topics": ["Обсудили релиз", "Договорились про митинг"],
        }
    )
    meeting = _meeting_with(
        [Line(t=1.0, who="Дарья", text="Когда релиз?", task=None)], done=[]
    )
    overview = build_overview(meeting, api_key="fake")
    assert overview == {
        "gist": "Обсудили релиз и договорились про митинг",
        "topics": ["Обсудили релиз", "Договорились про митинг"],
    }


@patch("recap.requests.post")
def test_build_overview_falls_back_across_model_chain_on_failure(mock_post):
    # First two models in the chain fail (network), third succeeds — same
    # resilience contract as hints.get_hints, see that module's MODEL_CHAIN.
    mock_post.side_effect = [
        requests.exceptions.ConnectionError("boom"),
        requests.exceptions.ConnectionError("boom"),
        _mock_openrouter_response({"gist": "Кратко о звонке", "topics": ["Тема после фолбэка"]}),
    ]
    meeting = _meeting_with(
        [Line(t=1.0, who="Дарья", text="Что-то обсудили", task=None)], done=[]
    )
    overview = build_overview(meeting, api_key="fake")
    assert overview == {"gist": "Кратко о звонке", "topics": ["Тема после фолбэка"]}
    assert mock_post.call_count == 3


@patch("recap.requests.post")
def test_build_overview_returns_empty_overview_when_all_models_fail(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")
    meeting = _meeting_with(
        [Line(t=1.0, who="Дарья", text="Что-то обсудили", task=None)], done=[]
    )
    assert build_overview(meeting, api_key="fake") == {"gist": "", "topics": []}


def test_list_recaps_returns_empty_list_when_dir_missing(tmp_path):
    assert list_recaps(dir=str(tmp_path / "nope")) == []


def test_list_recaps_returns_empty_list_when_dir_empty(tmp_path):
    assert list_recaps(dir=str(tmp_path)) == []


def test_list_recaps_returns_newest_first_with_readable_labels(tmp_path):
    (tmp_path / "2026-09-01_10-00-00.json").write_text("{}", encoding="utf-8")
    (tmp_path / "2026-09-02_11-30-00.json").write_text("{}", encoding="utf-8")
    result = list_recaps(dir=str(tmp_path))
    assert result == [
        {"filename": "2026-09-02_11-30-00.json", "label": "2026-09-02 11:30"},
        {"filename": "2026-09-01_10-00-00.json", "label": "2026-09-01 10:00"},
    ]


def test_read_recap_returns_file_contents(tmp_path):
    data = {"generated_at": "2026-09-02T10:00:00+00:00",
            "overview": {"gist": "g", "topics": []},
            "tasks": [{"key": "NEW", "title": "New", "said": ["y"]}]}
    (tmp_path / "2026-09-02_10-00-00.json").write_text(json.dumps(data), encoding="utf-8")
    result = read_recap("2026-09-02_10-00-00.json", dir=str(tmp_path))
    assert result == data


def test_read_recap_returns_none_for_missing_file(tmp_path):
    assert read_recap("nope.json", dir=str(tmp_path)) is None


def test_read_recap_rejects_path_traversal(tmp_path):
    (tmp_path.parent / "secret.json").write_text("{}", encoding="utf-8")
    assert read_recap("../secret.json", dir=str(tmp_path)) is None
    assert read_recap("/etc/passwd", dir=str(tmp_path)) is None
