import re

from match_core import match
from meeting import Line, Meeting
from sprint_snapshot import Task

_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")
SECONDS_PER_WORD = 0.4


def _utterance_duration(text: str) -> float:
    word_count = len(_WORD_RE.findall(text))
    return max(word_count, 1) * SECONDS_PER_WORD


def _primary_match(results):
    """Pick the result to use for a Line's single `task` field.

    match() sorts by task recency, not confidence, so the first result isn't
    necessarily the most trustworthy one. Prefer an explicit_number match
    (confidence 1.0, the most reliable signal) over a title_words match when
    both are present; otherwise fall back to the first (most recent) result.
    """
    if not results:
        return None
    number_matches = [r for r in results if r.reason == "explicit_number"]
    return number_matches[0] if number_matches else results[0]


def replay(transcript: list[dict], agenda: list[Task]) -> Meeting:
    meeting = Meeting(phase="live", remaining_count=len(agenda))
    t = 0.0
    for turn in transcript:
        t += _utterance_duration(turn["text"])
        results = match(turn["text"], agenda)
        primary = _primary_match(results)
        task_key = primary.task_key if primary else None
        meeting.add_line(Line(t=t, who=turn.get("speaker"), text=turn["text"], task=task_key))
        for r in results:
            meeting.mark_recognized(r.task_key)
    meeting.phase = "after"
    return meeting
