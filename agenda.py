from datetime import datetime, timezone

from sprint_snapshot import Task

REOPENED_STATUS = "Открыто повторно"
STALE_DAYS = 4

# Reconstructed from Rinat's real-sprint feedback (31 авг), not his full Jira
# workflow — closed/done statuses are project-specific and we only have his
# two named examples. Extend this if a real sprint surfaces more.
CLOSED_STATUSES = frozenset({"Закрыто", "Обработано"})


def build_agenda(tasks: list[Task], team: list[str]) -> list[Task]:
    filtered = [
        t for t in tasks if t.assignee in team and t.status not in CLOSED_STATUSES
    ]
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
