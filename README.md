# daily_standup_matcher

Reconstruction of the "ядро без интерфейса" (core, no UI) slice from a
daily-standup-copilot techspec — recognizes which sprint task is being
discussed from a finalized speech utterance, or stays silent when unsure.

Built without access to the original real code or real Fireflies
transcripts — see `docs/superpowers/specs/2026-08-29-daily-standup-matcher-design.md`
for what's a faithful reconstruction vs. an explicitly-flagged assumption.

## Two ways to run it

Pick whichever fits what you're doing right now — both run the exact same
matching/hints code underneath, the app is just a different wrapper around
the same scripts, not a separate implementation.

- **Script — for trying it out or debugging.** Double-click one of the
  `.command` files in the repo root (e.g. `Второй экран (терминал).command`),
  or run `venv/bin/python3 run_second_screen.py` directly. Nothing to
  install beyond "Setup" below. Opens a visible Terminal window, so any
  error prints right there — the way to go the first time, or whenever
  something looks wrong and you want to see what it's actually doing.
- **App — for everyday use during a real daily.** A packaged `.app` (see
  "Running as an app" below), no terminal window, nothing to look at or
  accidentally close. It does **not** show up in the Dock or Cmd+Tab —
  instead it lives as a small icon in the menu bar at the top of the
  screen, which toggles the window and lets you switch layout (unified
  build) or quit. Build it once with `py2app` (see below), then just open
  it like any other app from then on.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python3 patch_pywebview.py
