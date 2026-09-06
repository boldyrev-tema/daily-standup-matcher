import platform
import subprocess
from datetime import datetime, timezone

import numpy as np

import asyncio
import time

from live_audio import (
    LiveAudioSession,
    SYSTEM_AUDIO_DUMP_PATH,
    _notify_queue_done,
    build_additional_vocab,
    check_binary_arch,
    pick_working_input_device,
)
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


def test_check_binary_arch_returns_none_for_the_committed_universal_binary():
    # Real fixture, not synthetic — bin/SystemAudioDump is committed as a
    # universal (arm64+x86_64) binary specifically so this never trips (see
    # its own docstring for the real bug this guards, found live 5 сен on
    # Rinat's Intel Mac against an arm64-only build).
    assert check_binary_arch("bin/SystemAudioDump") is None


def test_check_binary_arch_returns_message_for_a_mismatched_arch(tmp_path):
    # /bin/ls is a real universal binary but only ships x86_64 + arm64e
    # slices — never plain "arm64", which is what platform.machine() (and
    # our own compiled binary) actually report on Apple Silicon. So on
    # EITHER host arch, at least one of its slices is guaranteed to not
    # match platform.machine() — pick whichever one that is.
    mismatched_arch = "arm64e" if platform.machine() == "x86_64" else "x86_64"
    thin_path = tmp_path / "thin_binary"
    subprocess.run(["lipo", "-thin", mismatched_arch, "/bin/ls", "-output", str(thin_path)], check=True)

    message = check_binary_arch(str(thin_path))

    assert message is not None
    assert mismatched_arch in message
    assert platform.machine() in message


def test_check_binary_arch_returns_none_when_lipo_is_unavailable(monkeypatch, tmp_path):
    # Fail permissive — a missing dev tool must never block real usage of a
    # binary that's actually fine.
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no lipo")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_binary_arch("bin/SystemAudioDump") is None


def test_stop_terminates_the_real_system_audio_subprocess():
    # Real bug, caught live (5 сен): _system_audio_loop's own
    # `while self.running: proc.stdout.read(4096)` can't notice stop() was
    # called while that read() is blocked waiting for the next chunk — its
    # `finally: proc.terminate()` never runs until more data happens to
    # arrive, leaving the real OS subprocess orphaned once the parent
    # process exits. Three such orphans had accumulated across closed
    # sessions on the same machine, competing for the same ScreenCaptureKit
    # capture. stop() itself must guarantee the subprocess is gone,
    # independent of whether the reading thread ever wakes up.
    #
    # Exercises the real fix against the real committed binary (not a mock
    # subprocess) — starts it exactly the way _system_audio_loop does,
    # assigns it to _sys_proc the same way, then calls the real stop().
    session = LiveAudioSession(api_key="fake", on_turn=lambda speaker, text: None)
    proc = subprocess.Popen([SYSTEM_AUDIO_DUMP_PATH], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    session._sys_proc = proc
    assert proc.poll() is None  # actually running, not dead on arrival

    session.stop()
    time.sleep(0.5)

    assert proc.poll() is not None  # real process actually terminated


def test_notify_queue_done_swallows_error_on_a_really_closed_loop():
    # Real bug (5 сен): stop() already pushes this same sentinel into both
    # queues synchronously — by the time a worker thread's own reading loop
    # notices and reaches its redundant final push, the event loop may have
    # already closed, and call_soon_threadsafe on a closed loop raises
    # RuntimeError. Uses a real asyncio loop, actually closed, not a mock —
    # the real failure mode this guards against.
    loop = asyncio.new_event_loop()
    q = asyncio.Queue()
    loop.close()

    _notify_queue_done(loop, q)  # must not raise


def test_notify_queue_done_pushes_the_sentinel_on_a_live_loop():
    loop = asyncio.new_event_loop()
    q = asyncio.Queue()
    try:
        _notify_queue_done(loop, q)
        loop.run_until_complete(asyncio.sleep(0))  # let call_soon_threadsafe's callback run
        assert q.get_nowait() is None
    finally:
        loop.close()
