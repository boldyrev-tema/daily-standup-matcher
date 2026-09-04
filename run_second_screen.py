import json
import re
import sys
import threading
import time

import webview

import menubar
from agenda import build_agenda, pick_alarm
from credentials import load_credential
from facts import agenda_row, build_facts
from hints import get_hints
from live_audio import LiveAudioSession, build_additional_vocab
from match_core import MatchResult, ambiguous_candidates, match, resolve_pending
from meeting import Line, Meeting
from recap import build_overview, build_recap, list_recaps, read_recap, save_recap
from sprint_snapshot import Task, load_current_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
LLM_KEY_PATH = "~/.credentials/openrouter_api_key.env"
SPEECHMATICS_KEY_PATH = "~/.credentials/speechmatics_api_key.env"
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


def _primary_match(results):
    """Pick the result to drive a Line's task/hit_words and which task's
    hints get fetched. match() sorts by task recency, not confidence, so the
    first result isn't necessarily the most trustworthy one. Prefer an
    explicit_number match (confidence 1.0) over a title_words match when both
    are present; otherwise fall back to the first (most recent) result.
    """
    if not results:
        return None
    number_matches = [r for r in results if r.reason == "explicit_number"]
    return number_matches[0] if number_matches else results[0]


def _apply_pending(
    pending: tuple[Line, list[Task]] | None,
    primary: MatchResult | None,
    text: str,
    agenda: list[Task],
    meeting: Meeting,
) -> tuple[MatchResult | None, tuple[Line, list[Task]] | None]:
    """Resolve an earlier margin-blocked ambiguous line (see
    match_core.ambiguous_candidates) using this turn's extra context —
    Rinat, 2 сен: a genuine tie between two "сделки" tasks resolved on the
    very next line, leaving the first line permanently unlabeled even though
    the meeting correctly moved on. Always consumes `pending` (returns None
    for it); the caller sets a fresh one from this turn if it's itself
    ambiguous.
    """
    if pending is None:
        return primary, None
    pending_line, pending_candidates = pending
    pending_keys = {t.key for t in pending_candidates}
    if primary is not None and primary.task_key in pending_keys:
        pending_line.task = primary.task_key
        pending_line.hit_words = primary.hit_words
    elif primary is None:
        resolved = resolve_pending(pending_line.text, pending_candidates, text)
        if resolved is not None:
            pending_line.task = resolved.task_key
            pending_line.hit_words = resolved.hit_words
            meeting.mark_recognized(resolved.task_key)
            primary = resolved
    return primary, None


def _agenda_rows(agenda, meeting, alarm_task):
    by_key = {t.key: t for t in agenda}

    def _row(task):
        is_alarm = alarm_task is not None and task.key == alarm_task.key
        row, annotation = agenda_row(task, is_alarm=is_alarm)
        return {"key": task.key, "title": task.title, "row": row, "annotation": annotation, "alarm": is_alarm}

    done_rows = [_row(by_key[key]) for key in meeting.done]
    remaining_rows = [_row(t) for t in agenda if t.key not in meeting.done]
    return done_rows, remaining_rows


def _state_json(meeting: Meeting, agenda, alarm_task) -> str:
    current_task = None
    if meeting.current:
        task = next((t for t in agenda if t.key == meeting.current), None)
        if task:
            current_task = {
                "key": task.key,
                "title": task.title,
                "facts": build_facts(task),
                "said": meeting.said,
                "ask": meeting.ask,
            }
    lines = [
        {"who": l.who, "text": l.text, "task": l.task, "hit_words": l.hit_words}
        for l in meeting.lines
    ]
    done_rows, remaining_rows = _agenda_rows(agenda, meeting, alarm_task)
    return json.dumps({
        "phase": meeting.phase,
        "elapsed_s": meeting.elapsed_s,
        "lines": lines,
        "agenda": {"done": done_rows, "remaining": remaining_rows},
        "current_task": current_task,
    })


def _safe_evaluate_js(window, script: str, closing=None) -> None:
    """Fire-and-forget wrapper around window.evaluate_js(). Real bug, caught
    live via py-spy TWICE (4 сен, same stack both times): pywebview's own
    evaluate_js blocks on a plain Semaphore(0).acquire() with NO timeout at
    all (confirmed by reading webview/platforms/cocoa.py directly) — if
    window.destroy() ends the run loop while a call is still in flight, the
    calling thread waits forever for a JS response that can now never
    arrive. A `closing` flag checked BEFORE the call (first fix) stops new
    calls from starting, but can't rescue a call that had already started
    a moment earlier — that's exactly the second hang, same stack, same
    line. Running the actual evaluate_js() in its own daemon thread is the
    real fix: even if THAT thread hangs forever, a daemon thread can never
    block process shutdown (threading._shutdown() only waits on non-daemon
    threads) — `closing` is now just an optimization to skip pointless
    calls, not the safety mechanism.
    """
    if closing is not None and closing.is_set():
        return

    def _run():
        try:
            window.evaluate_js(script)
        except Exception:
            pass  # matches every prior call site's own silent best-effort try/except

    threading.Thread(target=_run, daemon=True).start()


