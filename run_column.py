import json
import sys
import threading
import time

import webview

import menubar
from agenda import build_agenda, pick_alarm
from credentials import load_credential
from hints import get_hints
from match_core import ambiguous_candidates, match
from meeting import Line, Meeting
from run_second_screen import (
    LLM_KEY_PATH, TEAM, _WORD_RE, _apply_pending, _primary_match, _safe_evaluate_js, _state_json,
)
from sprint_snapshot import load_current_sprint


def _run_replay(window, loaded_event, closing=None):
    """`closing` — see _safe_evaluate_js's docstring (run_second_screen.py)
    for the real, py-spy-confirmed bug this guards against (4 сен, hit
    TWICE with the same stack): evaluate_js() has no timeout in pywebview's
    own implementation, so a call still in flight when window.destroy()
    ends the run loop blocks its thread forever — fatal since
    webview.start() spawns this as non-daemon. Every evaluate_js call site
    goes through _safe_evaluate_js (fires the call in its own daemon
    thread, so even a hung call can never block process shutdown); the loop
    itself also bails out early once closing is set, to stop doing pointless
    work (LLM calls included).
    """
    def push(js: str) -> None:
        _safe_evaluate_js(window, js, closing)

    try:
        # Wait for the page's real load event instead of guessing a fixed
        # delay — on a busy machine 3s isn't always enough and evaluate_js
        # fails with "Can't find variable: renderMeeting" (Rinat, 31 авг,
        # hit this twice on his machine).
        loaded_event.wait(timeout=10)

        tasks, team = load_current_sprint("fixtures/sprint.json", TEAM)
        agenda = build_agenda(tasks, team)
        alarm_task = pick_alarm(agenda)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")

        meeting = Meeting(phase="before", remaining_count=len(agenda))
        push(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
        time.sleep(2)
        meeting.phase = "live"

        t = 0.0
        pending: tuple[Line, list] | None = None
        for turn in transcript:
            if closing is not None and closing.is_set():
                return
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause

            results = match(turn["text"], agenda)
            primary = _primary_match(results)
            primary, pending = _apply_pending(pending, primary, turn["text"], agenda, meeting)

            task_key = primary.task_key if primary else None
            hit_words = primary.hit_words if primary else []
            line = Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key, hit_words=hit_words)
            meeting.add_line(line)
            for r in results:
                meeting.mark_recognized(r.task_key)
            if primary:
                meeting.current = primary.task_key
            else:
                candidates = ambiguous_candidates(turn["text"], agenda)
                if len(candidates) >= 2:
                    pending = (line, candidates)

            push(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

            if primary:
                task = next(x for x in agenda if x.key == primary.task_key)
                said, ask = get_hints(meeting.lines, task, api_key)
                meeting.set_hints(said, ask)
                push(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

                while meeting.reveal_next_said():
                    time.sleep(1.2)
                    push(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

        meeting.phase = "after"
        push(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
    except Exception as e:
        print(f"column replay failed: {e}", file=sys.stderr)
        push(f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}")


if __name__ == "__main__":
    window = webview.create_window(
        "Колонка",
        "column.html",
        width=400,
        height=880,
        frameless=True,
        on_top=True,
        transparent=True,
    )
    # Must run AFTER create_window(): pywebview lazily imports its Cocoa
    # backend inside create_window(), and that backend's own class body sets
    # setActivationPolicy_(0) (Regular) itself — calling this any earlier
    # gets silently overwritten (confirmed empirically: NSRunningApplication
    # still reported policy 0 after a "before create_window" placement).
    menubar.hide_from_dock()

    tray_icon, hide_window = menubar.start_tray(window, "К")

    closing_event = threading.Event()

    def minimize_window():
        hide_window()

    def close_window():
        # Set FIRST, synchronously — see run_second_screen.py's close_window
        # and _run_replay's docstring for the real, py-spy-confirmed bug
        # this guards against (4 сен): the replay thread is non-daemon and
        # can hang forever in evaluate_js() after the window is destroyed.
        closing_event.set()

        # See run_second_screen.py's close_window — window.destroy() ending
        # the run loop before this call's own JS response goes out can
        # deadlock the whole process (confirmed live via py-spy). A short
        # delay lets the response go out first.
        #
        # tray_icon.stop() has the exact same hazard (AppKit call + blocking
        # thread join) — deferred into the same delayed callback, not called
        # synchronously here, for the same reason. See run_second_screen.py's
        # close_window for the live report that caught this (2 сен: spinning
        # cursor, window never closed).
        #
        # Order matters too, found live 4 сен (see run_second_screen.py's
        # close_window for the full story): tray_icon.stop() running before
        # window.destroy() can stop the shared Cocoa run loop before
        # destroy()'s own scheduled close (AppHelper.callAfter) ever gets
        # processed, silently breaking events.closed/session.stop entirely.
        def _do_close():
            window.destroy()
            tray_icon.stop()

        menubar.defer(0.15, _do_close)

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    webview.start(_run_replay, (window, loaded_event, closing_event))
