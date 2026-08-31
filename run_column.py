import json
import sys
import threading
import time

import webview

from agenda import build_agenda, pick_alarm
from credentials import load_credential
from hints import get_hints
from match_core import match
from meeting import Line, Meeting
from run_second_screen import LLM_KEY_PATH, TEAM, _WORD_RE, _primary_match, _state_json
from sprint_snapshot import load_sprint


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
        for turn in transcript:
            word_count = len(_WORD_RE.findall(turn["text"]))
            pause = max(word_count, 1) * 0.4
            time.sleep(pause)
            t += pause

            results = match(turn["text"], agenda)
            primary = _primary_match(results)
            task_key = primary.task_key if primary else None
            hit_words = primary.hit_words if primary else []
            meeting.add_line(Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key, hit_words=hit_words))
            for r in results:
                meeting.mark_recognized(r.task_key)
            if primary:
                meeting.current = primary.task_key

            window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

            if primary:
                task = next(x for x in agenda if x.key == primary.task_key)
                said, ask = get_hints(meeting.lines, task, api_key)
                meeting.set_hints(said, ask)
                window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

                while meeting.reveal_next_said():
                    time.sleep(1.2)
                    window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")

        meeting.phase = "after"
        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda, alarm_task)})")
    except Exception as e:
        print(f"column replay failed: {e}", file=sys.stderr)
        try:
            window.evaluate_js(
                f"document.getElementById('heard-lines').innerHTML = {json.dumps(f'<p>Ошибка: {e}</p>')}"
            )
        except Exception:
            pass


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
    loaded_event = threading.Event()
    window.events.loaded += loaded_event.set
    webview.start(_run_replay, (window, loaded_event))
