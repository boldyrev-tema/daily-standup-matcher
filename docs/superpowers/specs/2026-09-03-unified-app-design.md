# Unified app: one process, live layout switching

## Decision (user, 3 сен)

The three layouts (Полоса / Второй экран / Колонка) stay as three distinct,
non-duplicating placements — not merged into one visual design. What changes
is packaging: today each is its own `run_*.py` entry point and its own
`.app`. The goal is ONE running app where the layout is a live choice inside
the product, not three separate app icons.

Chosen mechanism (user picked over a picker-screen-and-relaunch alternative,
and over an "all three windows at once" alternative): **one pywebview
window, live switch**. The meeting — agenda, matcher state, live Speechmatics
session or file replay — lives entirely on the Python side and never
restarts on a layout switch. Switching only changes what's loaded into the
one window: swap the HTML file, resize the window to that layout's target
size, then push the current state once so the new page renders it
immediately.

This works because all three HTML templates already consume state the same
way — a `renderMeeting(state)` JS function driven entirely by
`window.evaluate_js` pushes from Python, never computing anything from a
prior DOM state. Confirmed by reading each file's `renderMeeting`:
`column.html`/`second_screen.html` read the same rich shape (`agenda.done`/
`remaining`, `lines[]`, `current_task.facts/said/ask`) — `run_column.py`
already imports `run_second_screen._state_json` verbatim, no divergence.
`polosa.html` reads a reduced shape (`remaining_count`, `last_line`,
`current_task.first_fact`) via its own `_state_json` in
`run_polosa_replay.py`. Two existing builders, not one — chosen not to
unify them into a single schema (bigger, riskier change, no clear
benefit) and instead have the unified app pick the right builder by which
layout is currently on screen.

## What stays untouched

Per the user's explicit scope note from 3 сен ("через терминал — остаётся
как есть"): `run_column.py`, `run_second_screen.py`, `run_polosa_replay.py`
and their three `.command`/`.app` launchers keep working exactly as today,
standalone, one layout per process. The unified app is a new, additional
entry point (`run_app.py`), not a replacement.

The only change to an existing file: `run_second_screen.py`'s
`_process_turn` gets an optional trailing `push=None` parameter. When
omitted (every existing caller — `run_second_screen.py` itself,
`run_column.py`), behavior is byte-for-byte the same (default `push` is a
closure doing exactly what the inline `window.evaluate_js(...)` call did
before). `run_app.py` is the only caller that passes a custom `push` — one
that reads which layout is currently active and calls the matching state
builder.

## New pieces

- `run_app.py` — the unified entry point. Owns the layout registry (key →
  label/html/width/height), the single `webview` window, the "which layout
  is currently loaded" state, `switch_layout(key)`, and replay/live driver
  loops adapted from `run_second_screen.py`'s (same phases, same
  `_process_turn` call, different `push`).
- `menubar.start_layout_tray(...)` — new function alongside the existing
  `start_tray` (which the three standalone scripts keep using unchanged).
  One tray icon, a submenu of the three layouts (radio-style, checkmark on
  the active one) above the existing Показать/Скрыть + Выход items. Same
  proven safety rules as `start_tray`: everything on the main thread,
  `run_detached`, quit deferred through the same `threading.Timer` pattern.
- `setup_app.py` — py2app build script for the unified app, same recipe as
  `setup_column.py` (same two forced `packages` entries), `DATA_FILES`
  covering all three HTML templates + `recap.html` + fixtures (the unified
  app can end up on any layout, and `--live` pulls in the recap window like
  `run_second_screen.py` already does).

## Switching mechanics (why it's safe against the deadlocks already found)

Established rule in this project (2 сен, py-spy-confirmed): any AppKit call
that can end or block the run loop must never happen synchronously on a
non-main thread, and must never block waiting on something the run loop
itself has to deliver. Tray clicks run on the main thread already (see
`menubar.py`'s docstring), so `window.resize()`/`window.load_url()` can be
called directly from the click handler — same as `toggle`/`quit_app` in
`start_tray` already do for `window.hide()`/`window.show()`.

What CANNOT happen synchronously in that handler: waiting for the new
page's `loaded` event before pushing state. That event only fires once the
run loop itself processes the navigation — blocking on it inside a run-loop
callback is the exact shape of the deadlocks already found twice in this
project. So: the click handler clears a shared `threading.Event`, resizes,
calls `load_url`, and returns immediately; a separate daemon thread waits on
the event (timeout 10s, same as every other `loaded_event.wait` in this
codebase) and does the actual state push once it fires.

The background meeting-processing thread (replay loop or live `on_turn`
callback) keeps running the whole time, mutating the same `meeting`/`agenda`
objects — a layout switch never touches them, only which window/shape they
get rendered into next.

## Not changing in this pass

- No live-audio start from inside the switcher — `--live` vs. demo replay is
  still chosen at process launch (`sys.argv`), same as
  `run_second_screen.py` today.
- No per-layout tray icon glyph — one static icon; the submenu checkmark is
  the "which layout is active" signal, not the icon.
