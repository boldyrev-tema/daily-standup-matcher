from translit import KNOWN_IT_TERMS, translit, is_phonetic_match


def test_translit_known_it_loanwords():
    # Real, established Cyrillic spellings for common tech/IT loanwords
    # (checked against public IT-slang glossaries, not invented) — a naive
    # letter-substitution transliterator won't be exact on all of these
    # (English spelling is irregular), this just documents where it lands.
    assert translit("sprint") == "спринт"
    assert translit("commit") == "коммит"
    assert translit("market") == "маркет"
    assert translit("production") == "продакшн"


def test_known_it_terms_override_the_letter_rules():
    # The letter rules alone get "backend" wrong ("бакенд", not the real
    # "бэкенд") — the curated KNOWN_IT_TERMS dict is checked first and wins.
    assert KNOWN_IT_TERMS["backend"] == "бэкенд"
    assert translit("backend") == "бэкенд"
    assert translit("BACKEND") == "бэкенд"  # case-insensitive


def test_known_it_terms_not_in_dict_still_falls_back_to_rules():
    assert "market" not in KNOWN_IT_TERMS
    assert translit("market") == "маркет"  # rules alone already get this right


def test_is_phonetic_match_true_for_close_transliteration():
    # "backend" transliterates to "бакенд", not the established "бэкенд" —
    # one character off. is_phonetic_match must tolerate this, since exact
    # string equality is exactly what the naive transliterator can't promise.
    assert is_phonetic_match("backend", "бэкенд") is True


def test_is_phonetic_match_true_for_go_market_example():
    # The real case that started this: a Latin task title ("Go Market")
    # spoken/transcribed as Cyrillic phonetics.
    assert is_phonetic_match("go", "го") is True
    assert is_phonetic_match("market", "маркет") is True


def test_is_phonetic_match_false_for_unrelated_words():
    assert is_phonetic_match("market", "клиент") is False
    assert is_phonetic_match("backend", "погода") is False


def test_is_phonetic_match_false_for_too_short_words():
    # Short words (2-3 letters) are too ambiguous to fuzzy-match safely —
    # "go" against an unrelated short Cyrillic word could coincidentally
    # score high similarity by pure chance.
    assert is_phonetic_match("go", "то") is False
