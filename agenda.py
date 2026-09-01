from datetime import datetime, timezone

from sprint_snapshot import Task

REOPENED_STATUS = "Открыто повторно"
STALE_DAYS = 4

# Fallback only, used when a task carries no status_category (Rinat, 2 сен:
# his real Jira has "done"-category statuses under names we don't have here
# — "Reviewed", "ON REVIEW" — so name matching alone under-counts closed
# tasks). Reconstructed from Rinat's real-sprint feedback (31 авг), not his
# full Jira workflow. Extend this if a real sprint surfaces more names.
CLOSED_STATUSES = frozenset({"Закрыто", "Обработано"})


def _is_done(task: Task) -> bool:
    if task.status_category is not None:
        return task.status_category == "done"
    return task.status in CLOSED_STATUSES


def build_agenda(tasks: list[Task], team: list[str]) -> list[Task]:
    filtered = [t for t in tasks if t.assignee in team and not _is_done(t)]
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
