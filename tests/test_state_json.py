# tests/test_state_json.py
import json

from agenda import build_agenda
from meeting import Line, Meeting
from run_polosa_replay import TEAM, _state_json
from sprint_snapshot import load_sprint

EXPECTED_TOP_KEYS = {"phase", "elapsed_s", "remaining_count", "last_line", "current_task", "ask"}


def _agenda():
    tasks = load_sprint("fixtures/sprint.json")
    return build_agenda(tasks, TEAM)


def test_state_json_top_level_keys_match_the_polosa_html_contract():
    agenda = _agenda()
    meeting = Meeting(phase="live", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda))

    assert set(payload.keys()) == EXPECTED_TOP_KEYS


def test_state_json_last_line_shape_when_present():
    agenda = _agenda()
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.add_line(Line(t=1.0, who="Дарья", text="Привет", task=None))

    payload = json.loads(_state_json(meeting, agenda))

    assert payload["last_line"] is not None
    assert set(payload["last_line"].keys()) == {"who", "text"}


def test_state_json_current_task_shape_when_present():
    agenda = _agenda()
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.add_line(Line(t=1.0, who="Дарья", text="Привет", task=agenda[0].key))
    meeting.mark_recognized(agenda[0].key)

    payload = json.loads(_state_json(meeting, agenda))

    assert payload["current_task"] is not None
    assert set(payload["current_task"].keys()) == {"title", "first_fact"}


def test_state_json_last_line_and_current_task_are_none_before_any_lines():
    agenda = _agenda()
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda))

    assert payload["last_line"] is None
    assert payload["current_task"] is None
