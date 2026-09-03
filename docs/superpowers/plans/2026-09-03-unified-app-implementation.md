# Unified app implementation plan

Spec: `docs/superpowers/specs/2026-09-03-unified-app-design.md`

## Tasks

1. **`_process_turn` gets an optional `push` param.** `run_second_screen.py`:
   add `push=None` as a trailing parameter; when `None`, default to a
   closure equal to today's inline `window.evaluate_js(f"renderMeeting(...)")`
   call. Replace the three inline call sites inside the function body with
   `push()`. No behavior change for existing callers — locked down by
   `tests/test_process_turn.py` already passing unchanged, plus one new test
   asserting a custom `push` is used instead of the default when given.

2. **`run_app.py`: layout registry + single-window switch.** New module.
   `LAYOUTS` dict (key → label/html/width/height), `LAYOUT_ORDER` tuple.
   `_push_state(layout_key, window, meeting, agenda, alarm_task)` — picks
   `run_second_screen._state_json` or `run_polosa_replay._state_json`
   depending on `layout_key` and evaluates it. Pure enough to unit-test
   directly with a fake window (assert which builder's shape got pushed for
   each key) without touching pywebview/pystray.

3. **Replay + live driver loops in `run_app.py`.** Adapted from
   `run_second_screen.py`'s `_run_replay`/`_run_live`: same phase handling
   (`before` → 2s → `live` → `after`), same `LiveAudioSession` wiring for
   `--live`, same recap save-on-close — but `_process_turn` is called with
   `push=lambda: _push_state(state_ref["layout"], window, meeting, agenda, alarm_task)`
   instead of the default, so every push respects whichever layout is
   currently on screen.

4. **`switch_layout(key)` + `menubar.start_layout_tray`.** `menubar.py`
   gains `start_layout_tray(window, layouts, order, state_ref, on_select)` —
   new function, `start_tray` untouched. Click handler (main thread):
   no-op if already active; else clear a shared `loaded_event`, `resize()`,
   `load_url()`, update `state_ref["layout"]`, call `icon.update_menu()` so
   the checkmark moves; spawn a daemon thread that waits on `loaded_event`
   (timeout 10s) and then calls `_push_state` once for the new page.

5. **`__main__` wiring.** Same shape as `run_second_screen.py`'s: create
   window at the default layout's size, `menubar.hide_from_dock()`,
   `start_layout_tray`, expose `minimize_window`/`close_window` (same
   deferred-Timer close pattern as the other three scripts — copy, don't
   invent a new one), `--live` flag same as today, recap window same as
   `run_second_screen.py` when `--live` and a prior recap exists.

6. **`setup_app.py`.** Copy of `setup_column.py`'s options
   (`packages: [pymorphy3_dicts_ru, _sounddevice_data, ...]`), `APP =
   ["run_app.py"]`, `DATA_FILES` covering all three HTML files + `recap.html`
   + `fixtures/*`. Build it, run the bundled binary directly (log-captured,
   not `open`) in demo mode, confirm no crash and Dock/Cmd+Tab stays hidden
   (`lsappinfo` check, same as the other three builds).

## Verification

- Full test suite green throughout (134 baseline + new tests from tasks 1
  and 2).
- Demo-mode run (not bundled) via direct `python3 run_app.py`, headless
  Playwright against the loaded HTML the way earlier sessions verified
  `second_screen.html`/`column.html` rendering — or, if a quicker check
  suffices, drive `switch_layout` from a small script during a replay run
  and confirm via captured stdout/log that no exception fires and the
  window's title/size actually changed (`window.title`, no direct pixel
  check needed for a mechanism-level check).
- py2app build of `run_app.py`, same live-mic smoke test already done for
  `run_second_screen.py`'s bundle (launch with `--live`, capture log,
  confirm the Speechmatics session stays up ~20s with no reconnect error).
