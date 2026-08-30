# Второй экран (шаг 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "второй экран" (second screen) placement end-to-end — `hit_words` on the matcher, a public `age_label` + new `agenda_row` in `facts.py`, `hit_words` on `Line`, and a three-column `second_screen.html` + `run_second_screen.py` pywebview window that shows the full `Meeting` state (unlike the reduced "Полоса") by replaying `fixtures/sample_daily_transcript.json` with real Groq calls.

**Architecture:** Two small extensions to already-implemented, already-tested modules (`match_core.py` gains `hit_words` on `MatchResult`; `facts.py` gains a public `age_label` and a new `agenda_row`; `meeting.py`'s `Line` gains a `hit_words` field) feed a new leaf UI page (`second_screen.html`) and a new driver (`run_second_screen.py`) that mirrors the already-approved `polosa.html`/`run_polosa_replay.py` pair — same pywebview approach, same real Groq call, same techspec style tokens — but renders all three columns fully instead of the reduced Полоса subset.

**Tech Stack:** Python 3.14 (this project's `venv`), existing deps only (`pymorphy3`, `requests`, `pywebview`, `pytest`) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-second-screen-design.md` — read it alongside this plan.

## Global Constraints

- No code in this project touches `~/Desktop/Rinat Work/live_copilot_poc` or `~/Desktop/Rinat Work/meeting_copilot` — fully standalone.
- No test data or committed fixture may copy real Tranio task titles, sprint data, or coworker names verbatim. `fixtures/sample_daily_transcript.json` and `fixtures/sprint.json` are existing invented (NOVA-scenario) fixtures — reuse them as-is, do not replace with real data.
- `git commit` after every task in this project's own repo (`~/Desktop/Bot TG/daily_standup_matcher`), never `--no-verify`. No push to any remote unless asked.
- `MatchResult` and `Line` stay backward compatible — the new fields (`hit_words` on both) get defaults so every existing test in the 60-test suite keeps passing unmodified.
- "Колонка" (the third physical placement) is explicitly out of scope for this plan — same principle, different template, a separate future pass.
- Live microphone / real Jira token / diarization stay out of scope, same as "Полоса".
- LLM calls (`hints.get_hints`) already degrade gracefully on timeout/error — no change to that contract in this plan.
- Run `venv/bin/python3 -m pytest -v` (not plain `pytest`) — this project's dependencies are installed into its own `venv`, confirmed present at `venv/bin/python3`.
- Starting test count, confirmed by running the suite before writing this plan: **60 passed**. Each task's "Expected: PASS (N tests)" step below is this baseline plus that task's new tests, cumulative.

---

## Task 1: `match_core.py` — `hit_words` on `MatchResult`

**Files:**
- Modify: `match_core.py`
- Test: `tests/test_match_core.py` (extend)

**Interfaces:**
- Consumes: nothing new — same `Task`, `lemmatize`, `stopword_discount` already imported.
- Produces: `MatchResult` gains `hit_words: list[str] = field(default_factory=list)` (existing `task_key`, `confidence`, `reason` unchanged, still positional-compatible). New private `_hit_words(tokens: list[str], lemmas: list[str], title_lemmas: set[str]) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_match_core.py` (append at the end of the file; add `_hit_words` to the existing `match_core` import at the top):

```python
from match_core import MatchResult, _hit_words, compute_idf_weights, extract_number_mentions, match, score_task
```

(replace the existing `from match_core import ...` line at the top of the file with this one — same names plus `_hit_words`)

```python
def test_hit_words_uses_original_tokens_not_lemmas():
    tokens = ["сделок", "было", "много"]
    lemmas = ["сделка", "быть", "много"]
    title_lemmas = {"сделка", "клиент"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["сделок"]


def test_hit_words_dedups_repeated_lemma():
    tokens = ["сделка", "и", "сделке"]
    lemmas = ["сделка", "и", "сделка"]
    title_lemmas = {"сделка"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["сделка"]


def test_hit_words_preserves_order_of_appearance():
    tokens = ["клиент", "и", "сделка"]
    lemmas = ["клиент", "и", "сделка"]
    title_lemmas = {"сделка", "клиент"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["клиент", "сделка"]


def test_hit_words_no_false_hits_on_non_overlapping_words():
    tokens = ["погода", "сегодня", "хорошая"]
    lemmas = ["погода", "сегодня", "хороший"]
    title_lemmas = {"сделка"}
    assert _hit_words(tokens, lemmas, title_lemmas) == []


def test_match_result_hit_words_for_explicit_number():
    results = match("ладно возьму 214 в работу", AGENDA)
    assert results[0].hit_words == ["214"]


def test_match_result_hit_words_for_title_words():
    results = match("коллеги, там синхронизация остатков склада ещё не готова", AGENDA)
    assert results[0].task_key == "NOVA-10299"
    assert results[0].hit_words == ["синхронизация", "остатков", "склада"]


def test_match_result_hit_words_empty_when_no_match():
    results = match("ну короче вот как бы", AGENDA)
    assert results == []
```

Note on `test_match_result_hit_words_for_title_words`: the expected `hit_words` list was worked out by hand from `_tokenize`/`lemmatize` on both the utterance and `NOVA-10299`'s title ("Синхронизация остатков склада с кассой") — `синхронизация`→`синхронизация`, `остатков`→`остаток`, `склада`→`склад` all appear in both, in that order, with no repeats. This utterance is the same one already covered by the passing `test_case2_exact_title_word_match`, so the task/reason assertions are not new risk — only `hit_words` is new. If the exact list doesn't match after implementation (e.g. a pymorphy3 lemma differs from what's assumed here), print `results[0].hit_words` and correct the assertion to the actual (correct) output — don't force the implementation to fit a wrong prediction.

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_match_core.py -v`
Expected: FAIL — `ImportError: cannot import name '_hit_words' from 'match_core'`

- [ ] **Step 3: Implement `hit_words` in `match_core.py`**

Modify `match_core.py`:

1. Change the dataclass import line from `from dataclasses import dataclass` to `from dataclasses import dataclass, field`.

2. Add this new function right after `score_task` and before `MatchResult`:

```python
def _hit_words(tokens: list[str], lemmas: list[str], title_lemmas: set[str]) -> list[str]:
    seen: set[str] = set()
    hits: list[str] = []
    for token, lemma in zip(tokens, lemmas):
        if lemma in title_lemmas and lemma not in seen:
            seen.add(lemma)
            hits.append(token)
    return hits
```

3. Add the new field to `MatchResult`:

```python
@dataclass(frozen=True)
class MatchResult:
    task_key: str
    confidence: float
    reason: str
    hit_words: list[str] = field(default_factory=list)
```

4. In `match()`, change the first two lines of the body from:

```python
    idf = compute_idf_weights(agenda)
    utterance_lemmas = lemmatize(_tokenize(utterance))
```

to:

```python
    idf = compute_idf_weights(agenda)
    tokens = _tokenize(utterance)
    utterance_lemmas = lemmatize(tokens)
```

5. In the explicit-number loop, change:

```python
            if is_full_match or is_suffix_match:
                results.append(MatchResult(task.key, 1.0, "explicit_number"))
                matched_keys.add(task.key)
                break
```

to:

```python
            if is_full_match or is_suffix_match:
                results.append(MatchResult(task.key, 1.0, "explicit_number", hit_words=[number]))
                matched_keys.add(task.key)
                break
```

6. In the title-words block, change:

```python
    if scored:
        top_task, top_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
        if top_score - runner_up_score >= REQUIRED_MARGIN:
            results.append(MatchResult(top_task.key, top_score, "title_words"))
```

to:

```python
    if scored:
        top_task, top_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
        if top_score - runner_up_score >= REQUIRED_MARGIN:
            title_lemmas = set(lemmatize(_tokenize(top_task.title)))
            hit_words = _hit_words(tokens, utterance_lemmas, title_lemmas)
            results.append(MatchResult(top_task.key, top_score, "title_words", hit_words=hit_words))
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (67 tests: 60 baseline + 7 new)

- [ ] **Step 5: Commit**

```bash
git add match_core.py tests/test_match_core.py
git commit -m "Task 1: match_core.py — hit_words on MatchResult"
```

---

## Task 2: `facts.py` — public `age_label` + `agenda_row`

**Files:**
- Modify: `facts.py`
- Test: `tests/test_facts.py` (extend)

**Interfaces:**
- Consumes: `Task` (unchanged), `REOPENED_STATUS` from `agenda.py`.
- Produces: `age_label(updated_at: datetime, now: datetime) -> str` (renamed from private `_age_label`, same behavior). `agenda_row(task: Task, is_alarm: bool, now: datetime | None = None) -> tuple[str, str | None]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_facts.py` (append at the end; add these two imports at the top alongside the existing ones):

```python
from agenda import REOPENED_STATUS
from facts import age_label, agenda_row, build_facts
```

(this replaces the existing `from facts import build_facts` line)

```python
def test_age_label_is_public_and_matches_build_facts_wording():
    assert age_label(datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc), NOW) == "Обновлено вчера"
    assert age_label(NOW, NOW) == "Обновлено сегодня"


def test_agenda_row_basic_line_no_alarm():
    row, annotation = agenda_row(_task(), is_alarm=False, now=NOW)
    assert row == "В работе · Дарья Ковалёва · Обновлено вчера"
    assert annotation is None


def test_agenda_row_alarm_and_reopened_gets_annotation():
    task = _task(status=REOPENED_STATUS)
    row, annotation = agenda_row(task, is_alarm=True, now=NOW)
    assert row == f"{REOPENED_STATUS} · Дарья Ковалёва · Обновлено вчера"
    assert annotation == "задачу открыли повторно"


def test_agenda_row_alarm_but_not_reopened_gets_no_annotation():
    # is_alarm=True can also mean "stale >= 4 days", which has no separate
    # annotation in the real mockup — only the reopened case does.
    task = _task(status="В работе")
    row, annotation = agenda_row(task, is_alarm=True, now=NOW)
    assert annotation is None


def test_agenda_row_reopened_but_not_the_alarm_task_gets_no_annotation():
    # is_alarm is decided by the caller against agenda.pick_alarm() for the
    # whole agenda — a merely-reopened task that isn't THE alarm task must
    # not get the annotation on its own.
    task = _task(status=REOPENED_STATUS)
    row, annotation = agenda_row(task, is_alarm=False, now=NOW)
    assert annotation is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_facts.py -v`
Expected: FAIL — `ImportError: cannot import name 'age_label' from 'facts'`

- [ ] **Step 3: Implement in `facts.py`**

Replace the full contents of `facts.py` with:

```python
from datetime import datetime, timezone

from agenda import REOPENED_STATUS
from sprint_snapshot import Task

CRITICAL_PRIORITY = "критический"
RELEASE_LABEL = "релиз_текущий_спринт"


def age_label(updated_at: datetime, now: datetime) -> str:
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
    lines.append(age_label(task.updated_at, now))
    if task.created is not None:
        lines.append(f"Создана {task.created:%d.%m}")
    return lines


def agenda_row(task: Task, is_alarm: bool, now: datetime | None = None) -> tuple[str, str | None]:
    now = now or datetime.now(timezone.utc)
    row = f"{task.status} · {task.assignee} · {age_label(task.updated_at, now)}"
    annotation = "задачу открыли повторно" if is_alarm and task.status == REOPENED_STATUS else None
    return row, annotation
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (72 tests: 67 + 5 new)

- [ ] **Step 5: Commit**

```bash
git add facts.py tests/test_facts.py
git commit -m "Task 2: facts.py — public age_label + agenda_row"
```

---

## Task 3: `meeting.py` — `hit_words` on `Line`

**Files:**
- Modify: `meeting.py`
- Test: `tests/test_meeting.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Line` gains `hit_words: list[str] = field(default_factory=list)` (existing `t`, `who`, `text`, `task` unchanged, still positional-compatible). `Meeting` unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_meeting.py` (append at the end):

```python
def test_line_hit_words_defaults_to_empty_list():
    line = Line(t=1.0, who="Дарья", text="привет")
    assert line.hit_words == []


def test_line_hit_words_can_be_set():
    line = Line(t=1.0, who="Дарья", text="возьму 214 в работу", task="NOVA-10214", hit_words=["214"])
    assert line.hit_words == ["214"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meeting.py -v`
Expected: FAIL — `TypeError: Line.__init__() got an unexpected keyword argument 'hit_words'`

- [ ] **Step 3: Implement in `meeting.py`**

Change the `Line` dataclass at the top of `meeting.py` from:

```python
@dataclass
class Line:
    t: float
    who: str | None
    text: str
    task: str | None = None
```

to:

```python
@dataclass
class Line:
    t: float
    who: str | None
    text: str
    task: str | None = None
    hit_words: list[str] = field(default_factory=list)
```

(`field` is already imported at the top of `meeting.py` — no import change needed.)

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (74 tests: 72 + 2 new)

- [ ] **Step 5: Commit**

```bash
git add meeting.py tests/test_meeting.py
git commit -m "Task 3: meeting.py — hit_words on Line"
```

---

## Task 4: `second_screen.html` — the three-column page

**Files:**
- Create: `second_screen.html`

**Interfaces:**
- Consumes: a `renderMeeting(stateJson)` global JS function, called externally (by Task 5's pywebview wiring) with a JSON-serialized state:
  ```
  {
    phase: "before" | "live" | "after",
    elapsed_s: number,
    lines: [{who: string|null, text: string, task: string|null, hit_words: string[]}],
    agenda: {
      done: [{key, title, row, annotation: string|null, alarm: boolean}],
      remaining: [{key, title, row, annotation: string|null, alarm: boolean}]
    },
    current_task: {key, title, facts: string[], said: string[], ask: string|null} | null
  }
  ```
- Produces: nothing consumed by later tasks — this is a leaf, same as `polosa.html` was for the previous plan.

- [ ] **Step 1: Write `second_screen.html`**

```html
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Второй экран</title>
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
  body {
    background: var(--page-bg);
    backdrop-filter: blur(18px);
    color: var(--ink);
    overflow: hidden;
  }
  @media (prefers-reduced-transparency: reduce) {
    body { background: #131217; backdrop-filter: none; }
  }

  .app { display: flex; height: 100vh; }

  .col { padding: 20px; overflow-y: auto; }
  .col + .col { border-left: 1px solid var(--line); }
  .col-heard { width: 330px; flex-shrink: 0; }
  .col-recorded { flex: 1; min-width: 0; }
  .col-hints { width: 340px; flex-shrink: 0; }

  .col-header { display: flex; align-items: center; margin: 0 0 14px; }
  .section-label {
    font-size: 13px; font-weight: 600; letter-spacing: 0; color: var(--dim);
  }
  .body-text { font-size: 15px; font-weight: 400; line-height: 1.45; margin: 0; }
  .mute { color: var(--mute); }

  .live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--live);
    display: inline-block; margin-right: 6px;
    animation: breathe 1.8s ease-in-out infinite;
  }
  @keyframes breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) {
    .live-dot { animation: none; opacity: 0.85; }
  }

  .heard-line { margin-bottom: 16px; }
  .heard-who { font-size: 12px; font-weight: 600; color: var(--dim); margin-bottom: 4px; }
  .heard-line .hit {
    text-decoration: underline dotted;
    text-decoration-color: var(--dim);
  }

  .agenda-section { margin-bottom: 20px; }
  .agenda-section .section-label { margin-bottom: 10px; }
  .agenda-row { margin-bottom: 12px; }
  .agenda-row-title { font-size: 14px; font-weight: 600; color: var(--ink); line-height: 1.3; }
  .agenda-row-fact { font-size: 13px; color: var(--mute); margin-top: 2px; }
  .agenda-row-annotation { font-size: 12px; color: var(--alarm); margin-top: 2px; font-weight: 600; }
  .agenda-row.alarm .agenda-row-title,
  .agenda-row.alarm .agenda-row-fact { color: var(--alarm); }

  .hint-title { font-size: 18px; font-weight: 600; letter-spacing: -0.015em; line-height: 1.2; margin: 12px 0 12px; }
  .hint-block { margin-bottom: 18px; }
  .hint-block .section-label { margin-bottom: 8px; }
  .hint-block p { margin: 0 0 4px; }

  .ask-pill {
    background: var(--accent-bg); border: 1px solid var(--accent-border);
    border-radius: 10px; padding: 10px 12px; color: var(--accent-text);
    font-size: 14px; line-height: 1.4;
  }
</style>
</head>
<body>
  <div class="app">
    <div class="col col-heard">
      <div class="col-header">
        <span class="live-dot" id="live-dot" style="display:none;"></span>
        <span class="section-label">Слышу</span>
      </div>
      <div id="heard-lines"></div>
    </div>
    <div class="col col-recorded">
      <div class="col-header"><span class="section-label">Записал</span></div>
      <div id="recorded-sections"></div>
    </div>
    <div class="col col-hints">
      <div class="col-header"><span class="section-label">Подсказываю</span></div>
      <p class="hint-title" id="hint-title"></p>
      <div class="hint-block">
        <div class="section-label">В Jira</div>
        <div id="hint-facts"></div>
      </div>
      <div class="hint-block">
        <div class="section-label">Сказали</div>
        <div id="hint-said"></div>
      </div>
      <div class="hint-block">
        <div class="section-label">Спроси</div>
        <div id="hint-ask"><span class="mute">—</span></div>
      </div>
    </div>
  </div>

<script>
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function underlineHtml(text, hitWords) {
  const escaped = escapeHtml(text);
  if (!hitWords || hitWords.length === 0) return escaped;
  const pattern = hitWords
    .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const re = new RegExp("(" + pattern + ")", "gi");
  return escaped.replace(re, '<span class="hit">$1</span>');
}

function renderHeard(state) {
  const container = document.getElementById("heard-lines");
  document.getElementById("live-dot").style.display = state.phase === "live" ? "inline-block" : "none";

  const wasNearBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) < 24;
  container.innerHTML = "";
  state.lines.forEach(line => {
    const row = document.createElement("div");
    row.className = "heard-line";
    const who = document.createElement("div");
    who.className = "heard-who";
    who.textContent = line.task ? `${line.who || "?"} → ${line.task}` : (line.who || "?");
    const text = document.createElement("p");
    text.className = "body-text";
    text.innerHTML = underlineHtml(line.text, line.hit_words);
    row.appendChild(who);
    row.appendChild(text);
    container.appendChild(row);
  });
  if (wasNearBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function buildAgendaRow(r) {
  const row = document.createElement("div");
  row.className = "agenda-row" + (r.alarm ? " alarm" : "");
  const title = document.createElement("div");
  title.className = "agenda-row-title";
  title.textContent = `${r.title} · ${r.key}`;
  const fact = document.createElement("div");
  fact.className = "agenda-row-fact";
  fact.textContent = r.row;
  row.appendChild(title);
  row.appendChild(fact);
  if (r.annotation) {
    const ann = document.createElement("div");
    ann.className = "agenda-row-annotation";
    ann.textContent = r.annotation;
    row.appendChild(ann);
  }
  return row;
}

function buildAgendaSection(label, rows) {
  const section = document.createElement("div");
  section.className = "agenda-section";
  const heading = document.createElement("div");
  heading.className = "section-label";
  heading.textContent = label;
  section.appendChild(heading);
  rows.forEach(r => section.appendChild(buildAgendaRow(r)));
  return section;
}

function renderRecorded(state) {
  const container = document.getElementById("recorded-sections");
  container.innerHTML = "";
  if (state.phase === "before") {
    container.appendChild(buildAgendaSection("Повестка", state.agenda.remaining));
    return;
  }
  if (state.agenda.done.length > 0) {
    container.appendChild(buildAgendaSection("Обсудили", state.agenda.done));
  }
  const secondLabel = state.phase === "after" ? "Не обсудили" : "Осталось";
  container.appendChild(buildAgendaSection(secondLabel, state.agenda.remaining));
}

function renderHints(state) {
  const titleEl = document.getElementById("hint-title");
  const factsEl = document.getElementById("hint-facts");
  const saidEl = document.getElementById("hint-said");
  const askEl = document.getElementById("hint-ask");

  if (!state.current_task) {
    titleEl.textContent = "";
    factsEl.innerHTML = "";
    saidEl.innerHTML = "";
    askEl.innerHTML = '<span class="mute">Подсказка появится, когда узнаю задачу</span>';
    return;
  }

  titleEl.textContent = state.current_task.title;

  factsEl.innerHTML = "";
  state.current_task.facts.forEach(f => {
    const p = document.createElement("p");
    p.className = "body-text mute";
    p.textContent = f;
    factsEl.appendChild(p);
  });

  saidEl.innerHTML = "";
  if (state.current_task.said.length === 0) {
    saidEl.innerHTML = '<span class="mute">—</span>';
  } else {
    state.current_task.said.forEach(s => {
      const p = document.createElement("p");
      p.className = "body-text";
      p.textContent = "– " + s;
      saidEl.appendChild(p);
    });
  }

  if (state.current_task.ask) {
    askEl.innerHTML = "";
    const pill = document.createElement("div");
    pill.className = "ask-pill";
    pill.textContent = state.current_task.ask;
    askEl.appendChild(pill);
  } else {
    askEl.innerHTML = '<span class="mute">—</span>';
  }
}

function renderMeeting(state) {
  renderHeard(state);
  renderRecorded(state);
  renderHints(state);
}

window.renderMeeting = renderMeeting;
</script>
</body>
</html>
```

- [ ] **Step 2: Manual visual check**

Open the file directly in a browser (`open second_screen.html`), then in the browser devtools console run:

```js
renderMeeting({
  phase: "live",
  elapsed_s: 95,
  lines: [
    {who: "Дарья", text: "Отчёты почти готовы, убираем последние дубли платежей от партнёров.", task: "NOVA-10214", hit_words: ["дубли", "платежей", "партнёров"]},
    {who: "Максим", text: "Ну, короче, всё окей, погнали дальше.", task: null, hit_words: []}
  ],
  agenda: {
    done: [
      {key: "NOVA-10214", title: "Отчёты — убираем дубли платежей от партнёров", row: "В работе · Дарья Ковалёва · Обновлено вчера", annotation: null, alarm: false}
    ],
    remaining: [
      {key: "NOVA-10299", title: "Синхронизация остатков склада с кассой", row: "Открыто повторно · Игорь Сафин · Обновлено 11 дней назад", annotation: "задачу открыли повторно", alarm: true},
      {key: "NOVA-10230", title: "Функционал заявок для поставщиков", row: "Backlog · Максим Орлов · Обновлено 7 дней назад", annotation: null, alarm: false}
    ]
  },
  current_task: {
    key: "NOVA-10214",
    title: "Отчёты — убираем дубли платежей от партнёров",
    facts: ["В работе · Дарья Ковалёва", "Обновлено вчера"],
    said: ["Дарья почти закончила с дублями платежей"],
    ask: "Максим уже проверил MR по дублям?"
  }
});
```

Expected: three columns render side by side (330px / flexible / 340px). Left column shows both lines, the first with "Дарья → NOVA-10214" label and "дубли"/"платежей"/"партнёров" underlined with a dotted underline, live dot breathing green next to "Слышу". Middle column shows "Обсудили" with the one done task, then "Осталось" with two remaining tasks, the NOVA-10299 row and its "задачу открыли повторно" annotation in the alarm red color, NOVA-10230 in normal ink/mute colors. Right column shows the task title, both fact lines, the one "Сказали" line prefixed with "–", and the accent-colored ask pill. Check against the techspec's 8 behavior rules by eye: color appears only on the alarm row/annotation, the live dot, and the ask pill — everything else is grayscale; no entrance animation on any element.

- [ ] **Step 3: Commit**

```bash
git add second_screen.html
git commit -m "Task 4: second_screen.html — three-column full view, techspec tokens + apple-design motion"
```

---

## Task 5: `run_second_screen.py` — pywebview wiring + integration test + README update

**Files:**
- Create: `run_second_screen.py`
- Test: `tests/test_second_screen_state.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `match()` (from `match_core.py`, Task 1), `Line`/`Meeting` (from `meeting.py`, Task 3), `build_facts`/`agenda_row` (from `facts.py`, Task 2), `build_agenda`/`pick_alarm` (from `agenda.py`, already existing), `get_hints` (from `hints.py`, already existing), `load_credential` (from `credentials.py`, already existing).
- Produces: `TEAM: list[str]`, `_state_json(meeting: Meeting, agenda: list[Task], alarm_task: Task | None) -> str`, `_agenda_rows(agenda, meeting, alarm_task) -> tuple[list[dict], list[dict]]` — all importable by the test, same pattern as `run_polosa_replay.py`'s `_state_json` was importable by `tests/test_state_json.py`.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_second_screen_state.py
import json

from agenda import build_agenda, pick_alarm
from meeting import Line, Meeting
from run_second_screen import TEAM, _state_json
from sprint_snapshot import load_sprint

EXPECTED_TOP_KEYS = {"phase", "elapsed_s", "lines", "agenda", "current_task"}


def _agenda():
    tasks = load_sprint("fixtures/sprint.json")
    return build_agenda(tasks, TEAM)


def test_state_json_top_level_keys():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert set(payload.keys()) == EXPECTED_TOP_KEYS


def test_before_phase_all_tasks_in_remaining_none_done():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["agenda"]["done"] == []
    assert [r["key"] for r in payload["agenda"]["remaining"]] == [t.key for t in agenda]


def test_alarm_row_flagged_on_the_reopened_task():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    # fixtures/sprint.json has exactly one "Открыто повторно" task: NOVA-10299
    assert alarm_task.key == "NOVA-10299"
    meeting = Meeting(phase="live", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    remaining = payload["agenda"]["remaining"]
    alarm_row = next(r for r in remaining if r["key"] == "NOVA-10299")
    assert alarm_row["alarm"] is True
    assert alarm_row["annotation"] == "задачу открыли повторно"
    others = [r for r in remaining if r["key"] != "NOVA-10299"]
    assert all(r["alarm"] is False for r in others)
    assert all(r["annotation"] is None for r in others)


def test_done_tasks_move_from_remaining_to_done_in_recognition_order():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.mark_recognized("NOVA-10214")
    meeting.mark_recognized("NOVA-10201")

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert [r["key"] for r in payload["agenda"]["done"]] == ["NOVA-10214", "NOVA-10201"]
    remaining_keys = [r["key"] for r in payload["agenda"]["remaining"]]
    assert "NOVA-10214" not in remaining_keys
    assert "NOVA-10201" not in remaining_keys


def test_current_task_includes_facts_and_progressive_said():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.mark_recognized("NOVA-10214")
    meeting.set_hints(["первая строка", "вторая строка"], "вопрос?")
    meeting.reveal_next_said()

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    ct = payload["current_task"]
    assert ct["key"] == "NOVA-10214"
    assert len(ct["facts"]) >= 2
    assert ct["said"] == ["первая строка"]
    assert ct["ask"] == "вопрос?"


def test_current_task_is_none_before_recognition():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="before", remaining_count=len(agenda))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["current_task"] is None


def test_lines_carry_hit_words_and_task_key():
    agenda = _agenda()
    alarm_task = pick_alarm(agenda)
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    meeting.add_line(Line(t=1.0, who="Дарья", text="возьму 214 в работу", task="NOVA-10214", hit_words=["214"]))

    payload = json.loads(_state_json(meeting, agenda, alarm_task))

    assert payload["lines"][0]["task"] == "NOVA-10214"
    assert payload["lines"][0]["hit_words"] == ["214"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_second_screen_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_second_screen'`

- [ ] **Step 3: Implement `run_second_screen.py`**

```python
import json
import re
import sys
import time

import webview

from agenda import build_agenda, pick_alarm
from credentials import load_credential
from facts import agenda_row, build_facts
from hints import get_hints
from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import load_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
GROQ_KEY_PATH = "~/.credentials/groq_api_key.env"
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


def _primary_match(results):
    """Pick the result to drive a Line's task/hit_words and which task's
    hints get fetched. match() sorts by task recency, not confidence, so the
    first result isn't necessarily the most trustworthy one. Prefer an
    explicit_number match (confidence 1.0) over a title_words match when both
    are present; otherwise fall back to the first (most recent) result.
    """
    if not results:
        return None
    number_matches = [r for r in results if r.reason == "explicit_number"]
    return number_matches[0] if number_matches else results[0]


def _agenda_rows(agenda, meeting, alarm_task):
    by_key = {t.key: t for t in agenda}

    def _row(task):
        is_alarm = alarm_task is not None and task.key == alarm_task.key
        row, annotation = agenda_row(task, is_alarm=is_alarm)
        return {"key": task.key, "title": task.title, "row": row, "annotation": annotation, "alarm": is_alarm}

    done_rows = [_row(by_key[key]) for key in meeting.done]
    remaining_rows = [_row(t) for t in agenda if t.key not in meeting.done]
    return done_rows, remaining_rows


def _state_json(meeting: Meeting, agenda, alarm_task) -> str:
    current_task = None
    if meeting.current:
        task = next((t for t in agenda if t.key == meeting.current), None)
        if task:
            current_task = {
                "key": task.key,
                "title": task.title,
                "facts": build_facts(task),
                "said": meeting.said,
                "ask": meeting.ask,
            }
    lines = [
        {"who": l.who, "text": l.text, "task": l.task, "hit_words": l.hit_words}
        for l in meeting.lines
    ]
    done_rows, remaining_rows = _agenda_rows(agenda, meeting, alarm_task)
    return json.dumps({
        "phase": meeting.phase,
        "elapsed_s": meeting.elapsed_s,
        "lines": lines,
        "agenda": {"done": done_rows, "remaining": remaining_rows},
        "current_task": current_task,
    })


def _run_replay(window):
    try:
        time.sleep(3)  # let the window/page finish loading before the first push

        tasks = load_sprint("fixtures/sprint.json")
        agenda = build_agenda(tasks, TEAM)
        alarm_task = pick_alarm(agenda)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(GROQ_KEY_PATH, "GROQ_API_KEY")

        meeting = Meeting(phase="before", remaining_count=len(agenda))
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
        time.sleep(2)
        meeting.phase = "live"

        t = 0.0
        for turn in transcript:
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause

            results = match(turn["text"], agenda)
            primary = _primary_match(results)
            task_key = primary.task_key if primary else None
            hit_words = primary.hit_words if primary else []
            meeting.add_line(Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key, hit_words=hit_words))
            for r in results:
                meeting.mark_recognized(r.task_key)

            window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

            if primary:
                task = next(x for x in agenda if x.key == primary.task_key)
                said, ask = get_hints(meeting.lines, task, api_key)
                meeting.set_hints(said, ask)
                window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

                while meeting.reveal_next_said():
                    time.sleep(1.2)
                    window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

        meeting.phase = "after"
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
    except Exception as e:
        print(f"second screen replay failed: {e}", file=sys.stderr)
        try:
            window.evaluate_js(
                f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}"
            )
        except Exception:
            pass


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
    webview.start(_run_replay, window)
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python3 -m pytest -v`
Expected: PASS (81 tests: 74 + 7 new)

- [ ] **Step 5: MANUAL end-to-end check (required before this task counts as done)**

Run: `venv/bin/python3 run_second_screen.py`

Expected: a full 1100×760 window opens. After ~3s it shows the "before" phase with a single "Повестка" list in the middle column (all 6 tasks, no "Обсудили"/"Осталось" split) and empty "Слышу"/"Подсказываю" columns. ~2s later it switches to "live" and starts playing the 6 invented utterances with realistic pauses: the left column fills with lines (some tagged "→ KEY" with underlined hit words), the middle column splits into "Обсудили" (growing) / "Осталось" (shrinking), the NOVA-10299 row shows red with "задачу открыли повторно" whenever it's still in "Осталось", the right column shows the current task's title/facts/progressively-revealed "Сказали" lines from the real Groq call/ask pill. It ends in "after" phase with "Обсудили" unchanged and the second section relabeled "Не обсудили". Check by eye against techspec's 8 behavior rules (nothing disappears, only fades; scroll in "Слышу" doesn't jump when already near the bottom; no entrance animation on text swaps; color only on alarm row/annotation, live dot, and ask pill). If anything looks wrong (fabricated "Сказали" content, layout not matching 330/flex/340, missing alarm row), fix it and re-run — do not consider Task 5 done until this manual check looks right.

- [ ] **Step 6: Update `README.md`**

Replace the existing "Known gaps in this iteration" section (the last section of the file) with:

```markdown
- `second_screen.html` + `run_second_screen.py` — the "второй экран" full three-
  column view (Слышу / Записал / Подсказываю), same pywebview approach and real
  Groq call as "Полоса", but rendering the complete `Meeting` state: full
  scrolling transcript with underlined `hit_words` and "→ KEY" tags, the full
  agenda split by phase with the alarm row in red, all 5 Jira facts, and the
  progressive "Сказали" reveal that "Полоса" computed but never displayed.

## Known gaps in this iteration

Not implemented: live microphone / Speechmatics STT (still reads an invented
transcript file), real Jira snapshot (still `fixtures/sprint.json`), speaker
diarization, the "Колонка" placement (third physical layout — same data,
different template, not built yet), the Начать/Сначала button's click handler
on "Полоса" (the replay auto-starts instead — see
`docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why).
```

- [ ] **Step 7: Commit**

```bash
git add run_second_screen.py tests/test_second_screen_state.py README.md
git commit -m "Task 5: run_second_screen.py — pywebview wiring, real Groq, README update"
```

---

## Plan Self-Review Notes

- **Spec coverage:** `hit_words` on `MatchResult`/`_hit_words()` (Task 1), public `age_label` + `agenda_row()` (Task 2), `hit_words` on `Line` (Task 3), all three "Слышу"/"Записал"/"Подсказываю" columns incl. underline+inline tag, phase-dependent agenda sections with alarm row, all 5 facts, progressive "Сказали" (Task 4), pywebview wiring mirroring `polosa.html`/`run_polosa_replay.py` + integration test on the `_state_json` contract (Task 5). "Колонка" and live-mic/real-Jira explicitly out of scope, matching the spec's own "Не входит" section.
- **No placeholders:** every step has runnable code; the manual-check steps (Task 4 Step 2, Task 5 Step 5) specify exact expected visual results, not "verify it looks right."
- **Type/name consistency checked:** `MatchResult(task_key, confidence, reason, hit_words)`, `_hit_words(tokens, lemmas, title_lemmas)`, `age_label(updated_at, now)`, `agenda_row(task, is_alarm, now)`, `Line(t, who, text, task, hit_words)`, `_state_json(meeting, agenda, alarm_task)`, `_agenda_rows(agenda, meeting, alarm_task)` — spelled identically everywhere used across tasks.
- **Real-data check:** no task commits real Tranio titles/names/keys — Task 4's manual-check payload and all new tests reuse the existing invented NOVA-scenario fixtures/data already in the repo.
- **Cumulative test count check:** 60 (baseline, confirmed by running the suite) → 67 (Task 1, +7) → 72 (Task 2, +5) → 74 (Task 3, +2) → 74 (Task 4, no automated tests, leaf HTML) → 81 (Task 5, +7).
