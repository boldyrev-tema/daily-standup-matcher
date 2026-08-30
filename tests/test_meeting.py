from meeting import Line, Meeting


def test_add_line_appends_and_advances_elapsed():
    m = Meeting(phase="live", remaining_count=3)
    m.add_line(Line(t=1.2, who="Дарья", text="привет"))
    m.add_line(Line(t=3.5, who="Дарья", text="ещё реплика"))
    assert [l.text for l in m.lines] == ["привет", "ещё реплика"]
    assert m.elapsed_s == 3.5


def test_mark_recognized_first_time_sets_everything():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    assert m.current == "NOVA-1"
    assert m.done == ["NOVA-1"]
    assert m.fresh == "NOVA-1"
    assert m.remaining_count == 1


def test_mark_recognized_again_updates_current_but_not_done_twice():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    m.set_hints(["строка"], "вопрос?")
    m.mark_recognized("NOVA-1")
    assert m.done == ["NOVA-1"]  # not duplicated
    assert m.remaining_count == 1  # not decremented twice
    # second mark of the same task does not wipe hints already shown
    assert m.said == []  # reveal_next_said not called yet, but _said_lines preserved
    assert m.reveal_next_said() is True
    assert m.said == ["строка"]


def test_mark_recognized_new_task_resets_hints():
    m = Meeting(phase="live", remaining_count=2)
    m.mark_recognized("NOVA-1")
    m.set_hints(["строка"], "вопрос?")
    m.reveal_next_said()
    m.mark_recognized("NOVA-2")
    assert m.current == "NOVA-2"
    assert m.said == []
    assert m.said_n == 0
    assert m.ask is None


def test_reveal_next_said_grows_one_at_a_time():
    m = Meeting(phase="live")
    m.set_hints(["a", "b", "c"], None)
    assert m.said == []
    assert m.reveal_next_said() is True
    assert m.said == ["a"]
    assert m.reveal_next_said() is True
    assert m.said == ["a", "b"]
    assert m.reveal_next_said() is True
    assert m.said == ["a", "b", "c"]
    assert m.reveal_next_said() is False
    assert m.said == ["a", "b", "c"]


def test_line_hit_words_defaults_to_empty_list():
    line = Line(t=1.0, who="Дарья", text="привет")
    assert line.hit_words == []


def test_line_hit_words_can_be_set():
    line = Line(t=1.0, who="Дарья", text="возьму 214 в работу", task="NOVA-10214", hit_words=["214"])
    assert line.hit_words == ["214"]
