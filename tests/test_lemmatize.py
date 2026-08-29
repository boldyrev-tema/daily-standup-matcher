from lemmatize import lemmatize


def test_lemmatize_collapses_grammatical_case():
    assert lemmatize(["сделок"]) == ["сделка"]
    assert lemmatize(["сделки"]) == ["сделка"]
    assert lemmatize(["сделке"]) == ["сделка"]


def test_lemmatize_collapses_task_word_forms():
    assert lemmatize(["задач"]) == ["задача"]
    assert lemmatize(["задачу"]) == ["задача"]


def test_lemmatize_keeps_distinct_derivational_forms_distinct():
    assert lemmatize(["функционал"]) == ["функционал"]
    assert lemmatize(["функциональная"]) == ["функциональный"]


def test_lemmatize_preserves_token_order_and_count():
    assert lemmatize(["карточками", "клиентов"]) == ["карточка", "клиент"]
