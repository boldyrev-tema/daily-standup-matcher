# tests/test_replay_driver.py
from agenda import build_agenda
from sprint_snapshot import load_sprint
from replay_driver import replay
from match_core import match
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


def test_replay_recognizes_all_tasks_from_a_single_two_match_utterance():
    # A single utterance can legitimately match two different agenda tasks at
    # once: one via the explicit-number channel (confidence 1.0) and one via
    # fuzzy title-word overlap. match() sorts its results by task recency
    # (updated_at), NOT by confidence, so the more-recently-updated task can
    # land first in the list even when it was only a fuzzy title match.
    # Confirmed directly against match_core.match() on this fixture's agenda:
    # utterance below yields two MatchResults, with the title_words match
    # (NOVA-10214, updated 2026-08-27) ordered ahead of the explicit_number
    # match (NOVA-10230, updated 2026-08-23) purely because of recency.
    # replay() must still recognize BOTH tasks, not just results[0].
    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)

    utterance = (
        "Задача 10230 подождёт, а по отчётам убираем дубли платежей от "
        "партнёров всё готово"
    )
    results = match(utterance, agenda)
    assert {r.task_key for r in results} == {"NOVA-10214", "NOVA-10230"}
    assert results[0].task_key == "NOVA-10214"
    assert results[0].reason == "title_words"

    transcript = [{"speaker": "Дарья", "text": utterance}]
    meeting = replay(transcript, agenda)

    assert "NOVA-10214" in meeting.done
    assert "NOVA-10230" in meeting.done
    assert meeting.remaining_count == len(agenda) - 2


def test_replay_backfills_an_ambiguous_line_once_the_next_line_disambiguates_it():
    # Rinat, 2 сен: on his real Jira, a genuine single-utterance tie between
    # two "сделки" tasks (SITE-12160/SITE-12170) resolved on the immediately
    # following line — same shape as NOVA-10267/NOVA-10288 here, just with a
    # same-topic continuation instead of a topic switch (unlike the deliberately
    # ambiguous-and-unresolved line in sample_daily_transcript.json above).
    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)
    transcript = [
        {"speaker": "Полина", "text": "Мы выгружаем контакты в систему, но пока не уверены в какую именно."},
        {"speaker": "Полина", "text": "А, точно, это была старая система, для партнёров."},
    ]

    meeting = replay(transcript, agenda)

    assert meeting.done == ["NOVA-10267"]
    assert meeting.lines[0].task == "NOVA-10267"
    assert meeting.lines[1].task == "NOVA-10267"
