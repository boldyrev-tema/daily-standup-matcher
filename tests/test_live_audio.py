from datetime import datetime, timezone

import numpy as np

from live_audio import build_additional_vocab, pick_working_input_device
from sprint_snapshot import Task

DEVICES = [
    {"name": "LEN T27p-10", "max_input_channels": 0},
    {"name": "AirPods Pro (Tema)", "max_input_channels": 1},
    {"name": "Микрофон MacBook Air", "max_input_channels": 1},
]


def _samples(peak: int) -> np.ndarray:
    arr = np.zeros((10,), dtype=np.int16)
    if peak:
        arr[0] = peak
    return arr


def test_picks_default_when_it_has_real_signal():
    def record(idx):
        return _samples(300)

    picked = pick_working_input_device(devices=DEVICES, default_index=1, record=record)
    assert picked == 1


def test_falls_back_to_working_device_when_default_is_silent():
    # Reproduces the 2 сен live test: default input was AirPods Pro, which
    # returned exact-zero samples (Bluetooth mic never negotiated HFP mode),
    # while the built-in mic captured real speech fine.
    def record(idx):
        return _samples(0) if idx == 1 else _samples(300)

    picked = pick_working_input_device(devices=DEVICES, default_index=1, record=record)
    assert picked == 2


def test_never_probes_an_output_only_device():
    def record(idx):
        assert idx != 0, "output-only device (max_input_channels=0) must not be probed"
        return _samples(0) if idx == 1 else _samples(300)

    picked = pick_working_input_device(devices=DEVICES, default_index=1, record=record)
    assert picked == 2


def test_skips_device_that_raises_during_probe():
    def record(idx):
        if idx == 1:
            raise RuntimeError("device busy")
        return _samples(300)

    picked = pick_working_input_device(devices=DEVICES, default_index=1, record=record)
    assert picked == 2


def test_falls_back_to_default_when_every_device_is_silent():
    def record(idx):
        return _samples(0)

    picked = pick_working_input_device(devices=DEVICES, default_index=1, record=record)
    assert picked == 1


def _task(title: str) -> Task:
    return Task(
        key="NOVA-1", title=title, assignee="Кто-то",
        status="В работе", updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )


def test_build_additional_vocab_extracts_words_from_titles():
    agenda = [_task("Сделки — объединяем карточки клиентов")]
    vocab = build_additional_vocab(agenda)
    assert {"content": "Сделки"} in vocab
    assert {"content": "объединяем"} in vocab
    assert {"content": "карточки"} in vocab
    assert {"content": "клиентов"} in vocab


def test_build_additional_vocab_drops_short_and_stop_words():
    agenda = [_task("Выгрузка в старую систему для отчётов")]
    vocab = build_additional_vocab(agenda)
    contents = {v["content"].lower() for v in vocab}
    assert "в" not in contents
    assert "для" not in contents  # stopword
    # "старую" (6 letters) kept, but nothing 3 letters or shorter survives
    assert all(len(c) > 3 for c in contents)


def test_build_additional_vocab_dedupes_case_insensitively_keeping_first_seen():
    agenda = [_task("Сделки готовы"), _task("сделки закрыты")]
    vocab = build_additional_vocab(agenda)
    matches = [v for v in vocab if v["content"].lower() == "сделки"]
    assert matches == [{"content": "Сделки"}]


def test_build_additional_vocab_empty_agenda():
    assert build_additional_vocab([]) == []
