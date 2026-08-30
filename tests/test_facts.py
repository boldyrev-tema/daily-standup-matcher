from datetime import datetime, timezone
from sprint_snapshot import Task
from agenda import REOPENED_STATUS
from facts import age_label, agenda_row, build_facts

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)


def _task(**overrides):
    base = dict(
        key="NOVA-1", title="x", assignee="Дарья Ковалёва", status="В работе",
        updated_at=datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Task(**base)


def test_minimal_task_gives_two_lines():
    facts = build_facts(_task(), now=NOW)
    assert facts == ["В работе · Дарья Ковалёва", "Обновлено вчера"]


def test_critical_priority_adds_line():
    facts = build_facts(_task(priority="критический"), now=NOW)
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Приоритет: критический",
        "Обновлено вчера",
    ]


def test_non_critical_priority_adds_nothing():
    facts = build_facts(_task(priority="средний"), now=NOW)
    assert facts == ["В работе · Дарья Ковалёва", "Обновлено вчера"]


def test_release_label_adds_line():
    facts = build_facts(_task(labels=["релиз_текущий_спринт"]), now=NOW)
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Релиз в этом спринте",
        "Обновлено вчера",
    ]


def test_created_adds_line_at_the_end():
    facts = build_facts(
        _task(created=datetime(2026, 8, 1, tzinfo=timezone.utc)), now=NOW
    )
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Обновлено вчера",
        "Создана 01.08",
    ]


def test_all_five_lines_in_order():
    facts = build_facts(
        _task(
            priority="критический",
            labels=["релиз_текущий_спринт"],
            created=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        now=NOW,
    )
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Приоритет: критический",
        "Релиз в этом спринте",
        "Обновлено вчера",
        "Создана 01.08",
    ]


def test_age_label_today_vs_days_ago():
    assert build_facts(_task(updated_at=NOW), now=NOW)[-1] == "Обновлено сегодня"
    two_days_ago = _task(updated_at=datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc))
    assert build_facts(two_days_ago, now=NOW)[-1] == "Обновлено 2 дня назад"
    five_days_ago = _task(updated_at=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc))
    assert build_facts(five_days_ago, now=NOW)[-1] == "Обновлено 5 дней назад"


def test_age_label_is_public_and_matches_build_facts_wording():
    assert age_label(datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc), NOW) == "Обновлено вчера"
    assert age_label(NOW, NOW) == "Обновлено сегодня"


def test_agenda_row_basic_line_no_alarm():
    row, annotation = agenda_row(_task(), is_alarm=False, now=NOW)
    assert row == "В работе · Дарья Ковалёва · Обновлено вчера"
    assert annotation is None


def test_agenda_row_alarm_and_reopened_gets_annotation():
    task = _task(status=REOPENED_STATUS)
    row, annotation = agenda_row(task, is_alarm=True, now=NOW)
    assert row == f"{REOPENED_STATUS} · Дарья Ковалёва · Обновлено вчера"
    assert annotation == "задачу открыли повторно"


def test_agenda_row_alarm_but_not_reopened_gets_no_annotation():
    # is_alarm=True can also mean "stale >= 4 days", which has no separate
    # annotation in the real mockup — only the reopened case does.
    task = _task(status="В работе")
    row, annotation = agenda_row(task, is_alarm=True, now=NOW)
    assert annotation is None


def test_agenda_row_reopened_but_not_the_alarm_task_gets_no_annotation():
    # is_alarm is decided by the caller against agenda.pick_alarm() for the
    # whole agenda — a merely-reopened task that isn't THE alarm task must
    # not get the annotation on its own.
    task = _task(status=REOPENED_STATUS)
    row, annotation = agenda_row(task, is_alarm=False, now=NOW)
    assert annotation is None
