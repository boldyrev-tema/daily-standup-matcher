from datetime import datetime, timedelta, timezone

from agenda import REOPENED_STATUS, build_agenda, pick_alarm
from sprint_snapshot import Task


def _task(key, assignee, status, days_ago, now, status_category=None):
    return Task(
        key=key,
        title=f"Заголовок {key}",
        assignee=assignee,
        status=status,
        updated_at=now - timedelta(days=days_ago),
        status_category=status_category,
    )


NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def test_build_agenda_filters_by_team():
    tasks = [
        _task("A-1", "Аня", "S", 1, NOW),
        _task("A-2", "Боря", "S", 1, NOW),
    ]
    result = build_agenda(tasks, team=["Аня"])
    assert [t.key for t in result] == ["A-1"]


def test_build_agenda_sorts_by_recency_descending():
    old = _task("A-1", "Аня", "S", 5, NOW)
    new = _task("A-2", "Аня", "S", 1, NOW)
    result = build_agenda([old, new], team=["Аня"])
    assert [t.key for t in result] == ["A-2", "A-1"]


def test_build_agenda_excludes_closed_statuses():
    # Rinat, 31 авг, real sprint run: build_agenda took the freshest six by
    # assignee regardless of status — on his real sprint three of six rows
    # would have been "Закрыто"/"Обработано" (finished, nothing to discuss).
    closed1 = _task("A-1", "Аня", "Закрыто", 1, NOW)
    closed2 = _task("A-2", "Аня", "Обработано", 2, NOW)
    live = _task("A-3", "Аня", "В работе", 3, NOW)
    result = build_agenda([closed1, closed2, live], team=["Аня"])
    assert [t.key for t in result] == ["A-3"]


def test_build_agenda_excludes_by_status_category_when_present():
    # Rinat, 2 сен: his real Jira has "done"-category statuses under names
    # we don't have in CLOSED_STATUSES ("Reviewed", "ON REVIEW") — when
    # status_category is present it's authoritative, name matching is only
    # the fallback for tasks that don't carry it.
    reviewed = _task("A-1", "Аня", "Reviewed", 1, NOW, status_category="done")
    live = _task("A-2", "Аня", "В работе", 2, NOW, status_category="indeterminate")
    result = build_agenda([reviewed, live], team=["Аня"])
    assert [t.key for t in result] == ["A-2"]


def test_build_agenda_status_category_overrides_name_when_both_present():
    # A status named like a closed one but whose statusCategory says
    # otherwise (e.g. a project that reuses "Закрыто" for a non-final step)
    # must not be dropped — status_category wins over the name.
    task = _task("A-1", "Аня", "Закрыто", 1, NOW, status_category="indeterminate")
    result = build_agenda([task], team=["Аня"])
    assert [t.key for t in result] == ["A-1"]


def test_build_agenda_limits_to_six():
    tasks = [_task(f"A-{i}", "Аня", "S", i, NOW) for i in range(9)]
    result = build_agenda(tasks, team=["Аня"])
    assert len(result) == 6
    assert [t.key for t in result] == ["A-0", "A-1", "A-2", "A-3", "A-4", "A-5"]


def test_pick_alarm_prefers_reopened_over_stale():
    older_reopened = _task("A-1", "Аня", REOPENED_STATUS, 5, NOW)
    newer_reopened = _task("A-2", "Аня", REOPENED_STATUS, 1, NOW)
    stale = _task("A-3", "Аня", "В работе", 10, NOW)
    agenda = [older_reopened, newer_reopened, stale]
    assert pick_alarm(agenda, now=NOW) is older_reopened


def test_pick_alarm_falls_back_to_stale_when_no_reopened():
    stale = _task("A-1", "Аня", "В работе", 5, NOW)
    fresh = _task("A-2", "Аня", "В работе", 1, NOW)
    assert pick_alarm([stale, fresh], now=NOW) is stale


def test_pick_alarm_none_when_nothing_qualifies():
    fresh1 = _task("A-1", "Аня", "В работе", 1, NOW)
    fresh2 = _task("A-2", "Аня", "В работе", 2, NOW)
    assert pick_alarm([fresh1, fresh2], now=NOW) is None
