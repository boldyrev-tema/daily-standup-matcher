from datetime import datetime, timezone

from match_core import MatchResult
from meeting import Line, Meeting
from run_second_screen import _apply_pending
from sprint_snapshot import Task


def _task(key, title):
    return Task(
        key=key,
        title=title,
        assignee="Хава",
        status="В работе",
        updated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


TASK_OLD = _task("OLD-1", "Выгрузка контактов в старую систему")
TASK_NEW = _task("NEW-1", "Выгрузка контактов в новую систему")
AGENDA = [TASK_OLD, TASK_NEW]


def _pending_line():
    return Line(t=1.0, who="Хава", text="надо доделать выгрузку контактов в систему")


def test_apply_pending_passes_through_when_nothing_pending():
    meeting = Meeting()
    primary = MatchResult("OLD-1", 0.8, "title_words")

    result_primary, pending = _apply_pending(None, primary, "неважно что", AGENDA, meeting)

    assert result_primary is primary
    assert pending is None


def test_apply_pending_backfills_when_this_turn_independently_matches_a_tied_task():
    line = _pending_line()
    meeting = Meeting()
    primary = MatchResult("OLD-1", 0.9, "title_words", hit_words=["старую"])

    result_primary, pending = _apply_pending((line, [TASK_OLD, TASK_NEW]), primary, "старую доделал", AGENDA, meeting)

    assert result_primary is primary
    assert pending is None
    assert line.task == "OLD-1"
    assert line.hit_words == ["старую"]


def test_apply_pending_resolves_via_merged_retry_when_this_turn_alone_matches_nothing():
    line = _pending_line()
    meeting = Meeting(remaining_count=2)

    result_primary, pending = _apply_pending(
        (line, [TASK_OLD, TASK_NEW]),
        None,
        "именно в старую систему, для партнёров",
        AGENDA,
        meeting,
    )

    assert result_primary is not None
    assert result_primary.task_key == "OLD-1"
    assert pending is None
    assert line.task == "OLD-1"
    assert line.hit_words == result_primary.hit_words
    assert "OLD-1" in meeting.done


def test_apply_pending_leaves_line_unresolved_when_still_ambiguous():
    line = _pending_line()
    meeting = Meeting()

    result_primary, pending = _apply_pending(
        (line, [TASK_OLD, TASK_NEW]), None, "ну давайте после обеда", AGENDA, meeting
    )

    assert result_primary is None
    assert pending is None
    assert line.task is None
    assert meeting.done == []


def test_apply_pending_clears_without_backfill_when_this_turn_matches_an_unrelated_task():
    line = _pending_line()
    meeting = Meeting()
    other_task = _task("OTHER-1", "Починить биллинг")
    primary = MatchResult("OTHER-1", 0.9, "title_words")

    result_primary, pending = _apply_pending(
        (line, [TASK_OLD, TASK_NEW]), primary, "починим биллинг", [TASK_OLD, TASK_NEW, other_task], meeting
    )

    assert result_primary is primary
    assert pending is None
    assert line.task is None
