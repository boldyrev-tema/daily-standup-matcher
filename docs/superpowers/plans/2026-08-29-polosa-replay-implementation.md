# Полоса на реплее — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "Полоса" overlay end-to-end — Task model extension, deterministic facts, Meeting state, a real Groq LLM hints call, a transcript replay driver, and a pywebview window rendering the reduced Полоса view — validated by replaying real speech (matcher/LLM) without needing a live microphone or a real Jira token yet.

**Architecture:** Six new small modules on top of the already-implemented `sprint_snapshot.py`/`agenda.py`/`match_core.py`/`stopwords.py`/`lemmatize.py` (34 tests passing, commits `fdfab22`..`a9c8a3f`). `replay_driver.py` turns a list of utterances into `match()` calls and folds results into a `Meeting` (from `meeting.py`); `facts.py` derives the deterministic Jira-fact lines from a `Task`; `hints.py` makes the real Groq call for the LLM layer; `polosa.html` + `run_polosa_replay.py` render `Meeting` state in a pywebview window using the exact techspec style tokens and the apple-design motion rules already finalized in the spec.

**Tech Stack:** Python 3.14 (this project's `venv`), new deps `requests` (Groq REST call — matches the pattern already proven in `~/Desktop/Rinat Work/meeting_copilot`, not the `groq` SDK) and `pywebview` (overlay window), stdlib `dataclasses`/`re`/`json`/`time` for everything else, `pytest` for tests.

**Spec:** `docs/superpowers/specs/2026-08-29-polosa-replay-design.md` — read it alongside this plan.

## Global Constraints

- No code in this project touches `~/Desktop/Rinat Work/live_copilot_poc` or `~/Desktop/Rinat Work/meeting_copilot` — fully standalone (same constraint as the core plan).
- No test data or committed fixture may copy real Tranio task titles, sprint data, or coworker names verbatim — this includes the new integration test in Task 5. The real 44-line demo transcript used for this project's earlier manual validation stays in scratchpad only, never committed here.
- `git commit` after every task in this project's own repo (`~/Desktop/Bot TG/daily_standup_matcher`), never `--no-verify`. No push to any remote unless asked.
- `Task` stays a frozen dataclass — new fields get defaults so existing fixtures/tests keep working unmodified.
- `hit_words`/transcript word-underlining is explicitly out of scope for this plan (user's explicit choice during brainstorming) — no task implements it, no TODO left in code about it.
- `Meeting.current` persists across non-matching utterances — it only changes when `match()` returns a new result, confirmed against the real mockup's behavior (the recognized task stayed on screen through many unrelated follow-up utterances in the captured demo).
- LLM calls (`hints.py`) must degrade gracefully on timeout/error — never raise into the replay loop; the caller keeps showing facts-only.

---

## Task 1: `credentials.py` + extend `Task` with optional Jira-card fields

**Files:**
- Create: `credentials.py`
- Modify: `sprint_snapshot.py`
- Test: `tests/test_credentials.py`
- Test: `tests/test_sprint_snapshot.py` (extend)

**Interfaces:**
- Produces: `load_credential(path: str, key: str) -> str` (raises `ValueError` if key not found in file).
- Produces: `Task` gains `priority: str | None = None`, `labels: list[str] = field(default_factory=list)`, `created: datetime | None = None`, `url: str | None = None`. Existing fields (`key, title, assignee, status, updated_at`) unchanged, still positional-compatible.

- [ ] **Step 1: Write the failing test for `credentials.py`**

```python
# tests/test_credentials.py
import pytest
from credentials import load_credential


def test_load_credential_reads_value(tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("SOME_KEY=abc123\nOTHER_KEY=xyz\n")
    assert load_credential(str(env_file), "SOME_KEY") == "abc123"


def test_load_credential_raises_when_missing(tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("OTHER_KEY=xyz\n")
    with pytest.raises(ValueError):
        load_credential(str(env_file), "SOME_KEY")
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_credentials.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'credentials'`

- [ ] **Step 3: Implement `credentials.py`**

```python
import os


def load_credential(path: str, key: str) -> str:
    full_path = os.path.expanduser(path)
    with open(full_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.strip().split("=", 1)[1]
    raise ValueError(f"{key} not found in {full_path}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_credentials.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test for the extended `Task`**

Add to `tests/test_sprint_snapshot.py`:

```python
from datetime import datetime, timezone
from sprint_snapshot import Task


def test_task_optional_fields_default_empty():
    t = Task(
        key="NOVA-1", title="x", assignee="y", status="z",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert t.priority is None
    assert t.labels == []
    assert t.created is None
    assert t.url is None


def test_task_optional_fields_can_be_set():
    t = Task(
        key="NOVA-1", title="x", assignee="y", status="z",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        priority="критический",
        labels=["релиз_текущий_спринт"],
        created=datetime(2026, 7, 1, tzinfo=timezone.utc),
        url="https://example.invalid/NOVA-1",
    )
    assert t.priority == "критический"
    assert t.labels == ["релиз_текущий_спринт"]
    assert t.created == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert t.url == "https://example.invalid/NOVA-1"
```

- [ ] **Step 6: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_sprint_snapshot.py -v`
Expected: FAIL — `TypeError: Task.__init__() got an unexpected keyword argument 'priority'`

- [ ] **Step 7: Extend `Task` in `sprint_snapshot.py`**

```python
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    assignee: str
    status: str
    updated_at: datetime
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    created: datetime | None = None
    url: str | None = None


def load_sprint(path: str) -> list[Task]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [
        Task(
            key=item["key"],
            title=item["title"],
            assignee=item["assignee"],
            status=item["status"],
            updated_at=datetime.fromisoformat(item["updated_at"]),
            priority=item.get("priority"),
            labels=item.get("labels", []),
            created=datetime.fromisoformat(item["created"]) if item.get("created") else None,
            url=item.get("url"),
        )
        for item in raw
    ]
```

- [ ] **Step 8: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (38 tests: 34 previous + 4 new)

- [ ] **Step 9: Commit**

```bash
git add credentials.py sprint_snapshot.py tests/test_credentials.py tests/test_sprint_snapshot.py
git commit -m "Task 1: credentials.py + extend Task with priority/labels/created/url"
```

---

## Task 2: `facts.py`

**Files:**
- Create: `facts.py`
- Test: `tests/test_facts.py`

**Interfaces:**
- Consumes: `Task` (from Task 1, all optional fields).
- Produces: `build_facts(task: Task, now: datetime | None = None) -> list[str]` — 2 to 5 lines, exact order from the techspec.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_facts.py
from datetime import datetime, timezone
from sprint_snapshot import Task
from facts import build_facts

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)


def _task(**overrides):
    base = dict(
        key="NOVA-1", title="x", assignee="Дарья Ковалёва", status="В работе",
        updated_at=datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Task(**base)


def test_minimal_task_gives_two_lines():
    facts = build_facts(_task(), now=NOW)
    assert facts == ["В работе · Дарья Ковалёва", "Обновлено вчера"]


def test_critical_priority_adds_line():
    facts = build_facts(_task(priority="критический"), now=NOW)
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Приоритет: критический",
        "Обновлено вчера",
    ]


def test_non_critical_priority_adds_nothing():
    facts = build_facts(_task(priority="средний"), now=NOW)
    assert facts == ["В работе · Дарья Ковалёва", "Обновлено вчера"]


def test_release_label_adds_line():
    facts = build_facts(_task(labels=["релиз_текущий_спринт"]), now=NOW)
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Релиз в этом спринте",
        "Обновлено вчера",
    ]


def test_created_adds_line_at_the_end():
    facts = build_facts(
        _task(created=datetime(2026, 8, 1, tzinfo=timezone.utc)), now=NOW
    )
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Обновлено вчера",
        "Создана 01.08",
    ]


