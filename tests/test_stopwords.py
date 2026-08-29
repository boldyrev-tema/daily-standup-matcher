from stopwords import STOPWORDS, stopword_discount


def test_known_stopword_gets_third_weight():
    assert "ну" in STOPWORDS
    assert stopword_discount("ну") == 1 / 3


def test_content_word_gets_full_weight():
    assert "сделка" not in STOPWORDS
    assert stopword_discount("сделка") == 1.0


def test_stopword_list_is_reasonably_sized():
    assert len(STOPWORDS) >= 15
