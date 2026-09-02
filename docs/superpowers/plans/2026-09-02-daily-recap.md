# Сноска о прошлом дейлике — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On closing a live daily (`run_second_screen.py --live`), collect a per-task recap ("said" lines from `hints.get_hints`, sourced from the full session transcript) and save it; on the next `--live` launch, show the most recent saved recap in its own small closable window next to the main one.

**Architecture:** A new `recap.py` module groups `Meeting.lines` by task and reuses the already-live-tested `hints.get_hints()` per task (extended with an optional `lookback_seconds=None` to see the whole task's discussion, not just the live 90s window). Generation runs in a non-daemon background thread on `window.events.closing` so it never blocks the window from closing. A new `recap.html` window (same dark tokens as the other three placements) is conditionally created at `--live` startup when a saved recap exists, with its own close button reusing the just-fixed non-daemon-thread `window.destroy()` pattern.

**Tech Stack:** Python 3.14, pywebview, existing `requests`-based OpenRouter calls (via `hints.get_hints`), no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-daily-recap-design.md`

## Global Constraints

- Recap generation and the recap window apply ONLY to `run_second_screen.py --live` — never to replay mode or to `run_column.py`/`run_polosa_replay.py`.
- Source of truth for "what was discussed" is `Meeting.lines` (append-only), never the live `Meeting.said`/`Meeting.ask` fields (those get overwritten by `mark_recognized()`).
- Recap generation must never block window close — always a non-daemon background thread from `window.events.closing`.
- `recaps/` holds real transcript content from a public repo's users — must be gitignored, never committed.
- No new UI color/token values — reuse the existing dark palette (`--page-bg`, `--ink`, `--dim`, `--control-bg`, `--control-hover`, `--edge-highlight`) already defined in `second_screen.html`.
- Tasks with an empty `said` list (from `get_hints`) are excluded from the saved recap entirely.

---

## Task 1: `hints.get_hints` — optional full-history mode

**Files:**
- Modify: `hints.py:64-98` (`_recent_lines_text`, `get_hints`)
- Test: `tests/test_hints.py`

**Interfaces:**
- Produces: `get_hints(lines, task, api_key, timeout=6.0, lookback_seconds=90.0)` — new optional 5th param; `lookback_seconds=None` disables the 90-second window filter entirely (all passed-in lines are used). Existing 4-arg call sites are unaffected (default preserves current behavior).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_hints.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_hints.py::test_get_hints_lookback_none_includes_everything -v`
Expected: FAIL — `TypeError: get_hints() got an unexpected keyword argument 'lookback_seconds'`

- [ ] **Step 3: Implement**

In `hints.py`, replace `_recent_lines_text` and `get_hints`:

```python
def _recent_lines_text(lines: list[Line], now_t: float, lookback_seconds: float | None) -> str:
    if lookback_seconds is None:
        recent = lines
    else:
        recent = [l for l in lines if now_t - l.t <= lookback_seconds]
    return "\n".join(f"{l.who or '?'}: {l.text}" for l in recent)


def get_hints(
    lines: list[Line],
    task: Task,
    api_key: str,
    timeout: float = 6.0,
    lookback_seconds: float | None = LOOKBACK_SECONDS,
) -> tuple[list[str], str | None]:
    if not lines:
        return [], None
    now_t = lines[-1].t
    window_label = "за последние 90с" if lookback_seconds is not None else "за всё обсуждение"
    user_content = (
        f"Карточка задачи:\n{_task_card(task)}\n\n"
        f"Реплики {window_label}:\n{_recent_lines_text(lines, now_t, lookback_seconds)}"
    )
    for model, extra in MODEL_CHAIN:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            **extra,
        }
        try:
            return _request_hints(payload, api_key, timeout)
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError):
            continue
    return [], None
```

- [ ] **Step 4: Run all hints tests to verify nothing broke**

Run: `venv/bin/python -m pytest tests/test_hints.py -v`
Expected: PASS — all tests including the existing `test_get_hints_only_uses_last_90_seconds` (default `lookback_seconds` unchanged) and the new one.

- [ ] **Step 5: Commit**

```bash
git add hints.py tests/test_hints.py
git commit -m "$(cat <<'EOF'
Add lookback_seconds=None mode to get_hints for full-task-history summaries

The live 90s window is right for a live hint, but a post-daily recap needs
everything said about a task across the whole meeting, not just its last
90 seconds.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XqfxwnWQmrMQmeCunmZiTU
EOF
)"
```

---

## Task 2: `recap.py` — build, save, and load recaps

**Files:**
- Create: `recap.py`
- Modify: `.gitignore`
- Test: `tests/test_recap.py`

**Interfaces:**
- Consumes: `hints.get_hints(lines, task, api_key, lookback_seconds=None)` from Task 1; `meeting.Meeting` (`.lines: list[Line]`, `.done: list[str]`); `sprint_snapshot.Task` (`.key`, `.title`).
- Produces:
  - `build_recap(meeting: Meeting, agenda: list[Task], api_key: str) -> list[dict]` — each dict is `{"key": str, "title": str, "said": list[str]}`.
  - `save_recap(records: list[dict], dir: str = "recaps") -> str` — writes `{"generated_at": <ISO string>, "tasks": records}`, returns the file path written.
  - `latest_recap(dir: str = "recaps") -> dict | None` — returns the parsed contents of the newest file in `dir`, or `None` if the directory doesn't exist or is empty.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recap.py`:

```python
import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

from meeting import Line, Meeting
from sprint_snapshot import Task
from recap import build_recap, save_recap, latest_recap

TASK_A = Task(
    key="NOVA-1", title="Дубли платежей", assignee="Дарья",
    status="В работе", updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
)
TASK_B = Task(
    key="NOVA-2", title="Экспорт в CSV", assignee="Максим",
    status="В работе", updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
)


def _meeting_with(lines: list[Line], done: list[str]) -> Meeting:
    meeting = Meeting()
    for line in lines:
        meeting.add_line(line)
    meeting.done = done
    return meeting


def test_build_recap_groups_lines_by_task_and_calls_get_hints_per_task():
    lines = [
        Line(t=1.0, who="Дарья", text="Дубли почти убраны", task="NOVA-1"),
        Line(t=5.0, who="Максим", text="Экспорт готов", task="NOVA-2"),
    ]
    meeting = _meeting_with(lines, done=["NOVA-1", "NOVA-2"])
    calls = []

    def fake_get_hints(task_lines, task, api_key, lookback_seconds=None):
        calls.append((task.key, [l.text for l in task_lines], lookback_seconds))
        return ([f"said about {task.key}"], None)

    with patch("recap.get_hints", side_effect=fake_get_hints):
        records = build_recap(meeting, [TASK_A, TASK_B], api_key="fake")

    assert records == [
        {"key": "NOVA-1", "title": "Дубли платежей", "said": ["said about NOVA-1"]},
        {"key": "NOVA-2", "title": "Экспорт в CSV", "said": ["said about NOVA-2"]},
    ]
    assert calls[0] == ("NOVA-1", ["Дубли почти убраны"], None)
    assert calls[1] == ("NOVA-2", ["Экспорт готов"], None)


def test_build_recap_skips_tasks_with_empty_said():
    lines = [Line(t=1.0, who="Дарья", text="...", task="NOVA-1")]
    meeting = _meeting_with(lines, done=["NOVA-1"])
    with patch("recap.get_hints", return_value=([], None)):
        records = build_recap(meeting, [TASK_A], api_key="fake")
    assert records == []


def test_build_recap_skips_a_done_key_not_present_in_agenda():
    lines = [Line(t=1.0, who="Дарья", text="...", task="GONE-1")]
    meeting = _meeting_with(lines, done=["GONE-1"])
    with patch("recap.get_hints", return_value=(["x"], None)) as mock_get_hints:
        records = build_recap(meeting, [TASK_A], api_key="fake")
    assert records == []
    mock_get_hints.assert_not_called()


def test_save_recap_writes_json_with_generated_at_and_tasks(tmp_path):
    records = [{"key": "NOVA-1", "title": "Дубли платежей", "said": ["..."]}]
    path = save_recap(records, dir=str(tmp_path))
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["tasks"] == records
    assert "generated_at" in data


def test_latest_recap_returns_none_when_dir_missing(tmp_path):
    assert latest_recap(dir=str(tmp_path / "nope")) is None


def test_latest_recap_returns_none_when_dir_empty(tmp_path):
    assert latest_recap(dir=str(tmp_path)) is None


def test_latest_recap_returns_most_recent_file(tmp_path):
    with open(tmp_path / "2026-09-01_10-00-00.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": "2026-09-01T10:00:00+00:00",
                    "tasks": [{"key": "OLD", "title": "Old", "said": ["x"]}]}, f)
    with open(tmp_path / "2026-09-02_10-00-00.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": "2026-09-02T10:00:00+00:00",
                    "tasks": [{"key": "NEW", "title": "New", "said": ["y"]}]}, f)
    result = latest_recap(dir=str(tmp_path))
    assert result["tasks"][0]["key"] == "NEW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_recap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recap'`

- [ ] **Step 3: Implement `recap.py`**

```python
import json
import os
from datetime import datetime, timezone

from hints import get_hints
from meeting import Meeting
from sprint_snapshot import Task

RECAPS_DIR = "recaps"


def build_recap(meeting: Meeting, agenda: list[Task], api_key: str) -> list[dict]:
    """One record per task in meeting.done that has something to say.
    Sourced from meeting.lines (append-only, never overwritten) rather than
    the live meeting.said/meeting.ask fields, which get reset every time
    mark_recognized() moves to a new task — see
    docs/superpowers/specs/2026-09-02-daily-recap-design.md.
    """
    tasks_by_key = {task.key: task for task in agenda}
    records = []
    for key in meeting.done:
        task = tasks_by_key.get(key)
        if task is None:
            continue
        task_lines = [line for line in meeting.lines if line.task == key]
        said, _ask = get_hints(task_lines, task, api_key, lookback_seconds=None)
        if not said:
            continue
        records.append({"key": task.key, "title": task.title, "said": said})
    return records


def save_recap(records: list[dict], dir: str = RECAPS_DIR) -> str:
    os.makedirs(dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = os.path.join(dir, now.strftime("%Y-%m-%d_%H-%M-%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(), "tasks": records}, f, ensure_ascii=False, indent=2)
    return path


def latest_recap(dir: str = RECAPS_DIR) -> dict | None:
    if not os.path.isdir(dir):
        return None
    files = sorted(f for f in os.listdir(dir) if f.endswith(".json"))
    if not files:
        return None
    with open(os.path.join(dir, files[-1]), encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 4: Add `recaps/` to `.gitignore`**

`.gitignore` becomes:

```
venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
recaps/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_recap.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `venv/bin/python -m pytest -q`
Expected: PASS — all tests (previous 122 + 1 from Task 1 + 6 from this task).

- [ ] **Step 7: Commit**

```bash
git add recap.py tests/test_recap.py .gitignore
git commit -m "$(cat <<'EOF'
Add recap.py: build/save/load a post-daily recap per discussed task

Groups meeting.lines by task (not the live, overwritten meeting.said) and
reuses hints.get_hints() per task instead of a second LLM pass over the
full transcript. recaps/ is gitignored — real transcript content in a
public repo.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XqfxwnWQmrMQmeCunmZiTU
EOF
)"
```

---

## Task 3: `recap.html` — the small recap window

**Files:**
- Create: `recap.html`

**Interfaces:**
- Consumes: a `renderRecap(data)` JS call from Python, where `data` is the exact dict shape `latest_recap()` returns: `{"generated_at": <ISO string>, "tasks": [{"key", "title", "said": [...]}]}`.
- Produces: exposes a `pywebview.api.close_recap_window()` call from its close button (name deliberately distinct from the main window's `close_window`, which lives in a different window/JS-API namespace — kept distinct to avoid any confusion when reading `run_second_screen.py`'s `__main__` block later).

No automated test for this file — matches this project's existing convention (`second_screen.html`/`polosa.html`/`column.html` have none either). Verified manually in Task 4.

- [ ] **Step 1: Write `recap.html`**

```html
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Прошлый дейлик</title>
<style>
  :root {
    --page-bg: rgba(19,18,23,.86);
    --solid-bg: #131217;
    --ink: #F2F0EE;
    --dim: #9C97A3;
    --control-bg: rgba(255,255,255,.08);
    --control-hover: rgba(255,255,255,.16);
    --edge-highlight: rgba(255,255,255,.12);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; height: 100%; background: transparent;
    font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
  }
  body {
    background: var(--page-bg);
    border-top: 1px solid var(--edge-highlight);
    backdrop-filter: blur(18px) saturate(180%);
    color: var(--ink);
    overflow-y: auto;
    padding: 16px;
  }
  @media (prefers-reduced-transparency: reduce) {
    body { background: var(--solid-bg); backdrop-filter: none; }
  }
  .window-controls { position: fixed; top: 10px; right: 12px; z-index: 10; }
  .window-controls button {
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--control-bg); border: none; color: var(--dim);
    font-size: 15px; line-height: 1; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background 140ms ease, color 140ms ease;
  }
  .window-controls button:hover { background: var(--control-hover); color: var(--ink); }
  .window-controls button:active { transform: scale(.92); }
  h1 {
    font-size: 13px; font-weight: 600; color: var(--dim);
    text-transform: uppercase; letter-spacing: .04em;
    margin: 0 28px 14px 0;
  }
  .task { margin-bottom: 16px; }
  .task-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
  .said-line {
    font-size: 13px; line-height: 1.4; color: var(--ink);
    margin: 0 0 4px 0; padding-left: 12px; position: relative;
  }
  .said-line::before { content: "–"; position: absolute; left: 0; color: var(--dim); }
</style>
</head>
<body>
  <div class="window-controls">
    <button id="close-btn" title="Закрыть" aria-label="Закрыть окно">×</button>
  </div>
  <h1 id="recap-title">Прошлый дейлик</h1>
  <div id="recap-tasks"></div>
<script>
function renderRecap(data) {
  const dt = new Date(data.generated_at);
  const dateLabel = dt.toLocaleDateString("ru-RU") + " " +
    dt.toLocaleTimeString("ru-RU", {hour: "2-digit", minute: "2-digit"});
  document.getElementById("recap-title").textContent = "Прошлый дейлик — " + dateLabel;
  const container = document.getElementById("recap-tasks");
  container.innerHTML = "";
  data.tasks.forEach(task => {
    const div = document.createElement("div");
    div.className = "task";
    const title = document.createElement("div");
    title.className = "task-title";
    title.textContent = task.title;
    div.appendChild(title);
    task.said.forEach(line => {
      const p = document.createElement("p");
      p.className = "said-line";
      p.textContent = line;
      div.appendChild(p);
    });
    container.appendChild(div);
  });
}
document.getElementById("close-btn").addEventListener("click", () => {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.close_recap_window();
  }
});
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add recap.html
git commit -m "$(cat <<'EOF'
Add recap.html: small window that renders a saved daily recap

Same dark tokens as the other three placements. Close button calls
pywebview.api.close_recap_window() — wired up in the next task.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XqfxwnWQmrMQmeCunmZiTU
EOF
)"
```

---

## Task 4: Wire recap generation and the recap window into `run_second_screen.py`

**Files:**
- Modify: `run_second_screen.py:1-20` (imports), `run_second_screen.py:190-233` (`_run_live`), `run_second_screen.py:235-262` (`__main__`)

**Interfaces:**
- Consumes: `recap.build_recap`, `recap.save_recap`, `recap.latest_recap` (Task 2); `recap.html`'s `renderRecap(data)` and `close_recap_window` API (Task 3).

No automated test — this is pywebview window wiring, same convention as the rest of this file. Verified manually in Step 5.

- [ ] **Step 1: Add the import**

In `run_second_screen.py`, after the existing `from meeting import Line, Meeting` line, add:

```python
from recap import build_recap, latest_recap, save_recap
```

- [ ] **Step 2: Save the recap on close, without blocking**

In `_run_live` (`run_second_screen.py`), find:

```python
        session = LiveAudioSession(speechmatics_key, on_turn)
        session.start()
        window.events.closing += session.stop
        print("Живой микрофон запущен — говорите; закройте окно, чтобы остановить.")
```

Replace with:

```python
        session = LiveAudioSession(speechmatics_key, on_turn)
        session.start()
        window.events.closing += session.stop

        def _save_recap_on_close():
            # Non-daemon: closing the window must not wait for this, but the
            # process itself needs to stay alive until it's done writing —
            # see docs/superpowers/specs/2026-09-02-daily-recap-design.md
            # ("Не блокировать закрытие окна").
            def _do_save():
                records = build_recap(meeting, agenda, api_key)
                if records:
                    save_recap(records)

            threading.Thread(target=_do_save, daemon=False).start()

        window.events.closing += _save_recap_on_close
        print("Живой микрофон запущен — говорите; закройте окно, чтобы остановить.")
```

- [ ] **Step 3: Conditionally create the recap window at `--live` startup**

In `run_second_screen.py`, find the `__main__` block:

```python
if __name__ == "__main__":
    window = webview.create_window(
        "Второй экран",
        "second_screen.html",
        width=1100,
        height=760,
        frameless=True,
        on_top=True,
        transparent=True,
    )

    def minimize_window():
        window.minimize()

    def close_window():
        # destroy() called synchronously from inside this JS-bridge callback
        # left the window stuck showing a perpetual loading state instead of
        # closing (2 сен, live click test) — the callback's own thread is
        # what pywebview uses to deliver the JS promise result, and tearing
        # the window down mid-delivery never lets that resolve. Detaching
        # the destroy onto its own thread lets this call return normally.
        threading.Thread(target=window.destroy, daemon=True).start()

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    target = _run_live if "--live" in sys.argv else _run_replay
    webview.start(target, (window, loaded_event))
```

Replace with:

```python
if __name__ == "__main__":
    window = webview.create_window(
        "Второй экран",
        "second_screen.html",
        width=1100,
        height=760,
        frameless=True,
        on_top=True,
        transparent=True,
    )

    def minimize_window():
        window.minimize()

    def close_window():
        # destroy() called synchronously from inside this JS-bridge callback
        # left the window stuck showing a perpetual loading state instead of
        # closing (2 сен, live click test) — the callback's own thread is
        # what pywebview uses to deliver the JS promise result, and tearing
        # the window down mid-delivery never lets that resolve. Detaching
        # the destroy onto its own thread lets this call return normally.
        threading.Thread(target=window.destroy, daemon=True).start()

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set

    is_live = "--live" in sys.argv
    if is_live:
        prior_recap = latest_recap()
        if prior_recap is not None:
            recap_window = webview.create_window(
                "Прошлый дейлик",
                "recap.html",
                width=380,
                height=500,
                x=1160,
                y=40,
                frameless=True,
                on_top=True,
                transparent=True,
            )

            def close_recap_window():
                threading.Thread(target=recap_window.destroy, daemon=True).start()

            recap_window.expose(close_recap_window)
            recap_loaded_event = threading.Event()
            recap_window.events.loaded += recap_loaded_event.set

            def _show_recap():
                recap_loaded_event.wait(timeout=10)
                recap_window.evaluate_js(f"renderRecap({json.dumps(prior_recap, ensure_ascii=False)})")

            threading.Thread(target=_show_recap, daemon=True).start()

    target = _run_live if is_live else _run_replay
    webview.start(target, (window, loaded_event))
```

- [ ] **Step 4: Run the full test suite**

Run: `venv/bin/python -m pytest -q`
Expected: PASS — no regressions (this task adds no new automated tests, only wiring).

- [ ] **Step 5: Manual verification (real Groq call, real window)**

1. Delete any old test recaps: `rm -rf recaps/`
2. Launch: `venv/bin/python run_second_screen.py --live`
3. Confirm: no recap window appears (no prior recap yet) — expected, this is the first run.
4. Speak a couple of sentences that would match a task from `fixtures/sprint.json`'s agenda (check the file for a real task title to reference by name).
5. Close the main window via the "×" button. Confirm the window closes immediately (not stuck loading — this was the bug fixed earlier today).
6. Watch the terminal/process list: the Python process should keep running a few more seconds after the window closes, then exit on its own once the recap is saved.
7. Confirm a new file appeared under `recaps/*.json` with a non-empty `tasks` list (open it and read it).
8. Re-launch: `venv/bin/python run_second_screen.py --live`
9. Confirm a second, small "Прошлый дейлик" window appears next to the main one, showing the task title(s) and said-lines from step 7's file.
10. Click its own "×" — confirm it closes independently without affecting the main window.
11. Note (don't fix unless actually broken): check what happens if you close the main window while the recap window is still open — if it produces any error or leaves an orphaned process, report it before deciding whether it needs a follow-up fix.

- [ ] **Step 6: Commit**

```bash
git add run_second_screen.py
git commit -m "$(cat <<'EOF'
Wire the post-daily recap into run_second_screen.py --live

Recap is generated in a non-daemon background thread on window close
(never blocks closing) and, on the next --live launch, shown in its own
small window next to the main one if a saved recap exists.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XqfxwnWQmrMQmeCunmZiTU
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** source (`Meeting.lines` not `.said`) → Task 2; `get_hints` reuse + `lookback_seconds` fix found during spec self-review → Task 1; JSON format + `recaps/` gitignore → Task 2; non-blocking close via non-daemon thread → Task 4 Step 2; recap window + its own close-button fix reuse → Tasks 3–4; "no read-tracking, always show latest" → `latest_recap()` design in Task 2 (no state beyond "which file is newest"). All spec sections covered.
- **Placeholder scan:** none found — every step has real, complete code.
- **Type consistency:** `build_recap` returns `list[dict]` with `{"key", "title", "said"}` keys throughout (Task 2 impl, Task 2 tests, Task 4's `save_recap(records)` call, `recap.html`'s `data.tasks[i].title/.said`) — consistent everywhere it's used.