def test_all_five_lines_in_order():
    facts = build_facts(
        _task(
            priority="критический",
            labels=["релиз_текущий_спринт"],
            created=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        now=NOW,
    )
    assert facts == [
        "В работе · Дарья Ковалёва",
        "Приоритет: критический",
        "Релиз в этом спринте",
        "Обновлено вчера",
        "Создана 01.08",
    ]


def test_age_label_today_vs_days_ago():
    assert build_facts(_task(updated_at=NOW), now=NOW)[-1] == "Обновлено сегодня"
    two_days_ago = _task(updated_at=datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc))
    assert build_facts(two_days_ago, now=NOW)[-1] == "Обновлено 2 дня назад"
    five_days_ago = _task(updated_at=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc))
    assert build_facts(five_days_ago, now=NOW)[-1] == "Обновлено 5 дней назад"
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_facts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'facts'`

- [ ] **Step 3: Implement `facts.py`**

```python
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
```

Note: `_age_label`'s "N дня"/"N дней" split (2-4 vs 5+) follows standard Russian numeral grammar and isn't specified exactly in the techspec beyond the two examples ("вчера", "5 дней назад") — verified this matches natural Russian ("2 дня", "3 дня", "4 дня", "5 дней").

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (45 tests)

- [ ] **Step 5: Commit**

```bash
git add facts.py tests/test_facts.py
git commit -m "Task 2: facts.py — deterministic 2-5 line Jira-fact builder"
```

---

## Task 3: `meeting.py`

**Files:**
- Create: `meeting.py`
- Test: `tests/test_meeting.py`

**Interfaces:**
- Produces: `Line` dataclass (`t: float`, `who: str | None`, `text: str`, `task: str | None = None`).
- Produces: `Meeting` dataclass with `phase`, `lines`, `done`, `current`, `fresh`, `said`, `said_n`, `ask`, `elapsed_s`, `remaining_count`, and methods `add_line(line)`, `mark_recognized(key)`, `set_hints(said_lines, ask)`, `reveal_next_said() -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meeting.py
from meeting import Line, Meeting


