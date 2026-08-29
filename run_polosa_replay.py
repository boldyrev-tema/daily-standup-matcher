import json
import re
import time

import webview

from agenda import build_agenda
from credentials import load_credential
from facts import build_facts
from hints import get_hints
from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import load_sprint

TEAM = ["Дарья Ковалёва", "Максим Орлов", "Полина Реброва", "Игорь Сафин"]
GROQ_KEY_PATH = "~/.credentials/groq_api_key.env"
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")


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


def _run_replay(window):
    time.sleep(3)  # let the window/page finish loading before the first push

    tasks = load_sprint("fixtures/sprint.json")
    agenda = build_agenda(tasks, TEAM)
    with open("fixtures/sample_daily_transcript.json", encoding="utf-8") as f:
        transcript = json.load(f)
    api_key = load_credential(GROQ_KEY_PATH, "GROQ_API_KEY")

    meeting = Meeting(phase="live", remaining_count=len(agenda))
    t = 0.0
    for turn in transcript:
        word_count = len(_WORD_RE.findall(turn["text"]))
        pause = max(word_count, 1) * 0.4
        time.sleep(pause)
        t += pause

        results = match(turn["text"], agenda)
        task_key = results[0].task_key if results else None
        meeting.add_line(Line(t=t, who=turn["speaker"], text=turn["text"], task=task_key))

        if results:
            meeting.mark_recognized(results[0].task_key)
            task = next(x for x in agenda if x.key == results[0].task_key)
            said, ask = get_hints(meeting.lines, task, api_key)
            # polosa.html's reduced view never reads meeting.said/said_n (see
            # design spec's "Полоса" section) — the progressive one-at-a-time
            # reveal loop is only meaningful for a future full-view placement.
            # Setting the hints once keeps the data canonical on Meeting
            # without pushing an unchanged payload to the browser on a sleep
            # loop that has zero visible effect here.
            meeting.set_hints(said, ask)

        window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")

    meeting.phase = "after"
    window.evaluate_js(f"renderMeeting({_state_json(meeting, agenda)})")


if __name__ == "__main__":
    window = webview.create_window(
        "Полоса", "polosa.html", width=1200, height=200, frameless=True, on_top=True
    )
    webview.start(_run_replay, window)
