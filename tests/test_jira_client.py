from unittest.mock import MagicMock, patch

from jira_client import fetch_sprint_tasks, search_issues

BASE_URL = "https://example.atlassian.net"
JQL = "project = X AND sprint in openSprints()"


def _issue(key, summary, assignee_name, status_name, status_category, updated, created=None,
           priority=None, labels=None):
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "assignee": {"displayName": assignee_name} if assignee_name else None,
            "status": {"name": status_name, "statusCategory": {"key": status_category}},
            "updated": updated,
            "created": created,
            "priority": {"name": priority} if priority else None,
            "labels": labels or [],
        },
    }


def _response(issues, is_last=True, next_page_token=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    body = {"issues": issues, "isLast": is_last}
    if next_page_token:
        body["nextPageToken"] = next_page_token
    resp.json.return_value = body
    return resp


def test_search_issues_calls_the_current_search_jql_endpoint_with_basic_auth():
    # The legacy GET /rest/api/3/search is fully removed (confirmed via
    # research, 3 сен) — this endpoint/verb/auth shape is what's actually
    # live now.
    with patch("jira_client.requests.post") as mock_post:
        mock_post.return_value = _response([_issue("A-1", "Заголовок", "Даша", "В работе", "indeterminate", "2026-09-01T10:00:00.000+0300")])

        search_issues(BASE_URL, "me@example.com", "tok", JQL)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == f"{BASE_URL}/rest/api/3/search/jql"
        assert kwargs["auth"] == ("me@example.com", "tok")
        assert kwargs["json"]["jql"] == JQL


def test_search_issues_is_read_only_never_calls_anything_but_post_search_jql():
    # Rinat's techspec rule 8: "в Jira ничего не изменено" — this client
    # must have no code path that can write. Only /rest/api/3/search/jql is
    # ever hit; asserted directly, not just "no put/delete used" by
    # inspection.
    with patch("jira_client.requests.post") as mock_post, patch("jira_client.requests.put") as mock_put, \
         patch("jira_client.requests.delete") as mock_delete:
        mock_post.return_value = _response([])

        search_issues(BASE_URL, "me@example.com", "tok", JQL)

        mock_put.assert_not_called()
        mock_delete.assert_not_called()
        for call in mock_post.call_args_list:
            assert call.args[0] == f"{BASE_URL}/rest/api/3/search/jql"


def test_search_issues_paginates_via_next_page_token_until_is_last():
    page1 = _response([_issue("A-1", "Первая", "Даша", "В работе", "indeterminate", "2026-09-01T10:00:00.000+0300")],
                       is_last=False, next_page_token="tok-2")
    page2 = _response([_issue("A-2", "Вторая", "Максим", "В работе", "indeterminate", "2026-09-01T11:00:00.000+0300")],
                       is_last=True)

    with patch("jira_client.requests.post", side_effect=[page1, page2]) as mock_post:
        issues = search_issues(BASE_URL, "me@example.com", "tok", JQL)

        assert [i["key"] for i in issues] == ["A-1", "A-2"]
        assert mock_post.call_count == 2
        second_call_body = mock_post.call_args_list[1].kwargs["json"]
        assert second_call_body["nextPageToken"] == "tok-2"


def test_fetch_sprint_tasks_maps_confirmed_real_field_shape_to_task():
    issue = _issue(
        "SITE-12160", "Разделение сделок и персон", "Хава Гермиханова", "В работе", "indeterminate",
        "2026-09-01T10:00:00.000+0300", created="2026-08-21T09:00:00.000+0300",
        priority="критический", labels=["релиз_текущий_спринт"],
    )
    with patch("jira_client.requests.post") as mock_post:
        mock_post.return_value = _response([issue])

        tasks = fetch_sprint_tasks(BASE_URL, "me@example.com", "tok", JQL)

        assert len(tasks) == 1
        t = tasks[0]
        assert t.key == "SITE-12160"
        assert t.title == "Разделение сделок и персон"
        assert t.assignee == "Хава Гермиханова"
        assert t.status == "В работе"
        assert t.status_category == "indeterminate"
        assert t.updated_at.year == 2026 and t.updated_at.month == 9 and t.updated_at.day == 1
        assert t.created.day == 21
        assert t.priority == "критический"
        assert t.labels == ["релиз_текущий_спринт"]
        assert t.url == f"{BASE_URL}/browse/SITE-12160"


def test_fetch_sprint_tasks_handles_unassigned_and_no_priority_without_crashing():
    # Jira allows both — a real sprint will have some of each.
    issue = _issue("SITE-1", "Без исполнителя", None, "К выполнению", "new", "2026-09-01T10:00:00.000+0300")
    with patch("jira_client.requests.post") as mock_post:
        mock_post.return_value = _response([issue])

        tasks = fetch_sprint_tasks(BASE_URL, "me@example.com", "tok", JQL)

        assert tasks[0].assignee == ""
        assert tasks[0].priority is None
        assert tasks[0].created is None