def test_add_line_appends_and_advances_elapsed():
    m = Meeting(phase="live", remaining_count=3)
    m.add_line(Line(t=1.2, who="Дарья", text="привет"))
    m.add_line(Line(t=3.5, who="Дарья", text="ещё реплика"))
    assert [l.text for l in m.lines] == ["привет", "ещё реплика"]
    assert m.elapsed_s == 3.5


def test_mark_recognized_first_time_sets_everything():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    assert m.current == "NOVA-1"
    assert m.done == ["NOVA-1"]
    assert m.fresh == "NOVA-1"
    assert m.remaining_count == 1


def test_mark_recognized_again_updates_current_but_not_done_twice():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    m.set_hints(["строка"], "вопрос?")
    m.mark_recognized("NOVA-1")
    assert m.done == ["NOVA-1"]  # not duplicated
    assert m.remaining_count == 1  # not decremented twice
    # second mark of the same task does not wipe hints already shown
    assert m.said == []  # reveal_next_said not called yet, but _said_lines preserved
    assert m.reveal_next_said() is True
    assert m.said == ["строка"]


def test_mark_recognized_new_task_resets_hints():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    m.set_hints(["строка"], "вопрос?")
    m.reveal_next_said()
    m.mark_recognized("NOVA-2")
    assert m.current == "NOVA-2"
    assert m.said == []
    assert m.said_n == 0
    assert m.ask is None


