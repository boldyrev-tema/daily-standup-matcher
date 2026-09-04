"""Unified app: one process, one window, live choice of layout inside the
product (docs/superpowers/specs/2026-09-03-unified-app-design.md). The
three standalone run_*.py scripts (and their .command/.app launchers) keep
working exactly as before, untouched — this is a new, additional entry
point, not a replacement.

The meeting — agenda, matcher state, live Speechmatics session or file
replay — lives entirely here and never restarts on a layout switch;
switching only changes what's loaded into the one window (see
switch_layout() in __main__).
"""
import json
import sys
import threading
import time

import webview

import menubar
from agenda import build_agenda, pick_alarm
from credentials import load_credential
from live_audio import LiveAudioSession, build_additional_vocab
from meeting import Meeting
from recap import build_overview, build_recap, latest_recap, save_recap
from run_polosa_replay import _state_json as _polosa_state_json
from run_second_screen import LLM_KEY_PATH, SPEECHMATICS_KEY_PATH, TEAM, _WORD_RE, _process_turn, _safe_evaluate_js
from run_second_screen import _state_json as _rich_state_json
from sprint_snapshot import load_current_sprint

LAYOUTS = {
    "second_screen": {"label": "Второй экран", "html": "second_screen.html", "width": 1100, "height": 760},
    "column": {"label": "Колонка", "html": "column.html", "width": 400, "height": 880},
    "polosa": {"label": "Полоса", "html": "polosa.html", "width": 1200, "height": 200},
}
LAYOUT_ORDER = ("second_screen", "column", "polosa")
DEFAULT_LAYOUT = "second_screen"


def _push_state(layout_key, window, meeting, agenda, alarm_task, closing=None):
    """Полоса reads a reduced state shape (its own _state_json in
    run_polosa_replay.py, no alarm_task) — Колонка and Второй экран already
    share the rich one verbatim (run_column.py imports it as-is). Two
    existing builders, not unified into one — see the design spec for why.

    `closing` — see _safe_evaluate_js's docstring (run_second_screen.py) for
    the real, py-spy-confirmed bug this guards against (4 сен, hit TWICE
    with the exact same stack): a `closing` check before the call alone
    isn't enough — it can't rescue a call that had already started a moment
    earlier. _safe_evaluate_js runs the actual evaluate_js() in its own
    daemon thread, which is what actually makes a hung call harmless.
    """
    if layout_key == "polosa":
        _safe_evaluate_js(window, f"renderMeeting({_polosa_state_json(meeting, agenda)})", closing)
    else:
        _safe_evaluate_js(window, f"renderMeeting({_rich_state_json(meeting, agenda, alarm_task)})", closing)


def _run_replay(window, loaded_event, state_ref, session_ref, closing=None):
    try:
        # Same "wait for the real load event" reasoning as every other
        # run_*.py — see run_second_screen.py's _run_replay.
        loaded_event.wait(timeout=10)

        tasks, team = load_current_sprint("fixtures/sprint.json", TEAM)
        agenda = build_agenda(tasks, team)
        alarm_task = pick_alarm(agenda)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")

        meeting = Meeting(phase="before", remaining_count=len(agenda))
        session_ref.update(meeting=meeting, agenda=agenda, alarm_task=alarm_task)
        push = lambda: _push_state(state_ref["layout"], window, meeting, agenda, alarm_task, closing=closing)
        push()
        time.sleep(2)
        meeting.phase = "live"

        t = 0.0
        pending = None
        for turn in transcript:
            if closing is not None and closing.is_set():
                return
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause
            pending = _process_turn(
                turn["speaker"], turn["text"], t, agenda, meeting, alarm_task, api_key, window, pending, push=push,
                closing=closing,
            )

        meeting.phase = "after"
        push()
    except Exception as e:
        print(f"unified app replay failed: {e}", file=sys.stderr)


