# tests/test_second_screen_state.py
import json

from agenda import build_agenda, pick_alarm
from meeting import Line, Meeting
from run_second_screen import TEAM, _state_json
from sprint_snapshot import load_sprint

EXPECTED_TOP_KEYS = {"phase", "elapsed_s", "lines", "agenda", "current_task"}


def _agenda():
    tasks = load_sprint("fixtures/sprint.json")
    return build_agenda(tasks, TEAM)


def test_state_json_top_level_keys():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert set(payload.keys()) == EXPECTED_TOP_KEYS


def test_before_phase_all_tasks_in_remaining_none_done():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["agenda"]["done"] == []
    assert [r["key"] for r in payload["agenda"]["remaining"]] == [t.key for t in agenda]


def test_alarm_row_flagged_on_the_reopened_task():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    # fixtures/sprint.json has exactly one "Открыто повторно" task: NOVA-10299
    assert alarm_task.key == "NOVA-10299"
    meeting = Meeting(phase="live", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    remaining = payload["agenda"]["remaining"]
    alarm_row = next(r for r in remaining if r["key"] == "NOVA-10299")
    assert alarm_row["alarm"] is True
    assert alarm_row["annotation"] == "задачу открыли повторно"
    others = [r for r in remaining if r["key"] != "NOVA-10299"]
    assert all(r["alarm"] is False for r in others)
    assert all(r["annotation"] is None for r in others)


def test_done_tasks_move_from_remaining_to_done_in_recognition_order():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.mark_recognized("NOVA-10214")
    meeting.mark_recognized("NOVA-10201")

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert [r["key"] for r in payload["agenda"]["done"]] == ["NOVA-10214", "NOVA-10201"]
    remaining_keys = [r["key"] for r in payload["agenda"]["remaining"]]
    assert "NOVA-10214" not in remaining_keys
    assert "NOVA-10201" not in remaining_keys


def test_current_task_includes_facts_and_progressive_said():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.mark_recognized("NOVA-10214")
    meeting.set_hints(["первая строка", "вторая строка"], "вопрос?")
    meeting.reveal_next_said()

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    ct = payload["current_task"]
    assert ct["key"] == "NOVA-10214"
    assert len(ct["facts"]) >= 2
    assert ct["said"] == ["первая строка"]
    assert ct["ask"] == "вопрос?"


def test_current_task_is_none_before_recognition():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["current_task"] is None


def test_lines_carry_hit_words_and_task_key():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.add_line(Line(t=1.0, who="Дарья", text="возьму 214 в работу", task="NOVA-10214", hit_words=["214"]))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["lines"][0]["task"] == "NOVA-10214"
    assert payload["lines"][0]["hit_words"] == ["214"]