def test_reveal_next_said_grows_one_at_a_time():
    m = Meeting(phase="live")
    m.set_hints(["a", "b", "c"], None)
    assert m.said == []
    assert m.reveal_next_said() is True
    assert m.said == ["a"]
    assert m.reveal_next_said() is True
    assert m.said == ["a", "b"]
    assert m.reveal_next_said() is True
    assert m.said == ["a", "b", "c"]
    assert m.reveal_next_said() is False
    assert m.said == ["a", "b", "c"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meeting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'meeting'`

- [ ] **Step 3: Implement `meeting.py`**

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Line:
    t: float
    who: str | None
    text: str
    task: str | None = None


@dataclass
class Meeting:
    phase: Literal["before", "live", "after"] = "before"
    lines: list[Line] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    current: str | None = None
    fresh: str | None = None
    said: list[str] = field(default_factory=list)
    said_n: int = 0
    ask: str | None = None
    elapsed_s: float = 0.0
    remaining_count: int = 0
    _said_lines: list[str] = field(default_factory=list)

    def add_line(self, line: Line) -> None:
        self.lines.append(line)
        self.elapsed_s = line.t

    def mark_recognized(self, key: str) -> None:
        self.current = key
        if key in self.done:
            return
        self.done.append(key)
        self.fresh = key
        self.said = []
        self._said_lines = []
        self.said_n = 0
        self.ask = None
        self.remaining_count = max(0, self.remaining_count - 1)

    def set_hints(self, said_lines: list[str], ask: str | None) -> None:
        self._said_lines = said_lines
        self.said = []
        self.said_n = 0
        self.ask = ask

    def reveal_next_said(self) -> bool:
        if self.said_n < len(self._said_lines):
            self.said.append(self._said_lines[self.said_n])
            self.said_n += 1
            return True
        return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (50 tests)

- [ ] **Step 5: Commit**

```bash
git add meeting.py tests/test_meeting.py
git commit -m "Task 3: meeting.py — Line/Meeting state, progressive said reveal"
```

---

## Task 4: `hints.py` — real Groq LLM call

**Files:**
- Create: `hints.py`
- Modify: `requirements.txt`
- Test: `tests/test_hints.py`

**Interfaces:**
- Consumes: `Line` (from Task 3), `Task` (from Task 1).
- Produces: `get_hints(lines: list[Line], task: Task, api_key: str, timeout: float = 3.0) -> tuple[list[str], str | None]` — never raises; returns `([], None)` on any failure (timeout, network error, malformed response).

- [ ] **Step 1: Add `requests` to `requirements.txt`**

```
pymorphy3
pymorphy3-dicts-ru
pytest
requests
```

- [ ] **Step 2: Install it**

Run: `venv/bin/pip install -r requirements.txt`
Expected: installs succeed (requests is likely already present transitively, this pins it explicitly).

- [ ] **Step 3: Write the failing tests (mocked Groq — no network)**

```python
# tests/test_hints.py
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
```

- [ ] **Step 4: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_hints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hints'`

- [ ] **Step 5: Implement `hints.py`**

```python
import json

import requests

from meeting import Line
from sprint_snapshot import Task

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
LOOKBACK_SECONDS = 90.0

SYSTEM_PROMPT = (
    "Ты помогаешь ведущему дейлика во время встречи. Тебе даны реплики за "
    "последние 90 секунд разговора и карточка задачи, которую сейчас "
    "обсуждают.\n\n"
    "Верни СТРОГО JSON-объект вида:\n"
    '{"said": ["строка 1", "строка 2"], "ask": "вопрос" или null}\n\n'
    "Правила:\n"
    "- said — не более 3 строк по 60-90 знаков, каждая ОБЯЗАНА опираться на "
    "конкретную произнесённую реплику. Не пересказывай реплики целиком — "
    "выжимай только суть.\n"
    "- Ничего не выдумывай: если в репликах нет содержательной информации "
    "по задаче — верни пустой список said.\n"
    "- ask — один вопрос ведущему, только если есть явное расхождение между "
    "сказанным и карточкой задачи, или незакрытая договорённость. Если "
    "повода нет — null.\n"
    "- Никогда не предлагай действий в Jira — это вне твоей роли."
)


def _task_card(task: Task) -> str:
    parts = [f"Ключ: {task.key}", f"Заголовок: {task.title}", f"Статус: {task.status}"]
    parts.append(f"Исполнитель: {task.assignee}")
    if task.priority:
        parts.append(f"Приоритет: {task.priority}")
    return "\n".join(parts)


def _recent_lines_text(lines: list[Line], now_t: float) -> str:
    recent = [l for l in lines if now_t - l.t <= LOOKBACK_SECONDS]
    return "\n".join(f"{l.who or '?'}: {l.text}" for l in recent)


def get_hints(
    lines: list[Line], task: Task, api_key: str, timeout: float = 3.0
) -> tuple[list[str], str | None]:
    if not lines:
        return [], None
    now_t = lines[-1].t
    user_content = (
        f"Карточка задачи:\n{_task_card(task)}\n\n"
        f"Реплики за последние 90с:\n{_recent_lines_text(lines, now_t)}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        said = parsed.get("said", [])
        ask = parsed.get("ask")
        if not isinstance(said, list):
            return [], None
        return said[:3], ask
    except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return [], None
```

- [ ] **Step 6: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (54 tests)

- [ ] **Step 7: MANUAL — live Groq verification (required before this task counts as done)**

This project's own history (and `meeting_copilot`'s before it) shows mocked tests don't catch real prompt bugs. Run once against the real API:

```bash
source ~/.credentials/groq_api_key.env
venv/bin/python3 -c "
from datetime import datetime, timezone
from credentials import load_credential
from meeting import Line
from sprint_snapshot import Task
from hints import get_hints

api_key = load_credential('~/.credentials/groq_api_key.env', 'GROQ_API_KEY')
task = Task(key='NOVA-1', title='Отчёты — убираем дубли платежей от партнёров',
            assignee='Дарья Ковалёва', status='В работе',
            updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc))
lines = [
    Line(t=10.0, who='Дарья', text='Убираем дубли платежей от партнёров, почти готово, завтра отдам на ревью Максиму.'),
    Line(t=15.0, who='Максим', text='Окей, хорошо, жду.'),
]
said, ask = get_hints(lines, task, api_key)
print('said:', said)
print('ask:', ask)
"
```

Expected: `said` contains a grounded 1-line summary referencing the actual review handoff to Maxim; `ask` is likely `null` (no real discrepancy in this sample). If `said` looks fabricated or unrelated to the input lines, fix the prompt in `hints.py` and re-run — do not consider Task 4 done until this manual check looks right.

