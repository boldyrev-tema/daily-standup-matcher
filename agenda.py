from datetime import datetime, timezone

from sprint_snapshot import Task

REOPENED_STATUS = "Открыто повторно"
STALE_DAYS = 4


def build_agenda(tasks: list[Task], team: list[str]) -> list[Task]:
    filtered = [t for t in tasks if t.assignee in team]
    ordered = sorted(filtered, key=lambda t: t.updated_at, reverse=True)
    return ordered[:6]


def pick_alarm(agenda: list[Task], now: datetime | None = None) -> Task | None:
    now = now or datetime.now(timezone.utc)

    reopened = [t for t in agenda if t.status == REOPENED_STATUS]
    if reopened:
        return min(reopened, key=lambda t: t.updated_at)

    stale = [t for t in agenda if (now - t.updated_at).days >= STALE_DAYS]
    if stale:
        return min(stale, key=lambda t: t.updated_at)

    return None
