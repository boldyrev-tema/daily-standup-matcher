from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Line:
    t: float
    who: str | None
    text: str
    task: str | None = None
    hit_words: list[str] = field(default_factory=list)


@dataclass
class Meeting:
    phase: Literal["before", "live", "after"] = "before"
    lines: list[Line] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    current: str | None = None
    fresh: str | None = None
    said: list[str] = field(default_factory=list)
    said_n: int = 0
    ask: str | None = None
    elapsed_s: float = 0.0
    remaining_count: int = 0
    _said_lines: list[str] = field(default_factory=list)

    def add_line(self, line: Line) -> None:
        self.lines.append(line)
        self.elapsed_s = line.t

    def mark_recognized(self, key: str) -> None:
        self.current = key
        if key in self.done:
            return
        self.done.append(key)
        self.fresh = key
        self.said = []
        self._said_lines = []
        self.said_n = 0
        self.ask = None
        self.remaining_count = max(0, self.remaining_count - 1)

    def set_hints(self, said_lines: list[str], ask: str | None) -> None:
        self._said_lines = said_lines
        self.said = []
        self.said_n = 0
        self.ask = ask

    def reveal_next_said(self) -> bool:
        if self.said_n < len(self._said_lines):
            self.said.append(self._said_lines[self.said_n])
            self.said_n += 1
            return True
        return False