- [ ] **Step 8: Commit**

```bash
git add hints.py requirements.txt tests/test_hints.py
git commit -m "Task 4: hints.py — real Groq call for said/ask per techspec contract"
```

---

## Task 5: `replay_driver.py` + invented sample transcript + integration test

**Files:**
- Create: `replay_driver.py`
- Create: `fixtures/sample_daily_transcript.json`
- Test: `tests/test_replay_driver.py`

**Interfaces:**
- Consumes: `match()` (from `match_core.py`), `Task`/`load_sprint` (from `sprint_snapshot.py`), `build_agenda` (from `agenda.py`), `Line`/`Meeting` (from Task 3).
- Produces: `replay(transcript: list[dict], agenda: list[Task]) -> Meeting` — `transcript` items are `{"speaker": str, "text": str}`.

**Note on test data:** this integration test needs a multi-turn dialogue longer than the existing `fixtures/sprint.json` test cases exercise together. It's invented (NOVA scenario, same as the rest of the project), NOT the real 28.08 demo transcript used for this project's manual validation — that real transcript stays in scratchpad per the project's own rule against committing real Tranio data.

- [ ] **Step 1: Write the invented sample transcript fixture**

```json
[
  {"speaker": "Дарья", "text": "Отчёты почти готовы, убираем последние дубли платежей от партнёров."},
  {"speaker": "Дарья", "text": "И ещё была задача 10201, но там всё по плану."},
  {"speaker": "Максим", "text": "Ну, короче, всё окей, погнали дальше."},
  {"speaker": "Полина", "text": "Мы выгружаем контакты в систему, но пока не уверены в какую именно."},
  {"speaker": "Игорь", "text": "Со складом беда, синхронизация остатков с кассой опять поехала."},
  {"speaker": "Максим", "text": "Ладно, по заявкам поставщиков функционал я почти закончил."}
]
```

Save as `fixtures/sample_daily_transcript.json`.

- [ ] **Step 2: Write the failing integration test**

```python
# tests/test_replay_driver.py
from agenda import build_agenda
from sprint_snapshot import load_sprint
from replay_driver import replay
import json

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]


def _load_transcript():
    with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
        return json.load(f)


def test_replay_recognizes_expected_tasks_and_stays_silent_on_the_rest():
    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)
    transcript = _load_transcript()

    meeting = replay(transcript, agenda)

    # NOVA-10214 (word overlap), NOVA-10201 (number channel), NOVA-10299
    # (word overlap, also the alarm/reopened task), NOVA-10230 (word overlap)
    # recognized, in that order. NOVA-10267/NOVA-10288 stay silent — the
    # transcript line about them is deliberately ambiguous between the two
    # (omits "старую"/"новую"), same margin-gate mechanism validated on the
    # real transcript earlier in this project's history. The filler line
    # ("Ну, короче, всё окей, погнали дальше.") matches nothing.
    assert meeting.done == ["NOVA-10214", "NOVA-10201", "NOVA-10299", "NOVA-10230"]
    assert meeting.remaining_count == 2
    assert meeting.phase == "after"
    assert len(meeting.lines) == 6
```

- [ ] **Step 3: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_replay_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'replay_driver'`

- [ ] **Step 4: Implement `replay_driver.py`**

```python
import re

from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import Task

_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")
SECONDS_PER_WORD = 0.4


def _utterance_duration(text: str) -> float:
    word_count = len(_WORD_RE.findall(text))
    return max(word_count, 1) * SECONDS_PER_WORD


def replay(transcript: list[dict], agenda: list[Task]) -> Meeting:
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    t = 0.0
    for turn in transcript:
        t += _utterance_duration(turn["text"])
        results = match(turn["text"], agenda)
        task_key = results[0].task_key if results else None
        meeting.add_line(Line(t=t, who=turn.get("speaker"), text=turn["text"], task=task_key))
        if results:
            meeting.mark_recognized(results[0].task_key)
    meeting.phase = "after"
    return meeting
