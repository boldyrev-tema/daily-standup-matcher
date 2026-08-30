import re
from dataclasses import dataclass, field

from lemmatize import lemmatize
from sprint_snapshot import Task
from stopwords import stopword_discount

_NUMBER_RE = re.compile(r"\d{2,}")
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")

MIN_OVERLAP_WORDS = 2
MIN_SCORE = 0.5
REQUIRED_MARGIN = 0.3


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _key_digits(key: str) -> str:
    return "".join(ch for ch in key if ch.isdigit())


def extract_number_mentions(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def compute_idf_weights(agenda: list[Task]) -> dict[str, float]:
    doc_count: dict[str, int] = {}
    for task in agenda:
        lemmas = set(lemmatize(_tokenize(task.title)))
        for lemma in lemmas:
            doc_count[lemma] = doc_count.get(lemma, 0) + 1
    return {lemma: 1 / count for lemma, count in doc_count.items()}


def score_task(
    utterance_lemmas: list[str], task: Task, idf: dict[str, float]
) -> tuple[float, int]:
    title_lemmas = set(lemmatize(_tokenize(task.title)))
    overlap = set(utterance_lemmas) & title_lemmas
    score = sum(idf.get(lemma, 0.0) * stopword_discount(lemma) for lemma in overlap)
    return score, len(overlap)


def _hit_words(tokens: list[str], lemmas: list[str], title_lemmas: set[str]) -> list[str]:
    seen: set[str] = set()
    hits: list[str] = []
    for token, lemma in zip(tokens, lemmas):
        if lemma in title_lemmas and lemma not in seen:
            seen.add(lemma)
            hits.append(token)
    return hits


@dataclass(frozen=True)
class MatchResult:
    task_key: str
    confidence: float
    reason: str
    hit_words: list[str] = field(default_factory=list)


def match(utterance: str, agenda: list[Task]) -> list[MatchResult]:
    if not agenda:
        raise ValueError("agenda must not be empty")

    idf = compute_idf_weights(agenda)
    tokens = _tokenize(utterance)
    utterance_lemmas = lemmatize(tokens)
    mentioned_numbers = extract_number_mentions(utterance)

    results: list[MatchResult] = []
    matched_keys: set[str] = set()

    for task in agenda:
        key_digits = _key_digits(task.key)
        for number in mentioned_numbers:
            is_full_match = number == key_digits
            is_suffix_match = len(number) >= 3 and key_digits.endswith(number)
            if is_full_match or is_suffix_match:
                results.append(MatchResult(task.key, 1.0, "explicit_number", hit_words=[number]))
                matched_keys.add(task.key)
                break

    remaining = [t for t in agenda if t.key not in matched_keys]
    scored: list[tuple[Task, float]] = []
    for task in remaining:
        score, overlap_count = score_task(utterance_lemmas, task, idf)
        if overlap_count >= MIN_OVERLAP_WORDS and score > MIN_SCORE:
            scored.append((task, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    if scored:
        top_task, top_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
        if top_score - runner_up_score >= REQUIRED_MARGIN:
            title_lemmas = set(lemmatize(_tokenize(top_task.title)))
            hit_words = _hit_words(tokens, utterance_lemmas, title_lemmas)
            results.append(MatchResult(top_task.key, top_score, "title_words", hit_words=hit_words))

    task_by_key = {t.key: t for t in agenda}
    results.sort(key=lambda r: task_by_key[r.task_key].updated_at, reverse=True)
    return results
