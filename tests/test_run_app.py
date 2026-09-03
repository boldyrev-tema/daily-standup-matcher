from datetime import datetime, timezone

from meeting import Meeting
from run_app import LAYOUT_ORDER, LAYOUTS, _push_state
from run_polosa_replay import _state_json as _polosa_state_json
from run_second_screen import _state_json as _rich_state_json
from sprint_snapshot import Task

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _task(key, title):
    return Task(key=key, title=title, assignee="Дарья", status="В работе", updated_at=NOW)


class _FakeWindow:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)


def test_layout_registry_covers_all_three_html_files():
    assert set(LAYOUT_ORDER) == {"second_screen", "column", "polosa"}
    for key in LAYOUT_ORDER:
        spec = LAYOUTS[key]
        assert spec["html"].endswith(".html")
        assert spec["width"] > 0 and spec["height"] > 0


def test_push_state_uses_polosa_shape_for_polosa_layout():
    agenda = [_task("A-1", "Отчёты — убираем дубли платежей от партнёров")]
    meeting = Meeting(phase="live", remaining_count=1)
    window = _FakeWindow()

    _push_state("polosa", window, meeting, agenda, None)

    assert window.scripts == [f"renderMeeting({_polosa_state_json(meeting, agenda)})"]


def test_push_state_uses_rich_shape_for_column_and_second_screen():
    agenda = [_task("A-1", "Отчёты — убираем дубли платежей от партнёров")]
    meeting = Meeting(phase="live", remaining_count=1)

    for key in ("column", "second_screen"):
        window = _FakeWindow()
        _push_state(key, window, meeting, agenda, None)
        assert window.scripts == [f"renderMeeting({_rich_state_json(meeting, agenda, None)})"]
