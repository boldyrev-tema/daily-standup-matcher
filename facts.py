from datetime import datetime, timezone

from sprint_snapshot import Task

CRITICAL_PRIORITY = "критический"
RELEASE_LABEL = "релиз_текущий_спринт"


def _age_label(updated_at: datetime, now: datetime) -> str:
    days = (now.date() - updated_at.date()).days
    if days <= 0:
        return "Обновлено сегодня"
    if days == 1:
        return "Обновлено вчера"
    if 2 <= days <= 4:
        return f"Обновлено {days} дня назад"
    return f"Обновлено {days} дней назад"


def build_facts(task: Task, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    lines = [f"{task.status} · {task.assignee}"]
    if task.priority == CRITICAL_PRIORITY:
        lines.append(f"Приоритет: {CRITICAL_PRIORITY}")
    if RELEASE_LABEL in task.labels:
        lines.append("Релиз в этом спринте")
    lines.append(_age_label(task.updated_at, now))
    if task.created is not None:
        lines.append(f"Создана {task.created:%d.%m}")
    return lines
