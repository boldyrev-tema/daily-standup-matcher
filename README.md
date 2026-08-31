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
- `hints.py` — real LLM call (OpenRouter, `nvidia/nemotron-3-super-120b-a12b:free`,
  reasoning disabled — see "Why OpenRouter, not Groq" below) for the "Сказали"/"Спроси"
  layer, strict JSON contract, degrades to empty on timeout/error (never crashes the replay).
- `credentials.py` — reads `KEY=value` lines from a `~/.credentials/*.env`
  file (same tiny pattern as this author's `meeting_copilot` project).
- `replay_driver.py` — turns an invented sample transcript into a finished
  `Meeting` (used by the integration test; no pacing, no LLM calls).
- `run_polosa_replay.py` — the real thing: opens a pywebview "Полоса" window
  and plays `fixtures/sample_daily_transcript.json` with realistic pauses and
  real LLM calls. Needs `~/.credentials/openrouter_api_key.env` (`OPENROUTER_API_KEY=...`).
- `polosa.html` — the overlay page itself, techspec style tokens + apple-design
  restrained motion.

- `second_screen.html` + `run_second_screen.py` — the "второй экран" full three-
  column view (Слышу / Записал / Подсказываю), same pywebview approach and real
  LLM call as "Полоса", but rendering the complete `Meeting` state: full
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

## Why OpenRouter, not Groq

Rinat cloned this repo and ran it against his own real sprint snapshot and a
full 39-minute Fireflies transcript of an actual daily (not the 6-line demo
fixture) — see `docs/superpowers/specs/` project memory for the full writeup.
Groq's free tier limit is 8000 tokens/minute *regardless of model size*, and
one hint call is ~2300 tokens, so it 429s after the third recognition inside
any given minute — fatal on a real call with many recognitions close together.

OpenRouter's free tier is rate-limited by request count (50/day on a fresh
account, 20 RPM), not tokens, which doesn't hit the same wall. Tested 5 free
models empirically against this project's real prompt shape:
`google/gemma-4-31b-it:free` and `z-ai/glm-5.2:free` were consistently
upstream-429'd (shared free pool saturated, not our own quota) both times
tried. `nvidia/nemotron-3.5-lightning:free` and the default (reasoning-on)
`nvidia/nemotron-3-super-120b-a12b:free` both defaulted into a hidden
reasoning pass — 49s and 195s respectively, with the smaller Lightning model
also producing a character-level typo in its output. Passing
`"reasoning": {"enabled": false}` on `nemotron-3-super` cut that to 1.8-3.3s
with no quality loss, so that's what's wired into `hints.py`.
`minimax/minimax-m3:free` was comparably fast without needing that flag, but
its response body occasionally interleaves keep-alive whitespace pings that
broke naive JSON parsing in ad-hoc testing — kept as a fallback candidate,
not the default, until that's investigated further.

## Known gaps in this iteration

Not implemented: live microphone / Speechmatics STT (still reads an invented
transcript file), real Jira snapshot (still `fixtures/sprint.json`), speaker
diarization, the Начать/Сначала button's click handler on "Полоса" and
"Колонка" (the replay auto-starts instead — see
`docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why). The PRD
gate (3-4 real live dailies with hand-counted recognition/latency) is still
unmet — only demo-transcript replays, see `docs/superpowers/specs/` project
memory for details.
