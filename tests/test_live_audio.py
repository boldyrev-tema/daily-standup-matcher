import numpy as np

from live_audio import pick_working_input_device

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
