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

## Known gaps (see spec for full list)

Not implemented in this slice: any UI, `live_copilot_poc` integration, real
Jira access, speaker diarization, the LLM layer, or delay measurement on a
real daily. The stopword list is a reconstruction (Rinat's real 142-word
list isn't available); the alarm/sort criteria and the number-format
behavior *are* the real spec's, confirmed against the primary source and a
live demo playback.
