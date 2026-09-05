import re
from dataclasses import dataclass, field

from lemmatize import lemmatize
from sprint_snapshot import Task
from stopwords import stopword_discount
from translit import is_phonetic_match

_NUMBER_RE = re.compile(r"\d{2,}")
_WORD_RE = re.compile(r"[а-яА-ЯёЁa-zA-Z]+")
_LATIN_RE = re.compile(r"^[a-z]+$")
_CYRILLIC_RE = re.compile(r"^[а-яё]+$")

MIN_OVERLAP_WORDS = 2
MIN_SCORE = 0.5
REQUIRED_MARGIN = 0.3
PHRASE_WINDOW = 2


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


def _latin_alias_overlap(utterance_tokens: list[str], title_lemmas: set[str]) -> set[str]:
    """Latin-script title words (e.g. a product name like "Go Market") that a
    Cyrillic phonetic rendering in the utterance ("гоу маркет") echoes. Title
    text in Latin script passes through lemmatize() unchanged (pymorphy3 only
    knows Cyrillic), so a Latin title word is already a valid "lemma" — this
    just adds a second way to reach it, on top of the exact-string path that
    already works when the utterance is ALSO in Latin script.
    """
    latin_title_words = {w for w in title_lemmas if _LATIN_RE.match(w)}
    if not latin_title_words:
        return set()
    cyr_tokens = [t for t in utterance_tokens if _CYRILLIC_RE.match(t)]
    hits = set()
    for latin_word in latin_title_words:
        if any(is_phonetic_match(latin_word, tok) for tok in cyr_tokens):
            hits.add(latin_word)
    return hits


def _has_phrase_window(utterance_lemmas: list[str], significant_lemmas: set[str]) -> bool:
    """True if at least MIN_OVERLAP_WORDS DISTINCT lemmas from
    `significant_lemmas` occur within PHRASE_WINDOW positions of each other
    in `utterance_lemmas` — i.e. were actually spoken close together as a
    phrase, not just present somewhere in a long, unrelated utterance.

    Real false positive (Rinat, 5 сен, live testing): task title "Мои дела"
    matched an utterance where "мой" (from "по-моему") and "дело" (from "на
    самом деле") each appeared, far apart, in an unrelated sentence — two
    common words coincidentally overlapping the title, not the task
    actually being discussed. A title's own words are adjacent by
    construction, so requiring the utterance's overlapping words to cluster
    the same way filters this out while keeping real mentions ("готова
    функциональная заявка для поставщиков" — заявка/поставщик 2 positions
    apart — still passes at PHRASE_WINDOW=2, verified against the real
    fixture titles this project already ships).
    """
    positions = [i for i, lemma in enumerate(utterance_lemmas) if lemma in significant_lemmas]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            if positions[j] - positions[i] > PHRASE_WINDOW:
                continue
            if utterance_lemmas[positions[i]] != utterance_lemmas[positions[j]]:
                return True
    return False


def score_task(
    utterance_lemmas: list[str],
    task: Task,
    idf: dict[str, float],
    utterance_tokens: list[str] | None = None,
) -> tuple[float, int]:
    title_lemmas = set(lemmatize(_tokenize(task.title)))
    direct_overlap = set(utterance_lemmas) & title_lemmas
    alias_overlap = _latin_alias_overlap(utterance_tokens, title_lemmas) if utterance_tokens else set()
    overlap = direct_overlap | alias_overlap
    score = sum(idf.get(lemma, 0.0) * stopword_discount(lemma) for lemma in overlap)
    # Only count words that aren't stopwords toward MIN_OVERLAP_WORDS below —
    # a shared "и"/"для"/"на" still nudges the score (discounted, not zeroed)
    # but must not by itself satisfy "at least two overlapping words", or a
    # single real content word plus one shared filler word passes the gate.
    # Real false positives on a full transcript (Rinat, 31 авг): matched on
    # "и"/"для"/"на" pairing with one unrelated word each time.
    significant_direct = {lemma for lemma in direct_overlap if stopword_discount(lemma) >= 1.0}
    significant_alias = {lemma for lemma in alias_overlap if stopword_discount(lemma) >= 1.0}
    # Phrase-window check only applies to direct lemma hits, which have real
    # utterance positions — alias hits (_latin_alias_overlap, e.g. Latin
    # product names spoken as Cyrillic phonetics) have no comparable
    # position and are already a narrower, deliberate signal on their own
    # (see that function's docstring); requiring 2+ direct hits to cluster
    # only kicks in when direct hits alone would otherwise satisfy the gate.
    if len(significant_direct) >= MIN_OVERLAP_WORDS and not _has_phrase_window(
        utterance_lemmas, significant_direct
    ):
        significant_direct = set()
    significant_overlap = significant_direct | significant_alias
    return score, len(significant_overlap)


def _scored_candidates(
    lemmas: list[str], tokens: list[str], candidates: list[Task], idf: dict[str, float]
) -> list[tuple[Task, float]]:
    scored: list[tuple[Task, float]] = []
    for task in candidates:
        score, overlap_count = score_task(lemmas, task, idf, tokens)
        if overlap_count >= MIN_OVERLAP_WORDS and score > MIN_SCORE:
            scored.append((task, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _hit_words(tokens: list[str], lemmas: list[str], title_lemmas: set[str]) -> list[str]:
    seen: set[str] = set()
    hits: list[str] = []
    for token, lemma in zip(tokens, lemmas):
        if lemma in title_lemmas and lemma not in seen and stopword_discount(lemma) >= 1.0:
            seen.add(lemma)
            hits.append(token)
    return hits


@dataclass(frozen=True)
class MatchResult:
    task_key: str
    confidence: float
    reason: str
    hit_words: list[str] = field(default_factory=list, hash=False)


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
    scored = _scored_candidates(utterance_lemmas, tokens, remaining, idf)

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


def ambiguous_candidates(utterance: str, agenda: list[Task]) -> list[Task]:
    """Tasks match() stayed silent on because they were within
    REQUIRED_MARGIN of each other despite each clearing MIN_OVERLAP_WORDS and
    MIN_SCORE alone (see match()'s margin gate). Lets a caller retry
    disambiguation with more context — see resolve_pending — restricted to
    just this set, so a merged retry can only pick a winner among real
    contenders, never surface a task that wasn't already one.
    """
    if not agenda:
        return []
    idf = compute_idf_weights(agenda)
    tokens = _tokenize(utterance)
    lemmas = lemmatize(tokens)
    scored = _scored_candidates(lemmas, tokens, agenda, idf)
    if len(scored) < 2:
        return []
    top_score = scored[0][1]
    tied = [task for task, score in scored if top_score - score < REQUIRED_MARGIN]
    return tied if len(tied) >= 2 else []


def resolve_pending(
    pending_text: str, pending_candidates: list[Task], current_text: str
) -> MatchResult | None:
    """Retry an utterance match() left ambiguous, using the very next
    utterance as extra context — Rinat, 2 сен: a genuine single-utterance tie
    (two "сделки" tasks, SITE-12160/SITE-12170) resolved on the immediately
    following line, so on screen the miss was barely noticeable; this closes
    that gap outright instead of leaving the first line's task permanently
    unlabeled. Restricted to pending_candidates (the tie ambiguous_candidates
    already found) so the merged retry can only choose among real
    contenders, never invent a match against the full agenda.
    """
    combined = f"{pending_text} {current_text}"
    results = match(combined, pending_candidates)
    return results[0] if len(results) == 1 else None