def _run_live(window, loaded_event, state_ref, session_ref, closing=None):
    try:
        loaded_event.wait(timeout=10)

        tasks, team = load_current_sprint("fixtures/sprint.json", TEAM)
        agenda = build_agenda(tasks, team)
        alarm_task = pick_alarm(agenda)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")
        speechmatics_key = load_credential(SPEECHMATICS_KEY_PATH, "SPEECHMATICS_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
        session_ref.update(meeting=meeting, agenda=agenda, alarm_task=alarm_task)
        push = lambda: _push_state(state_ref["layout"], window, meeting, agenda, alarm_task, closing=closing)
        push()

        state = {"pending": None}
        lock = threading.Lock()
        start = time.monotonic()

        def on_turn(speaker: str, text: str) -> None:
            if closing is not None and closing.is_set():
                return
            with lock:
                t = time.monotonic() - start
                state["pending"] = _process_turn(
                    speaker, text, t, agenda, meeting, alarm_task, api_key, window, state["pending"], push=push,
                    closing=closing,
                )

        session = LiveAudioSession(speechmatics_key, on_turn, additional_vocab=build_additional_vocab(agenda))
        session.start()
        # events.closed, not events.closing — see run_second_screen.py's
        # _run_live for the full py-spy-confirmed reasoning.
        window.events.closed += session.stop

        def _save_recap_on_close():
            def _do_save():
                try:
                    records = build_recap(meeting, agenda, api_key)
                    overview = build_overview(meeting, api_key)
                    if records or overview["gist"] or overview["topics"]:
                        save_recap(records, overview)
                except Exception as e:
                    print(f"recap save failed: {e}", file=sys.stderr)

            threading.Thread(target=_do_save, daemon=False).start()

        window.events.closed += _save_recap_on_close
        print("Живой микрофон запущен — говорите; закройте окно, чтобы остановить.")
    except Exception as e:
        print(f"unified app live run failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    default_spec = LAYOUTS[DEFAULT_LAYOUT]
    window = webview.create_window(
        "Дейлик",
        default_spec["html"],
        width=default_spec["width"],
        height=default_spec["height"],
        frameless=True,
        on_top=True,
        transparent=True,
    )
    # Must run AFTER create_window() — see run_column.py's comment at the
    # same call site for why.
    menubar.hide_from_dock()

    state_ref = {"layout": DEFAULT_LAYOUT}
    session_ref = {"meeting": None, "agenda": None, "alarm_task": None}
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    closing_event = threading.Event()

    # Only second_screen.html has the recap-panel markup/JS (renderRecap) —
    # captured here, before switch_layout, so both it and the startup block
    # below can push into whichever window instance is live at the time.
    prior_recap = latest_recap()

    def _push_recap_if_second_screen(key):
        if key == "second_screen" and prior_recap is not None:
            _safe_evaluate_js(
                window, f"renderRecap({json.dumps(prior_recap, ensure_ascii=False)})", closing_event
            )

    def switch_layout(key):
        """Runs on the main thread (tray click handler) — resize/load_url
        are safe to call synchronously here (see menubar.start_layout_tray's
        docstring). Waiting for the new page's own loaded event is NOT safe
        synchronously (that event only fires once the run loop processes the
        navigation) — deferred to a daemon thread, same shape as every other
        loaded_event.wait in this codebase.
        """
        if state_ref["layout"] == key:
            return
        spec = LAYOUTS[key]
        loaded_event.clear()
        window.resize(spec["width"], spec["height"])
        window.load_url(spec["html"])
        state_ref["layout"] = key

        def _wait_and_push():
            if loaded_event.wait(timeout=10) and session_ref["meeting"] is not None:
                _push_state(
                    key, window, session_ref["meeting"], session_ref["agenda"], session_ref["alarm_task"],
                    closing=closing_event,
                )
                _push_recap_if_second_screen(key)

        threading.Thread(target=_wait_and_push, daemon=True).start()

    tray_icon, hide_window = menubar.start_layout_tray(window, LAYOUTS, LAYOUT_ORDER, state_ref, switch_layout)

    def minimize_window():
        hide_window()

    def close_window():
        # Set FIRST, synchronously — real py-spy-confirmed bug (4 сен): the
        # replay/live thread is non-daemon and can hang forever in
        # evaluate_js() after the window is destroyed, since that thread
        # doesn't otherwise know the window (and its run loop) are gone. See
        # _push_state's docstring for the full story.
        closing_event.set()

        # window.destroy() itself is just AppHelper.callAfter(window.close)
        # (see webview/platforms/cocoa.py) — it SCHEDULES the close on the
        # run loop, it doesn't close synchronously. tray_icon.stop() calling
        # into the SAME shared Cocoa run loop, if it runs FIRST, can stop
        # that loop before the scheduled window.close ever gets processed —
        # windowWillClose_ (and therefore events.closed, and everything
        # wired to it: session.stop, the recap save) then never fires at
        # all. Real bug, caught live (4 сен) with a temporary print on
        # events.closed that never fired even though window.destroy() itself
        # returned normally — the recap had silently never saved once, ever,
        # since the feature was written. Fix: destroy() first (let the close
        # actually get scheduled+processed), tray_icon.stop() after, still
        # deferred (calling it synchronously on the wrong thread was the
        # ORIGINAL hazard this function already guards against — see git
        # history for that one).
        def _do_close():
            window.destroy()
            tray_icon.stop()

        menubar.defer(0.15, _do_close)

    window.expose(minimize_window, close_window)

    # Live by default, not opt-in — unlike the three standalone run_*.py
    # (still --live-opt-in, meant for trying things out/debugging from a
    # terminal, see README's "Two ways to run it"), this is the packaged
    # app's whole reason to exist: by the time someone reaches for
    # dist/Дейлик.app instead of a script, the intent is already "use this
    # on a real daily." Double-clicking an .app can't pass arguments at
    # all, so a --live-required default would have meant demo forever for
    # anyone not launching from a terminal. --demo is the explicit opt-out
    # for testing/demoing without a microphone.
    is_live = "--demo" not in sys.argv
    if is_live and prior_recap is not None:
        # DEFAULT_LAYOUT is "second_screen", so this is safe at startup —
        # switch_layout's own _push_recap_if_second_screen handles it if the
        # user later switches away and back.
        def _show_recap():
            loaded_event.wait(timeout=10)
            _push_recap_if_second_screen(state_ref["layout"])

        threading.Thread(target=_show_recap, daemon=True).start()

    target = _run_live if is_live else _run_replay
    webview.start(target, (window, loaded_event, state_ref, session_ref, closing_event))