def _process_turn(speaker, text, t, agenda, meeting, alarm_task, api_key, window, pending, push=None, closing=None):
    """One utterance through the full pipeline: match -> pending-carryover
    resolution -> Meeting/Line bookkeeping -> render -> hints. Shared by the
    file replay (_run_replay) and the live-microphone path (_run_live) so
    the two can never drift into different matching behavior. Returns the
    (possibly updated) pending-ambiguity state for the next call.

    `push` defaults to pushing the rich second-screen/column state to
    `window`, matching every caller before run_app.py existed. run_app.py
    passes its own push that dispatches to whichever layout is currently on
    screen (see run_app.py's _push_state) — the one caller allowed to
    override this, since it's the only one juggling more than one layout on
    the same window. See _safe_evaluate_js for what `closing` actually
    protects against.
    """
    if closing is not None and closing.is_set():
        return pending
    if push is None:
        push = lambda: _safe_evaluate_js(
            window, f"renderMeeting({_state_json(meeting, agenda, alarm_task)})", closing
        )

    results = match(text, agenda)
    primary = _primary_match(results)
    primary, pending = _apply_pending(pending, primary, text, agenda, meeting)

    task_key = primary.task_key if primary else None
    hit_words = primary.hit_words if primary else []
    line = Line(t=t, who=speaker, text=text, task=task_key, hit_words=hit_words)
    meeting.add_line(line)
    for r in results:
        meeting.mark_recognized(r.task_key)
    if primary:
        meeting.current = primary.task_key
    else:
        candidates = ambiguous_candidates(text, agenda)
        if len(candidates) >= 2:
            pending = (line, candidates)

    push()

    if primary:
        task = next(x for x in agenda if x.key == primary.task_key)
        said, ask = get_hints(meeting.lines, task, api_key)
        meeting.set_hints(said, ask)
        push()

        while meeting.reveal_next_said():
            time.sleep(1.2)
            push()

    return pending


def _run_replay(window, loaded_event, closing=None):
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
        _safe_evaluate_js(window, f"renderMeeting({_state_json(meeting, agenda, alarm_task)})", closing)
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
            pending = _process_turn(
                turn["speaker"], turn["text"], t, agenda, meeting, alarm_task, api_key, window, pending,
                closing=closing,
            )

        meeting.phase = "after"
        _safe_evaluate_js(window, f"renderMeeting({_state_json(meeting, agenda, alarm_task)})", closing)
    except Exception as e:
        print(f"second screen replay failed: {e}", file=sys.stderr)
        _safe_evaluate_js(
            window,
            f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}",
            closing,
        )


def _run_live(window, loaded_event, closing=None):
    """Live daily: replaces sample_daily_transcript.json with a real
    Speechmatics stream off the mic (+ system/call audio if
    SYSTEM_AUDIO_DUMP_PATH is set — see live_audio.py). Matcher, agenda,
    hints, window — all unchanged, same as _process_turn shared with replay.

    `closing` — see _process_turn's docstring for the real, py-spy-confirmed
    bug this guards against (4 сен): without it, a turn recognized right as
    the window closes can hang this thread in evaluate_js() forever, which
    hangs process shutdown since webview.start() spawns this non-daemon.
    """
    try:
        loaded_event.wait(timeout=10)

        tasks, team = load_current_sprint("fixtures/sprint.json", TEAM)
        agenda = build_agenda(tasks, team)
        alarm_task = pick_alarm(agenda)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")
        speechmatics_key = load_credential(SPEECHMATICS_KEY_PATH, "SPEECHMATICS_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
        _safe_evaluate_js(window, f"renderMeeting({_state_json(meeting, agenda, alarm_task)})", closing)

        state = {"pending": None}
        lock = threading.Lock()
        start = time.monotonic()

        def on_turn(speaker: str, text: str) -> None:
            # Speechmatics calls this from its own asyncio thread — one turn
            # processed at a time so pending-carryover state can't race.
            if closing is not None and closing.is_set():
                return
            with lock:
                t = time.monotonic() - start
                state["pending"] = _process_turn(
                    speaker, text, t, agenda, meeting, alarm_task, api_key, window, state["pending"],
                    closing=closing,
                )

        session = LiveAudioSession(speechmatics_key, on_turn, additional_vocab=build_additional_vocab(agenda))
        session.start()
        # events.closed, not events.closing: closing only fires via Cocoa's
        # windowShouldClose_ delegate method, which performClose_ (the
        # native red button / Cmd+W) triggers but a direct .close() call
        # does not — and our own close_window() calls window.destroy(),
        # which goes straight to .close(). closed fires unconditionally
        # from windowWillClose_ regardless of how the window closed
        # (confirmed by reading webview/platforms/cocoa.py directly, 2 сен:
        # neither session.stop() nor the recap save were ever actually
        # firing on our own close button — only closing was wired up).
        window.events.closed += session.stop

        def _save_recap_on_close():
            # Non-daemon: closing the window must not wait for this, but the
            # process itself needs to stay alive until it's done writing —
            # see docs/superpowers/specs/2026-09-02-daily-recap-design.md
            # ("Не блокировать закрытие окна").
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
        print(f"live run failed: {e}", file=sys.stderr)
        _safe_evaluate_js(
            window,
            f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}",
            closing,
        )


