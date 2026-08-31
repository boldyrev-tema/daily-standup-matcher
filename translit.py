import difflib

# Orthographic (spelling-based, not phonetic-dictionary-based) approximation
# of English-to-Russian practical transcription — simplified from the rules
# at ru.wikipedia.org/wiki/Англо-русская_практическая_транскрипция. We only
# have written title text, not pronunciation, so this is inherently
# approximate (calibrated to ~65% exact matches against real IT-loanword
# spellings like "спринт"/"коммит"/"продакшн" — see tests/test_translit.py).
# is_phonetic_match() below is deliberately fuzzy so the remaining ~35% of
# near-misses ("бакенд" vs the real "бэкенд") still count.
_MULTI = [
    ("tion", "шн"), ("sion", "жн"), ("ture", "чер"),
    ("dge", "дж"), ("ge$", "дж"),
    ("ew", "ью"),
    ("th", "т"), ("ch", "ч"), ("sh", "ш"), ("ph", "ф"), ("ck", "к"), ("ng", "нг"),
    ("ee", "и"), ("ea", "и"), ("oo", "у"),
    ("ay", "эй"), ("ai", "эй"), ("oy", "ой"), ("oi", "ой"),
    ("ow", "оу"), ("qu", "кв"),
]
_SINGLE = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х",
    "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "к", "r": "р", "s": "с", "t": "т", "u": "а", "v": "в", "w": "в", "x": "кс",
    "y": "й", "z": "з",
}


def translit(word: str) -> str:
    word = word.lower()
    # Drop a silent word-final "e" after a consonant (magic-e pattern), but
    # only for words of 4+ letters so we don't eat short real vowel-e words.
    if len(word) >= 4 and word.endswith("e") and word[-2] not in "aeiou":
        word = word[:-1]
    out = []
    i, n = 0, len(word)
    while i < n:
        matched = False
        for pat, rep in _MULTI:
            if pat.endswith("$"):
                bare = pat[:-1]
                if i + len(bare) == n and word.startswith(bare, i):
                    out.append(rep)
                    i += len(bare)
                    matched = True
                    break
            elif word.startswith(pat, i):
                out.append(rep)
                i += len(pat)
                matched = True
                break
        if not matched:
            out.append(_SINGLE.get(word[i], word[i]))
            i += 1
    return "".join(out)


def is_phonetic_match(latin_word: str, cyr_word: str, threshold: float = 0.8) -> bool:
    """Whether cyr_word looks like a Cyrillic phonetic rendering of latin_word.

    Short words (<=3 letters) require an exact transliteration match — with
    so few characters, a "close" fuzzy match is often just coincidence.
    """
    latin_word = latin_word.lower()
    cyr_word = cyr_word.lower()
    expected = translit(latin_word)
    if len(latin_word) <= 3:
        return expected == cyr_word
    ratio = difflib.SequenceMatcher(None, expected, cyr_word).ratio()
    return ratio >= threshold
