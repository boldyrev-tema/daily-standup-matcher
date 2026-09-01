# daily_standup_matcher

Reconstruction of the "ядро без интерфейса" (core, no UI) slice from a
daily-standup-copilot techspec — recognizes which sprint task is being
discussed from a finalized speech utterance, or stays silent when unsure.

Built without access to the original real code, real Fireflies transcripts,
or a real Jira snapshot — see `docs/superpowers/specs/2026-08-29-daily-standup-matcher-design.md`
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
  Optional `status_category` field expects Jira's `statusCategory.key`
  (`"new"` / `"indeterminate"` / `"done"`) — stable across projects and
  locales, unlike status display names.
- `agenda.py` — filter by team, drop closed/done tasks, sort by recency,
  limit to 6, pick the single alarm task (reopened beats ≥4-days-stale).
  Drops a task by `status_category == "done"` when present (real Jira
  workflows use "done"-category status names we don't otherwise know about,
  e.g. "Reviewed"); falls back to matching `status` against `CLOSED_STATUSES`
  only when a snapshot doesn't carry `status_category`.
- `stopwords.py` — background/filler words get a ×⅓ weight discount, never
  full removal — but don't count toward the minimum-overlap-words gate in
  `match_core.py` (a stopword still nudges the score, it just can't satisfy
  "two real words" on its own).
- `lemmatize.py` — `pymorphy3` wrapper (not `pymorphy2` — doesn't install on
  Python 3.14 here).
- `translit.py` — English-to-Cyrillic transliteration for anglicism/mixed-
  script matching, see "Anglicisms and mixed-script speech" below.
- `match_core.py` — the matcher: explicit spoken numbers (already digits by
  the time STT hands them over) short-circuit to a match; otherwise IDF-
  weighted lemma overlap (plus a fuzzy Cyrillic-phonetic alias for Latin
  title words) with a ≥2-significant-word minimum and a score-margin gate
  against the runner-up candidate. Returns a list, since one utterance can
  mention more than one task.
- `fixtures/sprint.json` — 6 invented tasks (no real company data) covering
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

A live run against a real sprint snapshot and a full 39-minute Fireflies
transcript of an actual daily (not the 6-line demo fixture) surfaced this —
see `docs/superpowers/specs/` project memory for the full writeup.
Groq's free tier limit is 8000 tokens/minute *regardless of model size*, and
one hint call is ~2300 tokens, so it 429s after the third recognition inside
any given minute — fatal on a real call with many recognitions close together.

OpenRouter's free tier is rate-limited by request count (50/day on a fresh
account, 20 RPM, same for every free model — checked via `GET /api/v1/key`,
this isn't a per-model knob), not tokens, so it doesn't hit the same wall.

Tested 8 free models empirically against this project's real prompt shape,
across multiple batches on the same day. `google/gemma-4-31b-it:free` and
`z-ai/glm-5.2:free` were consistently upstream-429'd (shared free pool
saturated, not our own quota). `nvidia/nemotron-3.5-lightning:free` and
`minimax/minimax-m2.7:free` defaulted into a hidden reasoning pass or were
just slow/unreliable (15-195s, sometimes an empty response body).

**The free tier's real failure mode turned out to be provider volatility, not
model choice.** `nvidia/nemotron-3-super-120b-a12b:free` (reasoning disabled)
scored 9/10 in one batch and 3/8 an hour later in a different batch, with a
different error each time (`Upstream idle timeout exceeded` vs `Service
temporarily overloaded`) — `GET /api/v1/models/.../endpoints` confirms it has
exactly one upstream provider (Nvidia), no OpenRouter-side failover. So
`hints.py` doesn't pick one "best" model — it walks a `MODEL_CHAIN` of three,
falling through on failure instead of retrying the same one:
`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (reasoning off, 8/8 and
8/8 in two batches, ~1.8s avg — fastest and most reliable so far) first, then
`minimax/minimax-m3:free` (8/8 and 8/8, ~2-4s typical, one 37s outlier — also
a genuinely different upstream, GMICloud, so it doesn't share Nvidia's bad
days) as a real fallback, then `nemotron-3-super` last. Live end-to-end test
of the full chain: 10/12 non-empty. Not perfect — two calls in that run
exhausted all three — but a clear improvement over any single model, and
`get_hints()` degrades to an empty hint rather than crashing either way.

## Anglicisms and mixed-script speech

Established Russian IT loanwords spoken/written in Cyrillic ("задеплоили",
"заревьюил", "смержил") already match fine — `pymorphy3`'s dictionary knows
these as real loanwords. Two more cases, checked empirically: a Latin-script
title word spoken as literal Latin in the transcript matches trivially
(exact string equality). A Latin-script title word (e.g. a product name like
"Go Market") spoken and transcribed as Cyrillic phonetics ("гоу маркет") is
handled by `translit.py` (see `match_core._latin_alias_overlap`) — fuzzy,
not exact, since the transliterator itself is only ~65% exact against real
loanword spellings on its own. `translit.py` also carries `KNOWN_IT_TERMS`,
a curated base of common IT/PM anglicism spellings checked before the
letter rules — pushes that to 14/14 exact on the calibration set (see
`tests/test_translit.py`), extend it as more terms come up in practice.
Known limitation: components <=3 letters ("go") require an exact
transliteration match to stay safe (a looser threshold can't tell "гоу"
apart from the unrelated filler word "ого" — both score 0.80 similarity
against "го") — so a short component won't alias-match on its own, only
combined with another real overlapping word in the same utterance.

Validated against real (not invented) mixed-language speech: pulled actual
YouTube auto-captions for a public Russian podcast episode about code
review via `yt-dlp` — the same term came out three different ways in the
same recording (clean Latin, mixed-script, and clean Cyrillic), plus one
case where the STT mis-heard it as an unrelated real word entirely. The
matcher gets the clean-Cyrillic case right and correctly stays silent on
the unrelated-word misheard case — see
`test_case13b`/`test_case13c` in `tests/test_match_core.py`.

## Known gaps in this iteration

Not implemented: live microphone / Speechmatics STT (still reads an invented
transcript file), real Jira snapshot (still `fixtures/sprint.json`), speaker
diarization, the Начать/Сначала button's click handler on "Полоса" and
"Колонка" (the replay auto-starts instead — see
`docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why). The PRD
gate (3-4 real live dailies with hand-counted recognition/latency) is still
unmet — only demo-transcript replays, see `docs/superpowers/specs/` project
memory for details.