```

- [ ] **Step 5: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (55 tests). If `meeting.done` doesn't match the expected list, print `meeting.done` and check which line scored differently than predicted — adjust the test's expected list to match actual (correct) matcher behavior, don't force the matcher to fit a wrong prediction.

- [ ] **Step 6: Commit**

```bash
git add replay_driver.py fixtures/sample_daily_transcript.json tests/test_replay_driver.py
git commit -m "Task 5: replay_driver.py + invented sample transcript + integration test"
```

---

## Task 6: `polosa.html` — the overlay page

**Files:**
- Create: `polosa.html`

**Interfaces:**
- Consumes: a `renderMeeting(stateJson)` global JS function, called externally (by Task 7's pywebview wiring) with a JSON-serialized subset of `Meeting`: `{elapsed_s, remaining_count, phase, last_line: {who, text}, current_task: {title, first_fact} | null, ask: string | null}`.
- Produces: nothing consumed by later tasks — this is a leaf.

- [ ] **Step 1: Write `polosa.html`**

```html
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Полоса</title>
<style>
  :root {
    --page-bg: rgba(19,18,23,.86);
    --line: rgba(255,255,255,.09);
    --ink: #F2F0EE;
    --dim: #9C97A3;
    --mute: #6b6672;
    --live: #54C77A;
    --alarm: #E36B6B;
    --accent-text: #D6C8FF;
    --accent-bg: rgba(139,92,246,.16);
    --accent-border: rgba(139,92,246,.5);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; height: 100%; background: transparent;
    font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
  }
  body { display: flex; align-items: center; justify-content: center; }
  .polosa {
    width: 1200px; height: 200px;
    background: var(--page-bg);
    backdrop-filter: blur(18px);
    border-radius: 14px;
    display: flex;
    color: var(--ink);
    overflow: hidden;
  }
  .zone { padding: 16px 20px; display: flex; flex-direction: column; justify-content: center; }
  .zone + .zone { border-left: 1px solid var(--line); }

  .zone-control { width: 180px; flex-shrink: 0; }
  .zone-hear { flex: 1.4; min-width: 0; }
  .zone-hint { flex: 1.6; min-width: 0; }
  .zone-ask { width: 260px; flex-shrink: 0; }

  .title { font-size: 18px; font-weight: 600; letter-spacing: -0.015em; line-height: 1.15; margin: 0 0 6px; }
  .section-label { font-size: 13px; font-weight: 600; letter-spacing: 0; color: var(--dim); margin: 0 0 8px; }
  .body-text { font-size: 15px; font-weight: 400; line-height: 1.45; margin: 0; }
  .mute { font-size: 12px; font-weight: 500; letter-spacing: 0.01em; color: var(--mute); }

  .live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--live);
    display: inline-block; margin-right: 6px;
    animation: breathe 1.8s ease-in-out infinite;
  }
  @keyframes breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) {
    .live-dot { animation: none; opacity: 0.85; }
  }

  .zone-label {
    font-size: 13px; font-weight: 600; color: var(--dim);
    transition: opacity 140ms ease;
  }

  .ask-pill {
    background: var(--accent-bg); border: 1px solid var(--accent-border);
    border-radius: 10px; padding: 10px 12px; color: var(--accent-text);
    font-size: 14px; line-height: 1.4;
  }

  .btn {
    background: var(--ink); color: #111; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer;
  }
  .btn:active { transform: scale(0.97); }

  @media (prefers-reduced-transparency: reduce) {
    .polosa { background: #131217; backdrop-filter: none; }
  }
</style>
</head>
<body>
  <div class="polosa">
    <div class="zone zone-control">
      <div class="mute" id="elapsed">Сегодня, 12:00</div>
      <div class="mute" id="remaining">осталось —</div>
      <button class="btn" id="control-btn" style="margin-top:8px;">Начать</button>
    </div>
    <div class="zone zone-hear">
      <div class="zone-label" id="hear-label">Слышу</div>
      <p class="body-text" id="hear-text">Транскрипт появится, когда начнётся запись</p>
    </div>
    <div class="zone zone-hint">
      <div class="zone-label" id="hint-label">Подсказываю</div>
      <p class="title" id="hint-title" style="font-size:15px;"></p>
      <p class="body-text mute" id="hint-fact"></p>
    </div>
    <div class="zone zone-ask">
      <div class="section-label">Спроси</div>
      <div id="ask-content"><span class="mute">—</span></div>
    </div>
  </div>

<script>
function renderMeeting(state) {
  document.getElementById("elapsed").textContent = state.phase === "before"
    ? "Сегодня, 12:00" : formatElapsed(state.elapsed_s);
  document.getElementById("remaining").textContent = state.phase === "after"
    ? `не обсудили ${state.remaining_count}` : `осталось ${state.remaining_count}`;
  document.getElementById("control-btn").textContent = state.phase === "after" ? "Сначала" : "Начать";

  const hearLabel = document.getElementById("hear-label");
  hearLabel.textContent = (state.last_line && state.last_line.who) || "Слышу";
  document.getElementById("hear-text").textContent =
    (state.last_line && state.last_line.text) || "Транскрипт появится, когда начнётся запись";

  const hintLabel = document.getElementById("hint-label");
  const hintTitle = document.getElementById("hint-title");
  const hintFact = document.getElementById("hint-fact");
  if (state.current_task) {
    hintLabel.textContent = "Говорят о задаче";
    hintTitle.textContent = state.current_task.title;
    hintFact.textContent = state.current_task.first_fact;
  } else {
    hintLabel.textContent = "Подсказываю";
    hintTitle.textContent = "";
    hintFact.textContent = "Подсказка появится, когда узнаю задачу";
  }

  const askContent = document.getElementById("ask-content");
  if (state.ask) {
    askContent.innerHTML = "";
    const pill = document.createElement("div");
    pill.className = "ask-pill";
    pill.textContent = state.ask;
    askContent.appendChild(pill);
  } else {
    askContent.innerHTML = '<span class="mute">—</span>';
  }
}

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m} мин`;
}

window.renderMeeting = renderMeeting;
</script>
</body>
</html>
```

