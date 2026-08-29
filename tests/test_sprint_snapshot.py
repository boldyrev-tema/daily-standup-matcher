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
