import json
import re
import sys
import threading
import time

import webview

import menubar
from agenda import build_agenda
from credentials import load_credential
from facts import build_facts
from hints import get_hints
from match_core import ambiguous_candidates, match
from meeting import Line, Meeting
from run_second_screen import _apply_pending, _safe_evaluate_js
from sprint_snapshot import load_current_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
LLM_KEY_PATH = "~/.credentials/openrouter_api_key.env"
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


def _primary_match(results):
    """Pick the result to use for a Line's `task` field and for which task's
    hints get fetched. match() sorts by task recency, not confidence, so the
    first result isn't necessarily the most trustworthy one. Prefer an
    explicit_number match (confidence 1.0) over a title_words match when both
    are present; otherwise fall back to the first (most recent) result.
    """
    if not results:
        return None
    number_matches = [r for r in results if r.reason == "explicit_number"]
    return number_matches[0] if number_matches else results[0]


def _state_json(meeting: Meeting, agenda) -> str:
    current_task = None
    if meeting.current:
        task = next((t for t in agenda if t.key == meeting.current), None)
        if task:
            first_fact = build_facts(task)[0]
            current_task = {"title": task.title, "first_fact": first_fact}
    last_line = None
    if meeting.lines:
        l = meeting.lines[-1]
        last_line = {"who": l.who, "text": l.text}
    return json.dumps({
        "phase": meeting.phase,
        "elapsed_s": meeting.elapsed_s,
        "remaining_count": meeting.remaining_count,
        "last_line": last_line,
        "current_task": current_task,
        "ask": meeting.ask,
    })


def _run_replay(window, loaded_event, closing=None):
    """`closing` — see _safe_evaluate_js's docstring (run_second_screen.py)
    for the real, py-spy-confirmed bug this guards against (4 сен, hit
    TWICE with the same stack): evaluate_js() has no timeout in pywebview's
    own implementation, so a call still in flight when window.destroy()
    ends the run loop blocks its thread forever — fatal since
    webview.start() spawns this as non-daemon. Every evaluate_js call site
    goes through _safe_evaluate_js (fires the call in its own daemon
    thread, so even a hung call can never block process shutdown); the loop
    itself also bails out early once closing is set.
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
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
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
            line = Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key)
            meeting.add_line(line)
            for r in results:
                meeting.mark_recognized(r.task_key)
            if primary is None:
                candidates = ambiguous_candidates(turn["text"], agenda)
                if len(candidates) >= 2:
                    pending = (line, candidates)

            # Push immediately so the new line + task card appear without
            # waiting on the (up to 3s) Groq call below.
            push(f"renderMeeting({_state_json(meeting, agenda)})")

            if primary:
                task = next(x for x in agenda if x.key == primary.task_key)
                said, ask = get_hints(meeting.lines, task, api_key)
                # polosa.html's reduced view never reads meeting.said/said_n
                # (see design spec's "Полоса" section) — the progressive
                # one-at-a-time reveal loop is only meaningful for a future
                # full-view placement. Setting the hints once keeps the data
                # canonical on Meeting without pushing an unchanged payload
                # to the browser on a sleep loop that has zero visible effect
                # here.
                meeting.set_hints(said, ask)
                # Second push once hints are ready, so the ask/said pill
                # appears without having blocked the earlier push above.
                push(f"renderMeeting({_state_json(meeting, agenda)})")

        meeting.phase = "after"
        push(f"renderMeeting({_state_json(meeting, agenda)})")
    except Exception as e:
        print(f"polosa replay failed: {e}", file=sys.stderr)
        push(f"document.getElementById('hear-text').textContent = {json.dumps(f'Ошибка: {e}')}")


if __name__ == "__main__":
    window = webview.create_window(
        "Полоса",
        "polosa.html",
        width=1200,
        height=200,
        frameless=True,
        on_top=True,
        transparent=True,
    )
    # Must run AFTER create_window() — see run_column.py's comment at the
    # same call site for why.
    menubar.hide_from_dock()

    tray_icon, hide_window = menubar.start_tray(window, "П")

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
        def _do_close():
            tray_icon.stop()
            window.destroy()

        menubar.defer(0.15, _do_close)

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    webview.start(_run_replay, (window, loaded_event, closing_event))