- [ ] **Step 2: Manual visual check**

Open the file directly in a browser (`open polosa.html`), then in the browser devtools console run:

```js
renderMeeting({
  phase: "live", elapsed_s: 65, remaining_count: 2,
  last_line: {who: "Дарья", text: "Убираем дубли платежей от партнёров, почти готово."},
  current_task: {title: "Отчёты — убираем дубли платежей от партнёров", first_fact: "В работе · Дарья Ковалёва"},
  ask: "Максим уже проверил MR по дублям?"
});
```

Expected: control zone shows "1 мин" / "осталось 2"; hear zone label switches to "Дарья"; hint zone shows the task title + fact line; ask zone shows the accent pill. Check against the 8 techspec behavior rules by eye (color only on the accent pill and the live dot, no entrance animation on text changes, live dot breathing softly).

- [ ] **Step 3: Commit**

```bash
git add polosa.html
git commit -m "Task 6: polosa.html — reduced-view overlay page, techspec tokens + apple-design motion"
```

---

## Task 7: `run_polosa_replay.py` — pywebview wiring + README update

**Files:**
- Create: `run_polosa_replay.py`
- Modify: `requirements.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: `replay_driver.replay` is NOT reused directly here (that function runs to completion instantly, no pacing) — this script re-implements the same loop but with real-time pauses and live `polosa.html` pushes between each utterance, calling `match()`, `facts.build_facts()`, and `hints.get_hints()` (Groq — real key loaded via `credentials.load_credential`) as it goes.

**Design note (deviation, disclosed):** the mockup's "Начать" button is not wired to a click handler in this build. pywebview's JS→Python callback bridge has a documented timing bug in this author's related `live_copilot_poc` project (callback fires before `window.pywebview` is injected). Since this build only needs one-directional Python→JS pushes (`evaluate_js`), the replay instead auto-starts a few seconds after the window opens, sidestepping that entire bug class. The button still repaints correctly via `renderMeeting` (label flips to "Сначала" at the end) — it's just not clickable yet. This is scoped out of this plan, not silently dropped.

- [ ] **Step 1: Add `pywebview` to `requirements.txt`**

```
pymorphy3
pymorphy3-dicts-ru
pytest
requests
pywebview
```

Run: `venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: Implement `run_polosa_replay.py`**

