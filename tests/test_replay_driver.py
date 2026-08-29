# tests/test_replay_driver.py
from agenda import build_agenda
from sprint_snapshot import load_sprint
from replay_driver import replay
import json

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]


def _load_transcript():
    with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
        return json.load(f)


def test_replay_recognizes_expected_tasks_and_stays_silent_on_the_rest():
    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)
    transcript = _load_transcript()

    meeting = replay(transcript, agenda)

    # NOVA-10214 (word overlap), NOVA-10201 (number channel), NOVA-10299
    # (word overlap, also the alarm/reopened task), NOVA-10230 (word overlap)
    # recognized, in that order. NOVA-10267/NOVA-10288 stay silent — the
    # transcript line about them is deliberately ambiguous between the two
    # (omits "старую"/"новую"), same margin-gate mechanism validated on the
    # real transcript earlier in this project's history. The filler line
    # ("Ну, короче, всё окей, погнали дальше.") matches nothing.
    assert meeting.done == ["NOVA-10214", "NOVA-10201", "NOVA-10299", "NOVA-10230"]
    assert meeting.remaining_count == 2
    assert meeting.phase == "after"
    assert len(meeting.lines) == 6
