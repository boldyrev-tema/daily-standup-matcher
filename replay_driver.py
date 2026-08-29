import re

from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import Task

_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")
SECONDS_PER_WORD = 0.4


def _utterance_duration(text: str) -> float:
    word_count = len(_WORD_RE.findall(text))
    return max(word_count, 1) * SECONDS_PER_WORD


def replay(transcript: list[dict], agenda: list[Task]) -> Meeting:
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    t = 0.0
    for turn in transcript:
        t += _utterance_duration(turn["text"])
        results = match(turn["text"], agenda)
        task_key = results[0].task_key if results else None
        meeting.add_line(Line(t=t, who=turn.get("speaker"), text=turn["text"], task=task_key))
        if results:
            meeting.mark_recognized(results[0].task_key)
    meeting.phase = "after"
    return meeting
