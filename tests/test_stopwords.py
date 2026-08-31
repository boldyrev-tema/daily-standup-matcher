from stopwords import STOPWORDS, stopword_discount


def test_known_stopword_gets_third_weight():
    assert "ну" in STOPWORDS
    assert stopword_discount("ну") == 1 / 3


def test_content_word_gets_full_weight():
    assert "сделка" not in STOPWORDS
    assert stopword_discount("сделка") == 1.0


def test_stopword_list_is_reasonably_sized():
    assert len(STOPWORDS) >= 15


def test_common_function_words_are_covered():
    # Found missing on a real-transcript validation run (29 aug 2026): "и" + "с" alone
    # passed the >=2-word overlap gate in match_core.match() and produced a false
    # positive, because neither was discounted as a stopword.
    for word in ("и", "с", "на", "не", "что", "но", "за", "у", "к", "по", "от", "из"):
        assert word in STOPWORDS, f"{word!r} should be a stopword"


def test_words_rinat_named_as_missing_are_covered():
    # Rinat, 31 авг, real 39-minute daily run: named "под"/"явно" specifically
    # as words the reconstructed stopword list was still missing.
    for word in ("под", "явно"):
        assert word in STOPWORDS, f"{word!r} should be a stopword"
