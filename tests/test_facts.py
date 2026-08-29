from datetime import datetime, timezone
from sprint_snapshot import Task
from facts import build_facts

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