```

The third step patches a real bug in the installed pywebview package itself
(its internal HTTP server crashes — `TypeError: asset() missing 1 required
positional argument: 'file'` — whenever anything requests the server's bare
root URL instead of a specific filename; see `patch_pywebview.py` for the
full story). Safe to re-run after any `pip install --upgrade`.

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
  mention more than one task. `ambiguous_candidates()`/`resolve_pending()`
  give a caller a second chance at a margin-blocked tie using the next
  utterance as extra context, restricted to the tied set so it can only pick
  a winner among real contenders, never surface a new one — wired into every
  replay loop (`_apply_pending()` in `run_second_screen.py`, reused by
  `run_column.py`/`run_polosa_replay.py`/`replay_driver.py`) so a first line
  that's genuinely ambiguous on its own gets backfilled once the next line
  (independently, or merged with the first) disambiguates it. Found live on a
  real daily, 2 сен: a real tie between two "сделки" tasks resolved on the
  very next line but the first line stayed permanently unlabeled — this
  closes that gap.
- `fixtures/sprint.json` — 6 invented tasks (no real company data) covering
  every test case in the spec, including two live-bug regression cases.
- `jira_client.py` + `sprint_snapshot.load_current_sprint()` — optional live
  Jira fetch instead of the fixture, see "Live Jira snapshot" below.
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
  `--live` swaps the file-transcript replay for a real Speechmatics
  microphone stream — see "Live microphone" below.

- `live_audio.py` — mic (+ optional system/call audio) -> Speechmatics
  streaming transcription, one callback per finalized utterance. See "Live
  microphone" below.

- `column.html` + `run_column.py` — the "Колонка" narrow vertical placement
  (header → Подсказываю → Записал → Слышу, top to bottom), meant to sit as a
  400×880 overlay over the call window (same size as this author's
  `live_copilot_poc` suflyor). Reuses `run_second_screen.py`'s state/matching
  code directly (imports `_state_json`/`_primary_match`/`TEAM`, no duplicated
  logic) — the only differences are the vertical HTML template, "Слышу" capped
  to the last 3 lines instead of a full scroll, and a phase-driven header
  ("Сегодня, HH:MM" / "N мин" + live dot / "Закончился · обсудили N из M").
  See `docs/superpowers/specs/2026-08-30-column-design.md`.

- `recap.py` — builds/saves/loads the post-daily recap, see "Post-daily
  recap" below.
- `recap.html` — the small standalone window that shows a saved recap.
- `menubar.py` — menu-bar (macOS status bar) icon, replaces Dock-based
  minimize now that the app is hidden from the Dock. `start_tray()` (plain
  Показать/Скрыть + Выход, used by the three standalone `run_*.py`) and
  `start_layout_tray()` (adds a layout-picker submenu, used by `run_app.py`
  below) both run everything on the main thread — see the module docstring
  for the real crash a background-thread version hit.
- `patch_pywebview.py` — idempotent post-install patch for a real pywebview
  6.2.1 bug (its internal HTTP server crashes on a bare `/` request). Run
  once after `pip install -r requirements.txt`.
- `run_app.py` + `setup_app.py` — the unified app: one process, one window,
  live choice of layout (Полоса/Второй экран/Колонка) from the menu-bar
  icon instead of three separate apps. See "Running as an app" below.

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

## Live microphone (`run_second_screen.py --live`)

`live_audio.py` streams microphone audio (+ system/call audio, if enabled —
see below) to Speechmatics and calls back once per finalized utterance
(a real pause-based boundary, not per-word). `run_second_screen.py`'s
`_process_turn()` — the same function the file-replay path uses — takes it
from there, so live and replay can never drift into different matching
behavior. Needs `~/.credentials/speechmatics_api_key.env`
(`SPEECHMATICS_API_KEY=...`) in addition to the OpenRouter key. Adapted from
a proven PoC (this author's own `live_copilot_poc` project, tested live
21 авг) — only the audio-capture/streaming-STT plumbing, not its LLM/vision
layer.

Device selection probes the OS default input first and falls back to
another input device if it's silent (`pick_working_input_device()`) —
found live, 2 сен: the OS default was a Bluetooth headset stuck outside its
mic-capable mode, returning exact-zero samples with no error; the built-in
mic worked fine. Real hardware self-noise is never bit-exact zero, so a
near-zero probe reliably tells "not delivering audio" apart from "device is
just quiet."

Speechmatics gets a custom vocabulary (`additional_vocab`) built from the
current agenda's task titles (`live_audio.build_additional_vocab()`, words
>3 letters, stopwords dropped) — nudges recognition toward the actual
product names/jargon this sprint uses instead of a generic model's guess.

System audio (the other side of the call, labeled "Собеседник") needs the
`SystemAudioDump` binary from the `cheating-daddy` project — **not bundled
here** (this repo is public; that binary's license isn't ours to
redistribute). Point the `SYSTEM_AUDIO_DUMP_PATH` env var at a local copy to
enable it; without it, only the microphone channel ("Ты") runs.

`--live` is opt-in — `python3 run_second_screen.py` (no flag) still runs the
deterministic file replay, unchanged, for demos/tests.

## Live Jira snapshot (`jira_client.py` + `sprint_snapshot.load_current_sprint`)

Real feedback from a live call: the matcher only recognizes tasks against
a pre-loaded agenda, and until now that agenda was a hand-edited local
file — someone had to build a fresh `fixtures/sprint.json` before every
single call, or the matcher had nothing real to recognize speech against.
This section is what actually removes that step: once it's set up, every
launch pulls the current sprint straight from Jira on its own — no more
preparing a file by hand before each call.

**1. Get a Jira API token** (one-time, not per call): go to
https://id.atlassian.com/manage-profile/security/api-tokens while logged
into the Jira account, create a token, copy it — you won't be able to see
it again after leaving the page.

**2. Create `~/.credentials/jira_credentials.env`:**

```
JIRA_BASE_URL=https://your-site.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=<the token from step 1>
JIRA_JQL=project = X AND sprint in openSprints() ORDER BY updated DESC
JIRA_TEAM=Имя Первого, Имя Второго
```

`JIRA_BASE_URL` is the Jira site address (shows in the browser URL bar
while in Jira). `JIRA_JQL` picks which issues count as "this sprint" —
`JIRA_PROJECT_KEY=X` works instead of writing JQL by hand, a default query
gets built from it. `JIRA_TEAM` is the exact display names (as they appear
in Jira) of everyone whose tasks should show up on the agenda — without it
set, the live fetch is treated as failed (see below), since real Jira
names would never match anything otherwise.

**3. That's it — nothing else to run.** With this file present, every
`run_*.py` fetches the live sprint at launch instead of reading the local
fixture and feeds it into the exact same recognition logic described
above (lemma/number matching against task titles) — the matcher doesn't
change at all, it just gets real tasks to compare speech against instead
of invented ones. Read-only, same as everywhere else in this project —
only a search call is ever made, nothing here can write back to Jira.

No credentials file, or the fetch fails for any reason (bad JQL, expired
token, network, `JIRA_TEAM` missing) → falls back to `fixtures/sprint.json`
+ the module's hardcoded placeholder team, same as before, with a stderr
note in the failure case. Nobody without Jira set up (including this
repo's own tests/demo) is affected.

**Unverified against a real Jira instance** — no credentials were available
to test with, so this is built and tested against mocked responses only
(see `docs/superpowers/specs/2026-09-03-live-jira-snapshot-design.md`).
Needs someone to actually set the credentials file and run it once against
a real sprint before this is more than "should work."

## Post-daily recap (`recap.py` + `recap.html`)

On closing a `--live` window, the app builds a short recap of what was
discussed per task and saves it to `recaps/*.json` (gitignored — real
transcript content, this repo is public). On the next `--live` launch, if a
saved recap exists, a small separate window opens next to the main one
showing it.

The matcher only tags the ONE utterance that actually triggered task
recognition (`Line.task`) — the rest of a task's discussion (clarifications,
"when can you merge that", "tonight") never gets tagged, since `match()`
only looks at each utterance's own text. `build_recap()` groups
`meeting.lines` by time segment between consecutive recognition points
instead of by that narrow tag, so the recap covers the actual conversation,
not just the trigger line — then calls the same `hints.get_hints()` used for
the live "Сказали" hints, with a new `lookback_seconds=None` mode that skips
its normal 90-second window (a full-task summary needs everything, not just
the last 90s of it).

Generation runs in a non-daemon background thread on window close: the
window closes immediately, but the process itself stays alive a few extra
seconds to finish the LLM calls and write the file — see
`docs/superpowers/specs/2026-09-02-daily-recap-design.md`.

## Running as an app (no terminal)

Two independent ways to launch, both still supported:

- **Terminal** — `venv/bin/python3 run_second_screen.py` (or `run_column.py`
  / `run_polosa_replay.py`), same as always. `.command` files in the repo
  root do the same thing double-clickable from Finder, with a visible
  Terminal window for debugging.
- **App — `dist/Дейлик.app`, build this one.** One app, no terminal, a
  menu-bar icon (no Dock icon) with a submenu to switch live between the
  three layouts without restarting the meeting — the agenda, matcher
  state, and (in `--live` mode) the Speechmatics session keep running
  unchanged; only the window's content and size change.

`setup_column.py` / `setup_second_screen.py` / `setup_polosa_replay.py`
still exist and build a single-layout `.app` each the same way, if you ever
specifically want just one layout with no switcher — but `Дейлик.app`
covers everything they do plus live switching, so there's no reason to
build all four; pick `setup_app.py` unless you know you want one of the
others.

```bash
venv/bin/python3 setup_app.py py2app
```

`dist/`, `build/`, and `logs/` are gitignored — nothing here is committed,
only the `setup_*.py` scripts that produce them. Two native dependencies
needed forcing into `packages` in every `setup_*.py` (py2app's static
import analysis misses their non-code files otherwise): `pymorphy3_dicts_ru`
(dictionary data, "Can't find a dictionary for language 'ru'" without it)
and `_sounddevice_data` (the actual PortAudio `.dylib` — `sounddevice`
itself is a flat module, not a package, so it alone doesn't pull the native
library in). The Dock icon staying hidden needed more than the plist's
`LSUIElement` — pywebview's own Cocoa backend forces a Regular activation
policy the first time it creates a window, so `menubar.hide_from_dock()`
reasserts Accessory policy on a burst of delayed callbacks instead of a
single call, confirmed deterministic across repeated runs of the same
build.

## Known gaps in this iteration

Not yet done: live Jira fetch is built (see "Live Jira snapshot" above) but
**unverified against a real instance** — no credentials exist on this
machine to actually run it once. Speaker diarization on the live path (both
channels are pre-labeled "Ты"/"Собеседник" by which audio device they came
from, not detected), the Начать/Сначала button's
click handler on "Полоса" and "Колонка" (the replay auto-starts instead —
see `docs/superpowers/specs/2026-08-29-polosa-replay-design.md` for why).
The PRD gate (3-4 real live dailies with hand-counted recognition/latency)
is still unmet — replays of a real transcript got close twice, but that's
not the same as a live mic on a real call; see `docs/superpowers/specs/`
project memory for details. `--live` inside a `py2app` bundle has only been
smoke-tested (session stays connected ~20s, no reconnect/failure, correct
device-fallback logging) — not run through an actual full daily with a real
voice yet.
