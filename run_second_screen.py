import json
import re
import sys
import time

import webview

from agenda import build_agenda, pick_alarm
from credentials import load_credential
from facts import agenda_row, build_facts
from hints import get_hints
from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import load_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
GROQ_KEY_PATH = "~/.credentials/groq_api_key.env"
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


def _run_replay(window):
    try:
        time.sleep(3)  # let the window/page finish loading before the first push

        tasks = load_sprint("fixtures/sprint.json")
        agenda = build_agenda(tasks, TEAM)
        alarm_task = pick_alarm(agenda)
        with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
            transcript = json.load(f)
        api_key = load_credential(GROQ_KEY_PATH, "GROQ_API_KEY")

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
        print(f"second screen replay failed: {e}", file=sys.stderr)
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
    webview.start(_run_replay, window)
