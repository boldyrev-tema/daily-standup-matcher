import json
from datetime import datetime, timezone
from unittest.mock import patch, Mock

import requests

from meeting import Line
from sprint_snapshot import Task
from hints import get_hints

TASK = Task(
    key="NOVA-1", title="Отчёты — убираем дубли платежей от партнёров",
    assignee="Дарья Ковалёва", status="В работе",
    updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
)
LINES = [
    Line(t=10.0, who="Дарья", text="Убираем дубли платежей от партнёров, почти готово."),
    Line(t=15.0, who="Максим", text="Окей, хорошо."),
]


def _mock_response(payload: dict) -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    return resp


def test_get_hints_parses_valid_response():
    payload = {"said": ["Дарья почти закончила с дублями"], "ask": None}
    with patch("hints.requests.post", return_value=_mock_response(payload)):
        said, ask = get_hints(LINES, TASK, api_key="fake")
    assert said == ["Дарья почти закончила с дублями"]
    assert ask is None


def test_get_hints_returns_empty_on_timeout():
    with patch("hints.requests.post", side_effect=requests.exceptions.Timeout):
        said, ask = get_hints(LINES, TASK, api_key="fake")
    assert said == []
    assert ask is None


def test_get_hints_returns_empty_on_malformed_json():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
    with patch("hints.requests.post", return_value=resp):
        said, ask = get_hints(LINES, TASK, api_key="fake")
    assert said == []
    assert ask is None


def test_get_hints_returns_empty_when_json_is_not_an_object():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"choices": [{"message": {"content": "[]"}}]}
    with patch("hints.requests.post", return_value=resp):
        said, ask = get_hints(LINES, TASK, api_key="fake")
    assert said == []
    assert ask is None


def test_get_hints_only_uses_last_90_seconds():
    old_line = Line(t=1.0, who="Кто-то", text="Реплика минуту назад")
    recent_line = Line(t=95.0, who="Дарья", text="Свежая реплика")
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return _mock_response({"said": [], "ask": None})

    with patch("hints.requests.post", side_effect=fake_post):
        get_hints([old_line, recent_line], TASK, api_key="fake")
    user_content = captured["payload"]["messages"][1]["content"]
    assert "Свежая реплика" in user_content
    assert "Реплика минуту назад" not in user_content


def test_get_hints_lookback_none_includes_everything():
    old_line = Line(t=1.0, who="Кто-то", text="Реплика минуту назад")
    recent_line = Line(t=95.0, who="Дарья", text="Свежая реплика")
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return _mock_response({"said": [], "ask": None})

    with patch("hints.requests.post", side_effect=fake_post):
        get_hints([old_line, recent_line], TASK, api_key="fake", lookback_seconds=None)
    user_content = captured["payload"]["messages"][1]["content"]
    assert "Свежая реплика" in user_content
    assert "Реплика минуту назад" in user_content


def test_get_hints_includes_past_said_when_given():
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return _mock_response({"said": [], "ask": None})

    with patch("hints.requests.post", side_effect=fake_post):
        get_hints(LINES, TASK, api_key="fake", past_said=["Вчера обещали закончить сегодня"])
    user_content = captured["payload"]["messages"][1]["content"]
    assert "Что говорили по этой задаче в прошлый раз" in user_content
    assert "Вчера обещали закончить сегодня" in user_content


def test_get_hints_omits_past_context_when_not_given():
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return _mock_response({"said": [], "ask": None})

    with patch("hints.requests.post", side_effect=fake_post):
        get_hints(LINES, TASK, api_key="fake")
    user_content = captured["payload"]["messages"][1]["content"]
    assert "Что говорили по этой задаче в прошлый раз" not in user_content
