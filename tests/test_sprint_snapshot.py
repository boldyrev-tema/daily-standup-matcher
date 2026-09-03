from datetime import datetime, timezone

import sprint_snapshot
from sprint_snapshot import Task, load_current_sprint, load_sprint


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


FALLBACK_TEAM = ["Дарья Ковалёва", "Максим Орлов"]


def _write_credentials(path, **kv):
    path.write_text("".join(f"{k}={v}\n" for k, v in kv.items()), encoding="utf-8")


def test_load_current_sprint_falls_back_to_fixture_when_no_credentials_file(tmp_path):
    missing = tmp_path / "no_such_file.env"

    tasks, team = load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(missing))

    assert tasks == load_sprint("fixtures/sprint.json")
    assert team == FALLBACK_TEAM


def test_load_current_sprint_falls_back_when_fetch_raises(tmp_path, monkeypatch, capsys):
    creds = tmp_path / "jira_credentials.env"
    _write_credentials(
        creds, JIRA_BASE_URL="https://x.atlassian.net", JIRA_EMAIL="me@x.com",
        JIRA_API_TOKEN="tok", JIRA_PROJECT_KEY="X", JIRA_TEAM="Дарья Ковалёва",
    )
    monkeypatch.setattr(
        sprint_snapshot.jira_client, "fetch_sprint_tasks",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    tasks, team = load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(creds))

    assert tasks == load_sprint("fixtures/sprint.json")
    assert team == FALLBACK_TEAM
    assert "network down" in capsys.readouterr().err


def test_load_current_sprint_falls_back_when_team_not_configured(tmp_path, monkeypatch, capsys):
    creds = tmp_path / "jira_credentials.env"
    _write_credentials(
        creds, JIRA_BASE_URL="https://x.atlassian.net", JIRA_EMAIL="me@x.com",
        JIRA_API_TOKEN="tok", JIRA_PROJECT_KEY="X",
    )
    monkeypatch.setattr(sprint_snapshot.jira_client, "fetch_sprint_tasks", lambda *a, **kw: [])

    tasks, team = load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(creds))

    assert tasks == load_sprint("fixtures/sprint.json")
    assert team == FALLBACK_TEAM
    assert "JIRA_TEAM" in capsys.readouterr().err


def test_load_current_sprint_uses_live_tasks_and_team_on_success(tmp_path, monkeypatch):
    creds = tmp_path / "jira_credentials.env"
    _write_credentials(
        creds, JIRA_BASE_URL="https://x.atlassian.net", JIRA_EMAIL="me@x.com",
        JIRA_API_TOKEN="tok", JIRA_PROJECT_KEY="X",
        JIRA_TEAM="Хава Гермиханова, Владислав",
    )
    live_task = Task(key="SITE-1", title="t", assignee="Хава Гермиханова", status="s",
                      updated_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(sprint_snapshot.jira_client, "fetch_sprint_tasks", lambda *a, **kw: [live_task])

    tasks, team = load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(creds))

    assert tasks == [live_task]
    assert team == ["Хава Гермиханова", "Владислав"]


def test_load_current_sprint_builds_default_jql_from_project_key(tmp_path, monkeypatch):
    creds = tmp_path / "jira_credentials.env"
    _write_credentials(
        creds, JIRA_BASE_URL="https://x.atlassian.net", JIRA_EMAIL="me@x.com",
        JIRA_API_TOKEN="tok", JIRA_PROJECT_KEY="SITE", JIRA_TEAM="Хава",
    )
    captured = {}

    def _fake_fetch(base_url, email, token, jql):
        captured["jql"] = jql
        return []

    monkeypatch.setattr(sprint_snapshot.jira_client, "fetch_sprint_tasks", _fake_fetch)

    load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(creds))

    assert "SITE" in captured["jql"]
    assert "openSprints" in captured["jql"]


def test_load_current_sprint_prefers_explicit_jql_over_project_key(tmp_path, monkeypatch):
    creds = tmp_path / "jira_credentials.env"
    _write_credentials(
        creds, JIRA_BASE_URL="https://x.atlassian.net", JIRA_EMAIL="me@x.com",
        JIRA_API_TOKEN="tok", JIRA_JQL="project = CUSTOM AND assignee = currentUser()",
        JIRA_TEAM="Хава",
    )
    captured = {}

    def _fake_fetch(base_url, email, token, jql):
        captured["jql"] = jql
        return []

    monkeypatch.setattr(sprint_snapshot.jira_client, "fetch_sprint_tasks", _fake_fetch)

    load_current_sprint("fixtures/sprint.json", FALLBACK_TEAM, credentials_path=str(creds))

    assert captured["jql"] == "project = CUSTOM AND assignee = currentUser()"
