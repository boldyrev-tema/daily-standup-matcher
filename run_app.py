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
from recap import build_recap, latest_recap, save_recap
from run_polosa_replay import _state_json as _polosa_state_json
from run_second_screen import LLM_KEY_PATH, SPEECHMATICS_KEY_PATH, TEAM, _WORD_RE, _process_turn
from run_second_screen import _state_json as _rich_state_json
from sprint_snapshot import load_current_sprint

LAYOUTS = {
    "second_screen": {"label": "Второй экран", "html": "second_screen.html", "width": 1100, "height": 760},
    "column": {"label": "Колонка", "html": "column.html", "width": 400, "height": 880},
    "polosa": {"label": "Полоса", "html": "polosa.html", "width": 1200, "height": 200},
}
LAYOUT_ORDER = ("second_screen", "column", "polosa")
DEFAULT_LAYOUT = "second_screen"


def _push_state(layout_key, window, meeting, agenda, alarm_task):
    """Полоса reads a reduced state shape (its own _state_json in
    run_polosa_replay.py, no alarm_task) — Колонка and Второй экран already
    share the rich one verbatim (run_column.py imports it as-is). Two
    existing builders, not unified into one — see the design spec for why.
    """
    if layout_key == "polosa":
        window.evaluate_js(f"renderMeeting({_polosa_state_json(meeting, agenda)})")
    else:
        window.evaluate_js(f"renderMeeting({_rich_state_json(meeting, agenda, alarm_task)})")


def _run_replay(window, loaded_event, state_ref, session_ref):
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
        push = lambda: _push_state(state_ref["layout"], window, meeting, agenda, alarm_task)
        push()
        time.sleep(2)
        meeting.phase = "live"

        t = 0.0
        pending = None
        for turn in transcript:
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause
            pending = _process_turn(
                turn["speaker"], turn["text"], t, agenda, meeting, alarm_task, api_key, window, pending, push=push
            )

        meeting.phase = "after"
        push()
    except Exception as e:
        print(f"unified app replay failed: {e}", file=sys.stderr)


def _run_live(window, loaded_event, state_ref, session_ref):
    try:
        loaded_event.wait(timeout=10)

        tasks, team = load_current_sprint("fixtures/sprint.json", TEAM)
        agenda = build_agenda(tasks, team)
        alarm_task = pick_alarm(agenda)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")
        speechmatics_key = load_credential(SPEECHMATICS_KEY_PATH, "SPEECHMATICS_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
        session_ref.update(meeting=meeting, agenda=agenda, alarm_task=alarm_task)
        push = lambda: _push_state(state_ref["layout"], window, meeting, agenda, alarm_task)
        push()

        state = {"pending": None}
        lock = threading.Lock()
        start = time.monotonic()

        def on_turn(speaker: str, text: str) -> None:
            with lock:
                t = time.monotonic() - start
                state["pending"] = _process_turn(
                    speaker, text, t, agenda, meeting, alarm_task, api_key, window, state["pending"], push=push
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
                    if records:
                        save_recap(records)
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
                _push_state(key, window, session_ref["meeting"], session_ref["agenda"], session_ref["alarm_task"])

        threading.Thread(target=_wait_and_push, daemon=True).start()

    tray_icon, hide_window = menubar.start_layout_tray(window, LAYOUTS, LAYOUT_ORDER, state_ref, switch_layout)

    def minimize_window():
        hide_window()

    def close_window():
        # Same deadlock-avoidance shape as every other run_*.py's
        # close_window — see run_second_screen.py's for the full
        # py-spy-confirmed reasoning.
        def _do_close():
            tray_icon.stop()
            window.destroy()

        threading.Timer(0.15, _do_close).start()

    window.expose(minimize_window, close_window)

    is_live = "--live" in sys.argv
    if is_live:
        prior_recap = latest_recap()
        if prior_recap is not None:
            recap_window = webview.create_window(
                "Прошлый дейлик",
                "recap.html",
                width=380,
                height=500,
                x=1160,
                y=40,
                frameless=True,
                on_top=True,
                transparent=True,
            )

            def close_recap_window():
                threading.Timer(0.15, recap_window.destroy).start()

            recap_window.expose(close_recap_window)
            recap_loaded_event = threading.Event()
            recap_window.events.loaded += recap_loaded_event.set

            def _show_recap():
                recap_loaded_event.wait(timeout=10)
                recap_window.evaluate_js(f"renderRecap({json.dumps(prior_recap, ensure_ascii=False)})")

            threading.Thread(target=_show_recap, daemon=True).start()

    target = _run_live if is_live else _run_replay
    webview.start(target, (window, loaded_event, state_ref, session_ref))