```python
import json
import re
import time

import webview

from agenda import build_agenda
from credentials import load_credential
from facts import build_facts
from hints import get_hints
from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import load_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
GROQ_KEY_PATH = "~/.credentials/groq_api_key.env"
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


def _state_json(meeting: Meeting, agenda) -> str:
    current_task = None
    if meeting.current:
        task = next((t for t in agenda if t.key == meeting.current), None)
        if task:
            first_fact = build_facts(task)[0]
            current_task = {"title": task.title, "first_fact": first_fact}
    last_line = None
    if meeting.lines:
        l = meeting.lines[-1]
        last_line = {"who": l.who, "text": l.text}
    return json.dumps({
        "phase": meeting.phase,
        "elapsed_s": meeting.elapsed_s,
        "remaining_count": meeting.remaining_count,
        "last_line": last_line,
        "current_task": current_task,
        "ask": meeting.ask,
    })


def _run_replay(window):
    time.sleep(3)  # let the window/page finish loading before the first push

    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)
    with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
        transcript = json.load(f)
    api_key = load_credential(GROQ_KEY_PATH, "GROQ_API_KEY")

    meeting = Meeting(phase="live", remaining_count=len(agenda))
    t = 0.0
    for turn in transcript:
        word_count = len(_WORD_RE.findall(turn["text"]))
        pause = max(word_count, 1) * 0.4
        time.sleep(pause)
        t += pause

        results = match(turn["text"], agenda)
        task_key = results[0].task_key if results else None
        meeting.add_line(Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key))

        if results:
            meeting.mark_recognized(results[0].task_key)
            task = next(x for x in agenda if x.key == results[0].task_key)
            said, ask = get_hints(meeting.lines, task, api_key)
            meeting.set_hints(said, ask)

        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")

        while meeting.reveal_next_said():
            time.sleep(1.5)
            window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")

    meeting.phase = "after"
    window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")


if __name__ == "__main__":
    window = webview.create_window(
        "Полоса", "polosa.html", width=1200, height=200, frameless=True, on_top=True
    )
    webview.start(_run_replay, window)
```

- [ ] **Step 3: Manual end-to-end check**

Run: `venv/bin/python3 run_polosa_replay.py`
Expected: a small frameless window opens, auto-starts after ~3s, plays through the 6 invented utterances with realistic pauses, the hint zone updates on recognition (NOVA-10214, NOVA-10201, NOVA-10299, NOVA-10230 in order), "Сказали" lines from the real Groq call appear one at a time where applicable, control zone counts down, ends on "не обсудили 2" with the button reading "Сначала". Check by eye against the techspec's 8 behavior rules (nothing disappears, no entrance animation on text swaps, color only on alarm/accent/live).

- [ ] **Step 4: Update `README.md`**

Add after the existing "What's here" list:

```markdown
- `facts.py` — deterministic 2-5 line Jira-fact builder from a `Task`.
- `meeting.py` — `Line`/`Meeting` state: recognized-task tracking, progressive
  one-at-a-time reveal of LLM "said" lines.
- `hints.py` — real Groq call for the "Сказали"/"Спроси" LLM layer, strict
  JSON contract, degrades to empty on timeout/error (never crashes the replay).
- `credentials.py` — reads `KEY=value` lines from a `~/.credentials/*.env`
  file (same tiny pattern as this author's `meeting_copilot` project).
- `replay_driver.py` — turns an invented sample transcript into a finished
  `Meeting` (used by the integration test; no pacing, no LLM calls).
- `run_polosa_replay.py` — the real thing: opens a pywebview "Полоса" window
  and plays `fixtures/sample_daily_transcript.json` with realistic pauses and
  real Groq calls. Needs `~/.credentials/groq_api_key.env` (`GROQ_API_KEY=...`).
- `polosa.html` — the overlay page itself, techspec style tokens + apple-design
  restrained motion.

## Known gaps in this iteration

Not implemented: live microphone / Speechmatics STT (still reads an invented
transcript file), real Jira snapshot (still `fixtures/sprint.json`), speaker
diarization, `hit_words` transcript underlining, the Начать/Сначала button's
click handler (the replay auto-starts instead — see
`docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why).
```

- [ ] **Step 5: Commit**

```bash
git add run_polosa_replay.py requirements.txt README.md
git commit -m "Task 7: run_polosa_replay.py — pywebview wiring, real Groq, README update"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Task model extension (Task 1), `facts.py` (Task 2), `meeting.py` incl. `said_n` progressive reveal (Task 3), `hints.py` real Groq contract (Task 4), `replay_driver.py` (Task 5, using invented data per the project's own real-data rule — a deliberate, disclosed correction from the spec's original wording), `polosa.html` reduced view + apple-design motion (Task 6), pywebview wiring (Task 7). `hit_words` and live-mic/real-Jira explicitly out of scope, matching the spec's own "Не входит" section.
- **No placeholders:** every step has runnable code.
- **Type/name consistency checked:** `Task.priority/labels/created/url`, `Line(t, who, text, task)`, `Meeting(phase, lines, done, current, fresh, said, said_n, ask, elapsed_s, remaining_count)`, `build_facts(task, now)`, `get_hints(lines, task, api_key, timeout)`, `replay(transcript, agenda)` — spelled identically everywhere used across tasks.
- **Real-data check:** confirmed no task commits real Tranio titles/names/keys — Task 5's fixture and Task 4/7's example data are all NOVA-scenario inventions.
