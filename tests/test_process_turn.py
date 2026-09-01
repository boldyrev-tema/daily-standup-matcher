from datetime import datetime, timezone

import run_second_screen
from meeting import Meeting
from run_second_screen import _process_turn
from sprint_snapshot import Task

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _task(key, title):
    return Task(key=key, title=title, assignee="Дарья", status="В работе", updated_at=NOW)


class _FakeWindow:
    def __init__(self):
        self.calls = 0

    def evaluate_js(self, script):
        self.calls += 1


def test_process_turn_recognizes_task_and_fetches_hints(monkeypatch):
    # Locks down the extraction from _run_replay's old inline loop body —
    # match -> Meeting/Line bookkeeping -> render -> hints, shared now with
    # the live-mic path (_run_live).
    monkeypatch.setattr(
        run_second_screen, "get_hints", lambda lines, task, api_key: (["уже сказали"], "спроси про Х")
    )
    agenda = [_task("A-1", "Отчёты — убираем дубли платежей от партнёров")]
    window = _FakeWindow()
    meeting = Meeting(phase="live", remaining_count=1)

    pending = _process_turn(
        "Дарья", "убираем дубли платежей от партнёров", 1.0, agenda, meeting, None, "key", window, None
    )

    assert pending is None
    assert meeting.lines[0].task == "A-1"
    assert meeting.done == ["A-1"]
    assert meeting.said == ["уже сказали"]
    assert meeting.ask == "спроси про Х"
    assert window.calls >= 2  # at least the recognition render + the hints render


def test_process_turn_stays_silent_and_sets_pending_on_ambiguous_tie():
    tasks = [
        _task("B-1", "Выгрузка контактов в старую систему"),
        _task("B-2", "Выгрузка контактов в новую систему"),
    ]
    window = _FakeWindow()
    meeting = Meeting(phase="live", remaining_count=2)

    pending = _process_turn(
        "Полина", "надо доделать выгрузку контактов в систему", 1.0, tasks, meeting, None, "key", window, None
    )

    assert pending is not None
    _, candidates = pending
    assert meeting.lines[0].task is None
    assert {t.key for t in candidates} == {"B-1", "B-2"}


def test_process_turn_backfills_pending_line_via_next_turn(monkeypatch):
    monkeypatch.setattr(run_second_screen, "get_hints", lambda lines, task, api_key: ([], None))
    tasks = [
        _task("B-1", "Выгрузка контактов в старую систему"),
        _task("B-2", "Выгрузка контактов в новую систему"),
    ]
    window = _FakeWindow()
    meeting = Meeting(phase="live", remaining_count=2)

    pending = _process_turn(
        "Полина", "надо доделать выгрузку контактов в систему", 1.0, tasks, meeting, None, "key", window, None
    )
    pending = _process_turn(
        "Полина", "именно в старую систему для партнёров", 2.0, tasks, meeting, None, "key", window, pending
    )

    assert pending is None
    assert meeting.lines[0].task == "B-1"
    assert meeting.lines[1].task == "B-1"
