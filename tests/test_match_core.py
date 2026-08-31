from datetime import datetime, timezone

import pytest

from match_core import MatchResult, _hit_words, compute_idf_weights, extract_number_mentions, match, score_task
from sprint_snapshot import Task, load_sprint


def _task(key, title):
    return Task(
        key=key,
        title=title,
        assignee="Кто-то",
        status="S",
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_extract_number_mentions_finds_digit_sequences():
    assert extract_number_mentions("возьму следующим 412 в работу") == {"412"}


def test_extract_number_mentions_ignores_single_digits():
    assert extract_number_mentions("у меня 1 вопрос") == set()


def test_extract_number_mentions_can_find_several():
    assert extract_number_mentions("сначала 214 потом 201") == {"214", "201"}


def test_compute_idf_weights_gives_full_weight_to_unique_words():
    agenda = [_task("A-1", "Сделки и клиенты"), _task("A-2", "Отчёты и партнёры")]
    idf = compute_idf_weights(agenda)
    assert idf["сделка"] == 1.0
    assert idf["партнёр"] == 1.0


def test_compute_idf_weights_discounts_shared_words():
    agenda = [
        _task("A-1", "Выгрузка в старую систему"),
        _task("A-2", "Выгрузка в новую систему"),
    ]
    idf = compute_idf_weights(agenda)
    assert idf["выгрузка"] == 0.5
    assert idf["система"] == 0.5
    assert idf["старый"] == 1.0


def test_score_task_counts_overlapping_lemmas():
    task = _task("A-1", "Сделки и клиенты")
    idf = {"сделка": 1.0, "клиент": 1.0}
    score, count = score_task(["сделка", "клиент", "погода"], task, idf)
    assert count == 2
    assert score == 2.0


def test_score_task_discounts_stopword_but_does_not_zero_it():
    task = _task("A-1", "Выгрузка там")
    idf = {"выгрузка": 1.0, "там": 1.0}
    score_with_filler, count_with = score_task(["выгрузка", "там"], task, idf)
    score_without_filler, count_without = score_task(["выгрузка"], task, idf)
    assert count_with == 1
    assert count_without == 1
    assert score_without_filler < score_with_filler < score_without_filler + idf["там"]


def test_score_task_stopword_only_overlap_does_not_count_toward_gate():
    # Regression: Rinat's 31 авг real-transcript run found the matcher firing
    # 26 times on a 39-minute daily with only ~7 correct — root cause was
    # stopwords ("и"/"для"/"на") satisfying MIN_OVERLAP_WORDS on their own
    # weight alongside one unrelated word, even though they're discounted in
    # score. A title whose ONLY overlap with the utterance is a stopword must
    # report a significant-word count of 0, not 1.
    task = _task("A-1", "Функционал для клиентов")
    idf = {"функционал": 1.0, "для": 1.0, "клиент": 1.0}
    score, count = score_task(["для", "погода"], task, idf)
    assert count == 0
    assert score > 0  # still discounted into the score, just not into the gate


AGENDA = load_sprint("fixtures/sprint.json")


def test_case1_explicit_number_matches_by_digits_alone():
    results = match("ладно возьму 214 в работу", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10214"]
    assert results[0].reason == "explicit_number"


def test_case2_exact_title_word_match():
    results = match("коллеги, там синхронизация остатков склада ещё не готова", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10299"]
    assert results[0].reason == "title_words"


def test_case3_regression_word_form_mismatch_from_rinats_bug():
    results = match(
        "разобралась наконец с карточками клиентов, там в сделке была путаница",
        AGENDA,
    )
    assert [r.task_key for r in results] == ["NOVA-10201"]
    assert results[0].reason == "title_words"


def test_case3b_second_regression_found_watching_the_full_demo():
    results = match("готова функциональная заявка для поставщиков", AGENDA)
    assert [r.task_key for r in results] == ["NOVA-10230"]
    assert results[0].reason == "title_words"


def test_case4_single_overlapping_word_is_not_enough():
    results = match("короче там ждём поставщиков ещё", AGENDA)
    assert results == []


def test_case12_latin_title_word_recognized_via_cyrillic_phonetic_speech():
    # Real question from the user (31 авг), after discussing anglicisms with
    # Rinat: a Latin-script product name in the title ("Go Market"), spoken
    # and transcribed as Cyrillic phonetics ("гоу маркет"), used to match
    # nothing at all — zero shared lemmas across scripts. "маркет" alone
    # phonetically aliases "market"; combined with a real overlapping
    # Russian word this clears the two-word gate.
    agenda = [_task("T-1", "Интеграция Go Market с личным кабинетом")]
    results = match("по гоу маркету всё готово, интеграция с кабинетом сделана", agenda)
    assert [r.task_key for r in results] == ["T-1"]


def test_case13b_real_youtube_autocaption_data_clean_cyrillic_recognized():
    # Grounded in real data, not another synthetic guess: pulled auto-
    # generated Russian captions for a real podcast episode about code
    # review (Podlodka #251 "Peer Review", youtube.com/watch?v=1bnIA1c3_30,
    # via yt-dlp) to see how real STT output actually mangles this class of
    # term. Real auto-caption output for "код ревью" (clean Cyrillic,
    # phonetic alias for a Latin "Code Review" title) — recognized.
    agenda = [_task("T-1", "Code Review для PR по авторизации")]
    results = match(
        "вообще весь код ревью на за весь процесс койку сетапа недоверие программистом",
        agenda,
    )
    assert [r.task_key for r in results] == ["T-1"]


def test_case13c_real_youtube_autocaption_garbled_stt_stays_silent():
    # Same source (Podlodka #251 real auto-captions). "код ревью" ("code
    # review") sometimes came out as "кот ревью" — STT mis-heard it as "кот"
    # (cat, a real unrelated Russian word), not a clean phonetic rendering.
    # Must stay silent: "guessing" that a real, unrelated word means the
    # anglicism is exactly the false-positive risk the whole feature has to
    # avoid — a single garbled data point isn't grounds to match.
    agenda = [_task("T-1", "Code Review для PR по авторизации")]
    results = match(
        "кот ревью на многопоточности будет смотреть другой такой же junior",
        agenda,
    )
    assert results == []


def test_case13_latin_title_word_still_matches_same_script_speech():
    # Regression guard: the fuzzy Cyrillic-alias path must not break the
    # simple case where the utterance is already in the same script as the
    # title.
    agenda = [_task("T-1", "Интеграция Go Market с личным кабинетом")]
    results = match("по Go Market всё готово", agenda)
    assert [r.task_key for r in results] == ["T-1"]


def test_case11_regression_stopword_plus_one_word_stays_silent():
    # Rinat, 31 авг, real 39-minute daily: matcher fired 26 times, ~7 correct
    # — root cause was "для"/"и"/"на" pairing with a single real word to
    # satisfy MIN_OVERLAP_WORDS=2. "для функционала" only shares "для"
    # (stopword) and "функционал" with NOVA-10230's title — one real word,
    # should stay silent even though the raw score clears MIN_SCORE.
    results = match("для функционала ещё рановато, давайте позже", AGENDA)
    assert results == []


def test_case6_multiple_tasks_in_one_utterance_newest_first():
    results = match(
        "разобралась наконец с карточками клиентов, там в сделке была "
        "путаница, и ещё возьму 214",
        AGENDA,
    )
    assert [r.task_key for r in results] == ["NOVA-10214", "NOVA-10201"]
    assert results[0].reason == "explicit_number"
    assert results[1].reason == "title_words"


def test_case7_pure_filler_utterance_matches_nothing():
    results = match("ну короче вот как бы", AGENDA)
    assert results == []


def test_case8_ambiguous_tie_between_two_similar_tasks():
    results = match("надо доделать выгрузку контактов в систему", AGENDA)
    assert results == []


def test_case9_unrelated_smalltalk_matches_nothing():
    results = match("пойдём после созвона поедим, кто что хочет", AGENDA)
    assert results == []


def test_case10_empty_agenda_raises_instead_of_silently_matching_nothing():
    with pytest.raises(ValueError):
        match("что угодно", [])


def test_hit_words_uses_original_tokens_not_lemmas():
    tokens = ["сделок", "было", "много"]
    lemmas = ["сделка", "быть", "много"]
    title_lemmas = {"сделка", "клиент"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["сделок"]


def test_hit_words_dedups_repeated_lemma():
    tokens = ["сделка", "и", "сделке"]
    lemmas = ["сделка", "и", "сделка"]
    title_lemmas = {"сделка"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["сделка"]


def test_hit_words_preserves_order_of_appearance():
    tokens = ["клиент", "и", "сделка"]
    lemmas = ["клиент", "и", "сделка"]
    title_lemmas = {"сделка", "клиент"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["клиент", "сделка"]


def test_hit_words_no_false_hits_on_non_overlapping_words():
    tokens = ["погода", "сегодня", "хорошая"]
    lemmas = ["погода", "сегодня", "хороший"]
    title_lemmas = {"сделка"}
    assert _hit_words(tokens, lemmas, title_lemmas) == []


def test_match_result_hit_words_for_explicit_number():
    results = match("ладно возьму 214 в работу", AGENDA)
    assert results[0].hit_words == ["214"]


def test_match_result_hit_words_for_title_words():
    results = match("коллеги, там синхронизация остатков склада ещё не готова", AGENDA)
    assert results[0].task_key == "NOVA-10299"
    assert results[0].hit_words == ["синхронизация", "остатков", "склада"]


def test_match_result_hit_words_empty_when_no_match():
    results = match("ну короче вот как бы", AGENDA)
    assert results == []


def test_hit_words_excludes_stopwords_regression_from_real_fixture():
    """Reproduces the real shipped-fixture bug: turn 1 of
    fixtures/sample_daily_transcript.json ("...дубли платежей от
    партнёров.") used to include the preposition "от" in hit_words, which
    then underlined the middle of the unrelated word "готовы" in the
    second-screen UI (unanchored substring match). "от" is a stopword lemma
    and must never appear in hit_words.
    """
    results = match(
        "Отчёты почти готовы, убираем последние дубли платежей от партнёров.",
        AGENDA,
    )
    assert [r.task_key for r in results] == ["NOVA-10214"]
    assert results[0].reason == "title_words"
    assert "от" not in results[0].hit_words
    assert results[0].hit_words == ["отчёты", "убираем", "дубли", "платежей", "партнёров"]


def test_hit_words_excludes_stopword_lemma_directly():
    tokens = ["сделка", "от", "клиент"]
    lemmas = ["сделка", "от", "клиент"]
    title_lemmas = {"сделка", "от", "клиент"}
    assert _hit_words(tokens, lemmas, title_lemmas) == ["сделка", "клиент"]
