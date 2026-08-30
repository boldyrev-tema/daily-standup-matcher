# daily_standup_matcher

Reconstruction of the "ядро без интерфейса" (core, no UI) slice from Rinat's
daily-standup-copilot techspec — recognizes which sprint task is being
discussed from a finalized speech utterance, or stays silent when unsure.

Built without access to Rinat's real code, real Fireflies transcripts, or a
real Jira snapshot — see `docs/superpowers/specs/2026-08-29-daily-standup-matcher-design.md`
for what's a faithful reconstruction vs. an explicitly-flagged assumption.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Run tests

```bash
venv/bin/python3 -m pytest -v
```

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

- `second_screen.html` + `run_second_screen.py` — the "второй экран" full three-
  column view (Слышу / Записал / Подсказываю), same pywebview approach and real
  Groq call as "Полоса", but rendering the complete `Meeting` state: full
  scrolling transcript with underlined `hit_words` and "→ KEY" tags, the full
  agenda split by phase with the alarm row in red, all 5 Jira facts, and the
  progressive "Сказали" reveal that "Полоса" computed but never displayed.

- `column.html` + `run_column.py` — the "Колонка" narrow vertical placement
  (header → Подсказываю → Записал → Слышу, top to bottom), meant to sit as a
  400×880 overlay over the call window (same size as this author's
  `live_copilot_poc` suflyor). Reuses `run_second_screen.py`'s state/matching
  code directly (imports `_state_json`/`_primary_match`/`TEAM`, no duplicated
  logic) — the only differences are the vertical HTML template, "Слышу" capped
  to the last 3 lines instead of a full scroll, and a phase-driven header
  ("Сегодня, HH:MM" / "N мин" + live dot / "Закончился · обсудили N из M").
  See `docs/superpowers/specs/2026-08-30-column-design.md`.

## Known gaps in this iteration

Not implemented: live microphone / Speechmatics STT (still reads an invented
transcript file), real Jira snapshot (still `fixtures/sprint.json`), speaker
diarization, the Начать/Сначала button's click handler on "Полоса" and
"Колонка" (the replay auto-starts instead — see
`docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why). The PRD
gate (3-4 real live dailies with hand-counted recognition/latency) is still
unmet — only demo-transcript replays, see `docs/superpowers/specs/` project
memory for details.
