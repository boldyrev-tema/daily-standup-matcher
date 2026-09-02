import json
import re
import sys
import threading
import time

import webview

from agenda import build_agenda, pick_alarm
from credentials import load_credential
from facts import agenda_row, build_facts
from hints import get_hints
from live_audio import LiveAudioSession, build_additional_vocab
from match_core import MatchResult, ambiguous_candidates, match, resolve_pending
from meeting import Line, Meeting
from recap import build_recap, latest_recap, save_recap
from sprint_snapshot import Task, load_sprint

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


def _process_turn(speaker, text, t, agenda, meeting, alarm_task, api_key, window, pending):
    """One utterance through the full pipeline: match -> pending-carryover
    resolution -> Meeting/Line bookkeeping -> render -> hints. Shared by the
    file replay (_run_replay) and the live-microphone path (_run_live) so
    the two can never drift into different matching behavior. Returns the
    (possibly updated) pending-ambiguity state for the next call.
    """
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

    window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

    if primary:
        task = next(x for x in agenda if x.key == primary.task_key)
        said, ask = get_hints(meeting.lines, task, api_key)
        meeting.set_hints(said, ask)
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

        while meeting.reveal_next_said():
            time.sleep(1.2)
            window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

    return pending


def _run_replay(window, loaded_event):
    try:
        # Wait for the page's real load event instead of guessing a fixed
        # delay — on a busy machine 3s isn't always enough and evaluate_js
        # fails with "Can't find variable: renderMeeting" (Rinat, 31 авг,
        # hit this twice on his machine).
        loaded_event.wait(timeout=10)

        tasks = load_sprint("fixtures/sprint.json")
        agenda = build_agenda(tasks, TEAM)
        alarm_task = pick_alarm(agenda)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")

        meeting = Meeting(phase="before", remaining_count=len(agenda))
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
        time.sleep(2)
        meeting.phase = "live"

        t = 0.0
        pending: tuple[Line, list] | None = None
        for turn in transcript:
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause
            pending = _process_turn(
                turn["speaker"], turn["text"], t, agenda, meeting, alarm_task, api_key, window, pending
            )

        meeting.phase = "after"
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
    except Exception as e:
        print(f"second screen replay failed: {e}", file=sys.stderr)
        try:
            window.evaluate_js(
                f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}"
            )
        except Exception:
            pass


def _run_live(window, loaded_event):
    """Live daily: replaces sample_daily_transcript.json with a real
    Speechmatics stream off the mic (+ system/call audio if
    SYSTEM_AUDIO_DUMP_PATH is set — see live_audio.py). Matcher, agenda,
    hints, window — all unchanged, same as _process_turn shared with replay.
    """
    try:
        loaded_event.wait(timeout=10)

        tasks = load_sprint("fixtures/sprint.json")
        agenda = build_agenda(tasks, TEAM)
        alarm_task = pick_alarm(agenda)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")
        speechmatics_key = load_credential(SPEECHMATICS_KEY_PATH, "SPEECHMATICS_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

        state = {"pending": None}
        lock = threading.Lock()
        start = time.monotonic()

        def on_turn(speaker: str, text: str) -> None:
            # Speechmatics calls this from its own asyncio thread — one turn
            # processed at a time so pending-carryover state can't race.
            with lock:
                t = time.monotonic() - start
                state["pending"] = _process_turn(
                    speaker, text, t, agenda, meeting, alarm_task, api_key, window, state["pending"]
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
                    if records:
                        save_recap(records)
                except Exception as e:
                    print(f"recap save failed: {e}", file=sys.stderr)

            threading.Thread(target=_do_save, daemon=False).start()

        window.events.closed += _save_recap_on_close
        print("Живой микрофон запущен — говорите; закройте окно, чтобы остановить.")
    except Exception as e:
        print(f"live run failed: {e}", file=sys.stderr)
        try:
            window.evaluate_js(
                f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}"
            )
        except Exception:
            pass


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

    def minimize_window():
        window.minimize()

    def close_window():
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
        threading.Timer(0.15, window.destroy).start()

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set

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
                # Same fix as the main window's close_window — see its
                # comment for why a bare thread isn't enough.
                threading.Timer(0.15, recap_window.destroy).start()

            recap_window.expose(close_recap_window)
            recap_loaded_event = threading.Event()
            recap_window.events.loaded += recap_loaded_event.set

            def _show_recap():
                recap_loaded_event.wait(timeout=10)
                recap_window.evaluate_js(f"renderRecap({json.dumps(prior_recap, ensure_ascii=False)})")

            threading.Thread(target=_show_recap, daemon=True).start()

    target = _run_live if is_live else _run_replay
    webview.start(target, (window, loaded_event))
