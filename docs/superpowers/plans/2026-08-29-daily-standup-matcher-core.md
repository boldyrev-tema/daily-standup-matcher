# Дейлик-матчер: ядро без интерфейса — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python module that, given a synthetic Jira-sprint snapshot and a finalized speech utterance, recognizes which sprint task(s) are being discussed — or stays silent when unsure — reconstructing the mechanism described in Rinat's techspec without access to his real code or transcripts.

**Architecture:** Two independent pure-function stages with no shared state between calls (besides a per-call IDF cache): `agenda.py` turns a raw task list into a filtered, sorted, ≤6-item agenda with at most one alarm task; `match_core.py` turns (utterance, agenda) into a list of recognized tasks via a number channel (explicit digits in speech) and a word-overlap channel (IDF-weighted lemma overlap with a ≥2-word minimum and a stopword discount), both honoring the "when in doubt, stay silent" rule via a score threshold + margin gate.

**Tech Stack:** Python 3.14 (this machine's `python3`), `pymorphy3` + `pymorphy3-dicts-ru` for Russian lemmatization (NOT `pymorphy2` — verified it does not install on Python 3.14 here), `pytest` for tests, stdlib `dataclasses`/`datetime`/`re`/`json` for everything else. No network access, no Jira, no STT — this is the "ядро без интерфейса" slice only.

**Spec:** `docs/superpowers/specs/2026-08-29-daily-standup-matcher-design.md` — read it alongside this plan; this plan implements it task-by-task and the spec's "Тестирование" section numbers the 12 required cases this plan's tests cover.

## Global Constraints

- No code in this project touches `~/Desktop/live_copilot_poc` or `~/Desktop/meeting_copilot` — this is a fully standalone project (spec: "Архитектура").
- No network calls, no real Jira access — `sprint_snapshot.py` reads only a local JSON fixture (spec: "Не входит в эту итерацию").
- No test data may copy real Tranio task titles, sprint data, or coworker names verbatim — all fixtures use invented data (spec: "Известные ограничения реконструкции").
- Lemmatization uses `pymorphy3`, not `pymorphy2` (verified incompatible with this machine's Python 3.14).
- `match()` returns `list[MatchResult]`, never a single `Optional[MatchResult]` — multiple tasks can be mentioned in one utterance (spec: `match_core.py` section).
- Stopwords apply a ×⅓ weight discount, they are never fully removed from consideration (spec: `stopwords.py` section).
- A title-word match requires at least 2 distinct overlapping lemmas — one shared word is never enough (spec: `match_core.py` section).
- Alarm is a single task pick across the whole agenda (reopened status beats ≥4-days-stale), never a per-task boolean flag (spec: `agenda.py` section).
- `git commit` after every task, in the project's own repo (`~/Desktop/daily_standup_matcher`), never `--no-verify`.

---

## Task 1: Project scaffolding + `sprint_snapshot.py`

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `sprint_snapshot.py`
- Create: `fixtures/sprint.json`
- Test: `tests/test_sprint_snapshot.py`

**Interfaces:**
- Produces: `Task` dataclass (`key: str`, `title: str`, `assignee: str`, `status: str`, `updated_at: datetime`) — every later task imports this. `load_sprint(path: str) -> list[Task]`.

- [ ] **Step 1: Write `.gitignore` and `requirements.txt`**

`.gitignore`:
```
venv/
__pycache__/
*.pyc
.pytest_cache/
```

`requirements.txt`:
```
pymorphy3
pymorphy3-dicts-ru
pytest
```

- [ ] **Step 2: Create/confirm the venv and install dependencies**

Run:
```bash
cd ~/Desktop/daily_standup_matcher
python3 -m venv venv   # skip if venv/ already exists
venv/bin/pip install -r requirements.txt
```
Expected: installs succeed, no errors (already verified working on this machine's Python 3.14 during spec research).

- [ ] **Step 3: Write the fixture data — `fixtures/sprint.json`**

Six invented tasks, none copied from real Tranio data. Keys share a fictional project prefix (`NOVA`) and have unique 3-digit suffixes (used later by the number-channel tests). Statuses/assignees are placeholders — the interesting content is the titles and dates, both needed by later tasks.

```json
[
  {
    "key": "NOVA-10201",
    "title": "Сделки — объединяем карточки клиентов после импорта",
    "assignee": "Дарья Ковалёва",
    "status": "Тестирование",
    "updated_at": "2026-08-24T10:00:00+00:00"
  },
  {
    "key": "NOVA-10214",
    "title": "Отчёты — убираем дубли платежей от партнёров",
    "assignee": "Дарья Ковалёва",
    "status": "В работе",
    "updated_at": "2026-08-27T09:00:00+00:00"
  },
  {
    "key": "NOVA-10230",
    "title": "Функционал заявок для поставщиков",
    "assignee": "Максим Орлов",
    "status": "Backlog",
    "updated_at": "2026-08-23T09:00:00+00:00"
  },
  {
    "key": "NOVA-10267",
    "title": "Выгрузка контактов в старую систему",
    "assignee": "Полина Реброва",
    "status": "В работе",
    "updated_at": "2026-08-20T09:00:00+00:00"
  },
  {
    "key": "NOVA-10288",
    "title": "Выгрузка контактов в новую систему",
    "assignee": "Полина Реброва",
    "status": "В работе",
    "updated_at": "2026-08-21T09:00:00+00:00"
  },
  {
    "key": "NOVA-10299",
    "title": "Синхронизация остатков склада с кассой",
    "assignee": "Игорь Сафин",
    "status": "Открыто повторно",
    "updated_at": "2026-08-19T09:00:00+00:00"
  }
]
```

- [ ] **Step 4: Write the failing test**

`tests/test_sprint_snapshot.py`:
```python
from datetime import datetime, timezone

from sprint_snapshot import Task, load_sprint


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
```

- [ ] **Step 5: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_sprint_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sprint_snapshot'`

- [ ] **Step 6: Write minimal implementation**

`sprint_snapshot.py`:
```python
import json
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Task:
    key: str
    title: str
    assignee: str
    status: str
    updated_at: datetime


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
        )
        for item in raw
    ]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_sprint_snapshot.py -v`
Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add .gitignore requirements.txt sprint_snapshot.py fixtures/sprint.json tests/test_sprint_snapshot.py
git commit -m "Add sprint_snapshot.py: Task model + fixture loader, with synthetic 6-task fixture"
```

---

## Task 2: `stopwords.py`

**Files:**
- Create: `stopwords.py`
- Test: `tests/test_stopwords.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `STOPWORDS: frozenset[str]`, `stopword_discount(word: str) -> float` — used by `match_core.score_task` in Task 5.

- [ ] **Step 1: Write the failing test**

`tests/test_stopwords.py`:
```python
from stopwords import STOPWORDS, stopword_discount


def test_known_stopword_gets_third_weight():
    assert "ну" in STOPWORDS
    assert stopword_discount("ну") == 1 / 3


def test_content_word_gets_full_weight():
    assert "сделка" not in STOPWORDS
    assert stopword_discount("сделка") == 1.0


def test_stopword_list_is_reasonably_sized():
    # Not Rinat's real 142-word list (we don't have it) — but should be a
    # real reconstruction, not a token gesture.
    assert len(STOPWORDS) >= 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_stopwords.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stopwords'`

- [ ] **Step 3: Write minimal implementation**

`stopwords.py`:
```python
STOPWORDS: frozenset[str] = frozenset({
    "ну", "вот", "короче", "типа", "значит", "там", "просто", "это",
    "ещё", "уже", "да", "нет", "ага", "окей", "хорошо", "ладно",
    "слушай", "смотри", "кстати", "блин", "собственно", "как", "бы",
    "для", "то", "есть", "в", "общем", "в общем", "принципе",
})


def stopword_discount(word: str) -> float:
    """Rinat's spec: background speech words are three times cheaper,
    never fully removed from consideration."""
    return 1 / 3 if word in STOPWORDS else 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_stopwords.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add stopwords.py tests/test_stopwords.py
git commit -m "Add stopwords.py: discount-based background word weighting"
```

---

## Task 3: `lemmatize.py`

**Files:**
- Create: `lemmatize.py`
- Test: `tests/test_lemmatize.py`

**Interfaces:**
- Consumes: `pymorphy3.MorphAnalyzer`.
- Produces: `lemmatize(tokens: list[str]) -> list[str]` — used by `match_core.py` in Tasks 5-6.

- [ ] **Step 1: Write the failing test**

`tests/test_lemmatize.py`:
```python
from lemmatize import lemmatize


def test_lemmatize_collapses_grammatical_case():
    # Rinat's documented live bug: "сделок" (speech) never matched
    # "сделка"/"сделки" (title) because his matcher compared raw strings.
    assert lemmatize(["сделок"]) == ["сделка"]
    assert lemmatize(["сделки"]) == ["сделка"]
    assert lemmatize(["сделке"]) == ["сделка"]


def test_lemmatize_collapses_task_word_forms():
    assert lemmatize(["задач"]) == ["задача"]
    assert lemmatize(["задачу"]) == ["задача"]


def test_lemmatize_keeps_distinct_derivational_forms_distinct():
    # "функционал" (noun) and "функциональная" (adjective) are related but
    # different lemmas — lemmatization does not collapse these, only
    # inflectional variants of the *same* word. Documented here so nobody
    # is surprised later when this pair does NOT match on its own.
    assert lemmatize(["функционал"]) == ["функционал"]
    assert lemmatize(["функциональная"]) == ["функциональный"]


def test_lemmatize_preserves_token_order_and_count():
    assert lemmatize(["карточками", "клиентов"]) == ["карточка", "клиент"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_lemmatize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lemmatize'`

- [ ] **Step 3: Write minimal implementation**

`lemmatize.py`:
```python
import pymorphy3

_morph = pymorphy3.MorphAnalyzer()


def lemmatize(tokens: list[str]) -> list[str]:
    return [_morph.parse(token)[0].normal_form for token in tokens]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_lemmatize.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add lemmatize.py tests/test_lemmatize.py
git commit -m "Add lemmatize.py: pymorphy3 wrapper, verified against Rinat's documented stemmer bug"
```

---

## Task 4: `agenda.py`

**Files:**
- Create: `agenda.py`
- Test: `tests/test_agenda.py`

**Interfaces:**
- Consumes: `sprint_snapshot.Task`.
- Produces: `build_agenda(tasks: list[Task], team: list[str]) -> list[Task]`, `pick_alarm(agenda: list[Task], now: datetime | None = None) -> Task | None`, constants `REOPENED_STATUS`, `STALE_DAYS`.

- [ ] **Step 1: Write the failing test**

`tests/test_agenda.py`:
```python
from datetime import datetime, timedelta, timezone

from agenda import REOPENED_STATUS, build_agenda, pick_alarm
from sprint_snapshot import Task


def _task(key, assignee, status, days_ago, now):
    return Task(
        key=key,
        title=f"Заголовок {key}",
        assignee=assignee,
        status=status,
        updated_at=now - timedelta(days=days_ago),
    )


NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def test_build_agenda_filters_by_team():
    tasks = [
        _task("A-1", "Аня", "S", 1, NOW),
        _task("A-2", "Боря", "S", 1, NOW),
    ]
    result = build_agenda(tasks, team=["Аня"])
    assert [t.key for t in result] == ["A-1"]


def test_build_agenda_sorts_by_recency_descending():
    old = _task("A-1", "Аня", "S", 5, NOW)
    new = _task("A-2", "Аня", "S", 1, NOW)
    result = build_agenda([old, new], team=["Аня"])
    assert [t.key for t in result] == ["A-2", "A-1"]


def test_build_agenda_limits_to_six():
    tasks = [_task(f"A-{i}", "Аня", "S", i, NOW) for i in range(9)]
    result = build_agenda(tasks, team=["Аня"])
    assert len(result) == 6
    # keeps the 6 most recently updated
    assert [t.key for t in result] == ["A-0", "A-1", "A-2", "A-3", "A-4", "A-5"]


def test_pick_alarm_prefers_reopened_over_stale():
    older_reopened = _task("A-1", "Аня", REOPENED_STATUS, 5, NOW)
    newer_reopened = _task("A-2", "Аня", REOPENED_STATUS, 1, NOW)
    stale = _task("A-3", "Аня", "В работе", 10, NOW)
    agenda = [older_reopened, newer_reopened, stale]
    assert pick_alarm(agenda, now=NOW) is older_reopened


def test_pick_alarm_falls_back_to_stale_when_no_reopened():
    stale = _task("A-1", "Аня", "В работе", 5, NOW)
    fresh = _task("A-2", "Аня", "В работе", 1, NOW)
    assert pick_alarm([stale, fresh], now=NOW) is stale


def test_pick_alarm_none_when_nothing_qualifies():
    fresh1 = _task("A-1", "Аня", "В работе", 1, NOW)
    fresh2 = _task("A-2", "Аня", "В работе", 2, NOW)
    assert pick_alarm([fresh1, fresh2], now=NOW) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_agenda.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agenda'`

- [ ] **Step 3: Write minimal implementation**

`agenda.py`:
```python
from datetime import datetime, timezone

from sprint_snapshot import Task

REOPENED_STATUS = "Открыто повторно"
STALE_DAYS = 4


def build_agenda(tasks: list[Task], team: list[str]) -> list[Task]:
    filtered = [t for t in tasks if t.assignee in team]
    ordered = sorted(filtered, key=lambda t: t.updated_at, reverse=True)
    return ordered[:6]


def pick_alarm(agenda: list[Task], now: datetime | None = None) -> Task | None:
    """Exactly one task per daily gets flagged, never a per-task boolean —
    confirmed against Rinat's live MagicPath demo: of two "reopened" tasks
    in the same agenda, only the older one was highlighted."""
    now = now or datetime.now(timezone.utc)

    reopened = [t for t in agenda if t.status == REOPENED_STATUS]
    if reopened:
        return min(reopened, key=lambda t: t.updated_at)

    stale = [t for t in agenda if (now - t.updated_at).days >= STALE_DAYS]
    if stale:
        return min(stale, key=lambda t: t.updated_at)

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_agenda.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add agenda.py tests/test_agenda.py
git commit -m "Add agenda.py: team filter + recency sort + single-pick alarm"
```

---

## Task 5: `match_core.py` — scoring building blocks

**Files:**
- Create: `match_core.py`
- Test: `tests/test_match_core.py`

**Interfaces:**
- Consumes: `sprint_snapshot.Task`, `stopwords.stopword_discount`, `lemmatize.lemmatize`.
- Produces: `extract_number_mentions(text: str) -> set[str]`, `compute_idf_weights(agenda: list[Task]) -> dict[str, float]`, `score_task(utterance_lemmas: list[str], task: Task, idf: dict[str, float]) -> tuple[float, int]`, plus internal `_tokenize`/`_key_digits` helpers. Task 6 adds `match()` and `MatchResult` to this same file.

This task covers the pieces `match()` (Task 6) is built from, tested in isolation so failures are easy to localize.

- [ ] **Step 1: Write the failing tests**

`tests/test_match_core.py` (this file grows again in Task 6 — start it here):
```python
from datetime import datetime, timezone

from match_core import compute_idf_weights, extract_number_mentions, score_task
from sprint_snapshot import Task


def _task(key, title):
    return Task(
        key=key,
        title=title,
        assignee="Кто-то",
        status="S",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_extract_number_mentions_finds_digit_sequences():
    # Confirmed live against Rinat's MagicPath demo playback: a spoken
    # number ("двенадцать четыреста двенадцать") already arrives in the
    # transcript as digits ("...с Legacy 412"), not words — Speechmatics
    # normalizes it before the matcher ever sees the text.
    assert extract_number_mentions("возьму следующим 412 в работу") == {"412"}


def test_extract_number_mentions_ignores_single_digits():
    assert extract_number_mentions("у меня 1 вопрос") == set()


def test_extract_number_mentions_can_find_several():
    assert extract_number_mentions("сначала 214 потом 201") == {"214", "201"}


def test_compute_idf_weights_gives_full_weight_to_unique_words():
    agenda = [_task("A-1", "Сделки и клиенты"), _task("A-2", "Отчёты и партнёры")]
    idf = compute_idf_weights(agenda)
    assert idf["сделка"] == 1.0
    assert idf["партнёр"] == 1.0


def test_compute_idf_weights_discounts_shared_words():
    agenda = [
        _task("A-1", "Выгрузка в старую систему"),
        _task("A-2", "Выгрузка в новую систему"),
    ]
    idf = compute_idf_weights(agenda)
    assert idf["выгрузка"] == 0.5
    assert idf["система"] == 0.5
    assert idf["старый"] == 1.0


def test_score_task_counts_overlapping_lemmas():
    task = _task("A-1", "Сделки и клиенты")
    idf = {"сделка": 1.0, "клиент": 1.0}
    score, count = score_task(["сделка", "клиент", "погода"], task, idf)
    assert count == 2
    assert score == 2.0


def test_score_task_discounts_stopword_but_does_not_zero_it():
    task = _task("A-1", "Выгрузка там")
    idf = {"выгрузка": 1.0, "там": 1.0}
    score_with_filler, count_with = score_task(["выгрузка", "там"], task, idf)
    score_without_filler, count_without = score_task(["выгрузка"], task, idf)
    assert count_with == 2
    assert count_without == 1
    assert score_without_filler < score_with_filler < score_without_filler + idf["там"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_match_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'match_core'`

- [ ] **Step 3: Write minimal implementation**

`match_core.py`:
```python
import re

from lemmatize import lemmatize
from sprint_snapshot import Task
from stopwords import stopword_discount

_NUMBER_RE = re.compile(r"\d{2,}")
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _key_digits(key: str) -> str:
    return "".join(ch for ch in key if ch.isdigit())


def extract_number_mentions(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def compute_idf_weights(agenda: list[Task]) -> dict[str, float]:
    doc_count: dict[str, int] = {}
    for task in agenda:
        lemmas = set(lemmatize(_tokenize(task.title)))
        for lemma in lemmas:
            doc_count[lemma] = doc_count.get(lemma, 0) + 1
    return {lemma: 1 / count for lemma, count in doc_count.items()}


def score_task(
    utterance_lemmas: list[str], task: Task, idf: dict[str, float]
) -> tuple[float, int]:
    title_lemmas = set(lemmatize(_tokenize(task.title)))
    overlap = set(utterance_lemmas) & title_lemmas
    score = sum(idf.get(lemma, 0.0) * stopword_discount(lemma) for lemma in overlap)
    return score, len(overlap)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_match_core.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add match_core.py tests/test_match_core.py
git commit -m "Add match_core.py scoring primitives: number extraction, IDF weights, stopword-discounted scoring"
```

---

## Task 6: `match_core.py` — `match()` and the 12 spec test cases

**Files:**
- Modify: `match_core.py`
- Modify: `tests/test_match_core.py`

**Interfaces:**
- Consumes: everything from Task 5, plus `agenda.build_agenda` is NOT used here (tests build their own 6-task agenda straight from the fixture) — `sprint_snapshot.load_sprint`.
- Produces: `MatchResult` dataclass (`task_key: str`, `confidence: float`, `reason: str`), `match(utterance: str, agenda: list[Task]) -> list[MatchResult]`. This is the deliverable of the whole plan — nothing later depends on it within this project.

This task also directly implements every numbered case in the spec's "Тестирование" section (1, 2, 3, 3b, 4, 6, 7, 8, 9, 10 — cases 5, 11, 12 were already covered in Tasks 5 and 4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_match_core.py`:
```python
import pytest

from match_core import MatchResult, match
from sprint_snapshot import load_sprint

AGENDA = load_sprint("fixtures/sprint.json")


def test_case1_explicit_number_matches_by_digits_alone():
    results = match("ладно возьму 214 в работу", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10214"]
    assert results[0].reason == "explicit_number"


def test_case2_exact_title_word_match():
    results = match("коллеги, там синхронизация остатков склада ещё не готова", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10299"]
    assert results[0].reason == "title_words"


def test_case3_regression_word_form_mismatch_from_rinats_bug():
    # Mirrors Rinat's documented live bug (SITE-12160, "сделок" vs
    # "сделка"/"сделки") in our own invented domain: only "клиентов" is an
    # exact string match (1 word, below the 2-word minimum) — lemmatization
    # additionally surfaces "карточка" and "сделка", clearing the bar.
    results = match(
        "разобралась наконец с карточками клиентов, там в сделке была путаница",
        AGENDA,
    )
    assert [r.task_key for r in results] == ["NOVA-10201"]
    assert results[0].reason == "title_words"


def test_case3b_second_regression_found_watching_the_full_demo():
    # Independently found while watching Rinat's demo play to the end
    # (SITE-12170, "функциональная задача для сделок" vs title "Функционал
    # задач для сделок") — same bug class, not in his documented list.
    results = match("готова функциональная заявка для поставщиков", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10230"]
    assert results[0].reason == "title_words"


def test_case4_single_overlapping_word_is_not_enough():
    results = match("короче там ждём поставщиков ещё", AGENDA)
    assert results == []


def test_case6_multiple_tasks_in_one_utterance_newest_first():
    results = match(
        "разобралась наконец с карточками клиентов, там в сделке была "
        "путаница, и ещё возьму 214",
        AGENDA,
    )
    assert [r.task_key for r in results] == ["NOVA-10214", "NOVA-10201"]
    assert results[0].reason == "explicit_number"
    assert results[1].reason == "title_words"


def test_case7_pure_filler_utterance_matches_nothing():
    results = match("ну короче вот как бы", AGENDA)
    assert results == []


def test_case8_ambiguous_tie_between_two_similar_tasks():
    results = match("надо доделать выгрузку контактов в систему", AGENDA)
    assert results == []


def test_case9_unrelated_smalltalk_matches_nothing():
    results = match("пойдём после созвона поедим, кто что хочет", AGENDA)
    assert results == []


def test_case10_empty_agenda_raises_instead_of_silently_matching_nothing():
    with pytest.raises(ValueError):
        match("что угодно", [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_match_core.py -v`
Expected: FAIL — `ImportError: cannot import name 'MatchResult' from 'match_core'` (and/or `match`)

- [ ] **Step 3: Write minimal implementation**

Append to `match_core.py`:
```python
from dataclasses import dataclass

MIN_OVERLAP_WORDS = 2
MIN_SCORE = 0.5
REQUIRED_MARGIN = 0.3


@dataclass(frozen=True)
class MatchResult:
    task_key: str
    confidence: float
    reason: str


def match(utterance: str, agenda: list[Task]) -> list[MatchResult]:
    if not agenda:
        raise ValueError("agenda must not be empty")

    idf = compute_idf_weights(agenda)
    utterance_lemmas = lemmatize(_tokenize(utterance))
    mentioned_numbers = extract_number_mentions(utterance)

    results: list[MatchResult] = []
    matched_keys: set[str] = set()

    for task in agenda:
        key_digits = _key_digits(task.key)
        for number in mentioned_numbers:
            is_full_match = number == key_digits
            is_suffix_match = len(number) >= 3 and key_digits.endswith(number)
            if is_full_match or is_suffix_match:
                results.append(MatchResult(task.key, 1.0, "explicit_number"))
                matched_keys.add(task.key)
                break

    remaining = [t for t in agenda if t.key not in matched_keys]
    scored: list[tuple[Task, float]] = []
    for task in remaining:
        score, overlap_count = score_task(utterance_lemmas, task, idf)
        if overlap_count >= MIN_OVERLAP_WORDS and score > MIN_SCORE:
            scored.append((task, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    if scored:
        top_task, top_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
        if top_score - runner_up_score >= REQUIRED_MARGIN:
            results.append(MatchResult(top_task.key, top_score, "title_words"))

    task_by_key = {t.key: t for t in agenda}
    results.sort(key=lambda r: task_by_key[r.task_key].updated_at, reverse=True)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_match_core.py -v`
Expected: 17 passed (7 from Task 5 + 10 new)

- [ ] **Step 5: Commit**

```bash
git add match_core.py tests/test_match_core.py
git commit -m "Add match(): number + word channels, silence-when-unsure gate, all 12 spec test cases green"
```

---

## Task 7: README + full verification pass

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing new — this task only documents and verifies what Tasks 1-6 built.

- [ ] **Step 1: Write `README.md`**

```markdown
# daily_standup_matcher

Reconstruction of the "ядро без интерфейса" (core, no UI) slice from Rinat's
daily-standup-copilot techspec — recognizes which sprint task is being
discussed from a finalized speech utterance, or stays silent when unsure.

Built without access to Rinat's real code, real Fireflies transcripts, or a
real Jira snapshot — see `docs/superpowers/specs/2026-08-29-daily-standup-matcher-design.md`
for what's a faithful reconstruction vs. an explicitly-flagged assumption.

## Setup

\`\`\`bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
\`\`\`

## Run tests

\`\`\`bash
venv/bin/python3 -m pytest -v
\`\`\`

## What's here

- `sprint_snapshot.py` — `Task` model + JSON fixture loader (no live Jira).
- `agenda.py` — filter by team, sort by recency, limit to 6, pick the single
  alarm task (reopened beats ≥4-days-stale).
- `stopwords.py` — background/filler words get a ×⅓ weight discount, never
  full removal.
- `lemmatize.py` — `pymorphy3` wrapper (not `pymorphy2` — doesn't install on
  Python 3.14 here).
- `match_core.py` — the matcher: explicit spoken numbers (already digits by
  the time STT hands them over) short-circuit to a match; otherwise IDF-
  weighted lemma overlap with a ≥2-word minimum and a score-margin gate
  against the runner-up candidate. Returns a list, since one utterance can
  mention more than one task.
- `fixtures/sprint.json` — 6 invented tasks (no real Tranio data) covering
  every test case in the spec, including two live-bug regression cases.

## Known gaps (see spec for full list)

Not implemented in this slice: any UI, `live_copilot_poc` integration, real
Jira access, speaker diarization, the LLM layer, or delay measurement on a
real daily. The stopword list is a reconstruction (Rinat's real 142-word
list isn't available); the alarm/sort criteria and the number-format
behavior *are* the real spec's, confirmed against the primary source and a
live demo playback.
```

- [ ] **Step 2: Run the full test suite**

Run: `venv/bin/python3 -m pytest -v`
Expected: all tests across all 6 test files pass (33 total: 2 + 3 + 4 + 6 + 7 + 10 from Tasks 1-6 — re-count after Task 6's actual run and adjust this number if it drifted during implementation).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add README: setup, test instructions, what this reconstruction covers and doesn't"
```

---

## Plan Self-Review Notes

- **Spec coverage:** every component in the spec (`sprint_snapshot.py`, `agenda.py`, `stopwords.py`, `lemmatize.py`, `match_core.py`) has its own task; all 12 numbered test cases from the spec's "Тестирование" section are covered (1-4, 6-10 in Task 6; 5 in Task 5; 11-12 in Task 4).
- **Dependency correction carried through:** `pymorphy2` → `pymorphy3` swap (verified during spec research) is reflected in `requirements.txt`, `lemmatize.py`, and the README — not just the spec.
- **No placeholders:** every step has runnable code, not descriptions of code.
- **Type/name consistency checked:** `Task`, `MatchResult`, `build_agenda`, `pick_alarm`, `match`, `score_task`, `compute_idf_weights`, `extract_number_mentions` are spelled identically everywhere they're used across tasks.
