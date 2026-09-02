import json
import re
import sys
import threading
import time

import webview

from agenda import build_agenda
from credentials import load_credential
from facts import build_facts
from hints import get_hints
from match_core import ambiguous_candidates, match
from meeting import Line, Meeting
from run_second_screen import _apply_pending
from sprint_snapshot import load_sprint

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


def _run_replay(window, loaded_event):
    try:
        # Wait for the page's real load event instead of guessing a fixed
        # delay — on a busy machine 3s isn't always enough and evaluate_js
        # fails with "Can't find variable: renderMeeting" (Rinat, 31 авг,
        # hit this twice on his machine).
        loaded_event.wait(timeout=10)

        tasks = load_sprint("fixtures/sprint.json")
        agenda = build_agenda(tasks, TEAM)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(LLM_KEY_PATH, "OPENROUTER_API_KEY")

        meeting = Meeting(phase="live", remaining_count=len(agenda))
        t = 0.0
        pending: tuple[Line, list] | None = None
        for turn in transcript:
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
            window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")

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
                window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")

        meeting.phase = "after"
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")
    except Exception as e:
        print(f"polosa replay failed: {e}", file=sys.stderr)
        try:
            window.evaluate_js(
                f"document.getElementById('hear-text').textContent = {json.dumps(f'Ошибка: {e}')}"
            )
        except Exception:
            pass


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

    def minimize_window():
        window.minimize()

    def close_window():
        window.destroy()

    window.expose(minimize_window, close_window)
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    webview.start(_run_replay, (window, loaded_event))
