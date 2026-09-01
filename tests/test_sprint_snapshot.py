from datetime import datetime, timezone

from sprint_snapshot import Task, load_sprint


def test_load_sprint_reads_fixture():
    tasks = load_sprint("fixtures/sprint.json")
    assert len(tasks) == 6
    first = tasks[0]
    assert first.key == "NOVA-10201"
    assert first.title == "Сделки — объединяем карточки клиентов после импорта"
    assert first.assignee == "Дарья Ковалёва"
    assert first.status == "Тестирование"
    assert first.updated_at == datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)


def test_task_is_a_plain_dataclass():
    t = Task(
        key="X-1",
        title="Заголовок",
        assignee="Кто-то",
        status="Статус",
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert t.key == "X-1"


def test_task_optional_fields_default_empty():
    t = Task(
        key="NOVA-1", title="x", assignee="y", status="z",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert t.priority is None
    assert t.labels == []
    assert t.created is None
    assert t.url is None
    assert t.status_category is None


def test_task_optional_fields_can_be_set():
    t = Task(
        key="NOVA-1", title="x", assignee="y", status="z",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        priority="критический",
        labels=["релиз_текущий_спринт"],
        created=datetime(2026, 7, 1, tzinfo=timezone.utc),
        url="https://example.invalid/NOVA-1",
        status_category="done",
    )
    assert t.priority == "критический"
    assert t.labels == ["релиз_текущий_спринт"]
    assert t.created == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert t.url == "https://example.invalid/NOVA-1"
    assert t.status_category == "done"


def test_load_sprint_reads_status_category_when_present():
    tasks = load_sprint("fixtures/sprint.json")
    by_key = {t.key: t for t in tasks}
    # NOVA-10230 is "Backlog" — Jira's statusCategory.key for a not-started
    # status is "new", distinct from "indeterminate" (in progress) and
    # "done" (finished, regardless of the status's display name).
    assert by_key["NOVA-10230"].status_category == "new"
    assert by_key["NOVA-10214"].status_category == "indeterminate"