if __name__ == "__main__":
    window = webview.create_window(
        "Второй экран",
        "second_screen.html",
        width=1100,
        height=760,
        frameless=True,
        on_top=True,
        transparent=True,
    )
    # Must run AFTER create_window() — see run_column.py's comment at the
    # same call site for why.
    menubar.hide_from_dock()

    tray_icon, hide_window = menubar.start_tray(window, "Э")

    closing_event = threading.Event()

    def minimize_window():
        hide_window()

    def close_window():
        # Set FIRST, synchronously, not deferred — a real py-spy-confirmed
        # bug (4 сен): webview.start() spawns _run_replay/_run_live as a
        # non-daemon thread, and once window.destroy() ends the run loop,
        # any evaluate_js() call still in flight from that thread blocks
        # forever (no timeout in pywebview's own implementation) — the
        # whole process then hangs in threading._shutdown(), waiting on a
        # thread that can never finish. closing_event lets that thread
        # notice and stop pushing before destroy() ever runs.
        closing_event.set()

        # window.destroy() ends the Cocoa run loop webview.start() is
        # driving. If that happens before THIS exposed call's own return
        # value has gone back to JS (also delivered through that same main-
        # thread run loop via evaluate_js), the two race — and can deadlock
        # forever, not just stall. Confirmed live via a py-spy thread dump
        # (2 сен): the main thread was stuck in threading._shutdown() while
        # pywebview's own JS-bridge response thread sat blocked in
        # evaluate_js, waiting on a run loop that no longer existed. A short
        # delay lets this call's own response go out first, on a still-live
        # run loop, before destroy() ends it.
        #
        # tray_icon.stop() has the exact same hazard: it's an AppKit call
        # (postEvent_atStart_) plus a blocking thread join, and calling it
        # synchronously here — on the JS-bridge thread, not main — hung the
        # window on a live test (2 сен, real user report: spinning cursor,
        # never closed). Deferred into the same delayed callback as
        # destroy() so it doesn't block this exposed call's own return either.
        #
        # Order matters, found live (4 сен): window.destroy() is itself just
        # AppHelper.callAfter(window.close) (see webview/platforms/cocoa.py)
        # — it SCHEDULES the close on the run loop rather than closing
        # synchronously. tray_icon.stop() running FIRST can stop that same
        # shared run loop before the scheduled close is ever processed, so
        # windowWillClose_ (and therefore events.closed, and everything
        # wired to it — session.stop, the recap save) never fires at all.
        # Confirmed with a temporary print on events.closed that silently
        # never fired even though window.destroy() itself returned normally
        # — the recap had never actually saved once, this whole time.
        # destroy() first, tray_icon.stop() after, fixes it.
        def _do_close():
            window.destroy()
            tray_icon.stop()

        menubar.defer(0.15, _do_close)

    # Picker for past dailies (Granola/Fireflies-style: browse by date, not
    # just the single most recent one) — the page itself pulls this via
    # pywebview.api.list_recaps()/read_recap() on its own load event (see
    # second_screen.html's loadRecapList()), no Python-side push needed.
    # Exposed regardless of --live/--demo — browsing past real recaps
    # doesn't depend on how THIS run started.
    window.expose(minimize_window, close_window, list_recaps, read_recap)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set

    is_live = "--live" in sys.argv
    target = _run_live if is_live else _run_replay
    webview.start(target, (window, loaded_event, closing_event))
