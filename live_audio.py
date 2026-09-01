import asyncio
import audioop
import os
import queue
import subprocess
import threading
from typing import Callable

import numpy as np
import sounddevice as sd
from speechmatics.rt import (
    AsyncClient,
    AudioEncoding,
    AudioFormat,
    ConversationConfig,
    ServerMessageType,
    TranscriptResult,
    TranscriptionConfig,
)

# Adapted from the proven PoC at ~/Desktop/Rinat Work/live_copilot_poc/
# live_copilot_poc.py (mic + system-audio -> Speechmatics streaming, tested
# live 21 авг) — only the audio-capture/streaming-STT plumbing is reused
# here. That PoC's LLM/vision suggestion layer isn't: this project already
# has its own matcher/hints pipeline (match_core.py/hints.py) that consumes
# finalized (speaker, text) turns exactly like this module produces them.
#
# System audio ("Собеседник", the other side of the call) needs the
# SystemAudioDump binary from the cheating-daddy project — NOT bundled here
# (this repo is public; that binary's license isn't ours to redistribute).
# Point SYSTEM_AUDIO_DUMP_PATH at a local copy to enable it; without it, only
# the microphone channel ("Ты") runs, same graceful degradation as the PoC.

MIC_SAMPLE_RATE = 16000
SYS_SAMPLE_RATE = 24000  # SystemAudioDump's native output rate
SYSTEM_AUDIO_DUMP_PATH = os.environ.get("SYSTEM_AUDIO_DUMP_PATH", "")


def _pick_mic_device() -> int | None:
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and "macbook" in dev["name"].lower():
            return i
    return None


class LiveAudioSession:
    """Streams microphone ("Ты") + optional system audio ("Собеседник") to
    Speechmatics and calls on_turn(speaker, text) once per finalized
    utterance (Speechmatics' END_OF_UTTERANCE, a real pause-based boundary —
    not per-word, see run_channel_session in the source PoC). Runs its own
    asyncio loop in a background thread; start() returns immediately.
    """

    def __init__(self, api_key: str, on_turn: Callable[[str, str], None]):
        self.api_key = api_key
        self.on_turn = on_turn
        self.running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._mic_queue: asyncio.Queue | None = None
        self._sys_queue: asyncio.Queue | None = None

    def start(self) -> None:
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()
        self._ready.wait(timeout=10)
        threading.Thread(target=self._mic_loop, daemon=True).start()
        threading.Thread(target=self._system_audio_loop, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        if self._loop is not None:
            if self._mic_queue is not None:
                self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, None)
            if self._sys_queue is not None:
                self._loop.call_soon_threadsafe(self._sys_queue.put_nowait, None)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        finally:
            loop.close()

    async def _main(self) -> None:
        self._mic_queue = asyncio.Queue()
        self._sys_queue = asyncio.Queue()
        self._ready.set()
        await asyncio.gather(
            self._run_channel_session("Ты", self._mic_queue),
            self._run_channel_session("Собеседник", self._sys_queue),
        )

    async def _run_channel_session(self, speaker: str, audio_queue: asyncio.Queue) -> None:
        audio_format = AudioFormat(encoding=AudioEncoding.PCM_S16LE, sample_rate=MIC_SAMPLE_RATE, chunk_size=3200)
        transcription_config = TranscriptionConfig(
            language="ru",
            max_delay=0.8,
            enable_partials=True,
            conversation_config=ConversationConfig(end_of_utterance_silence_trigger=0.5),
        )
        while self.running:
            buffer_parts: list[str] = []
            try:
                async with AsyncClient(api_key=self.api_key) as client:

                    @client.on(ServerMessageType.ADD_TRANSCRIPT)
                    def on_final(msg):
                        text = TranscriptResult.from_message(msg).metadata.transcript
                        if text:
                            buffer_parts.append(text)

                    @client.on(ServerMessageType.END_OF_UTTERANCE)
                    def on_end_of_utterance(msg):
                        full_text = "".join(buffer_parts).strip()
                        buffer_parts.clear()
                        if full_text:
                            self.on_turn(speaker, full_text)

                    await client.start_session(transcription_config=transcription_config, audio_format=audio_format)
                    while self.running:
                        chunk = await audio_queue.get()
                        if chunk is None:
                            return
                        await client.send_audio(chunk)
            except Exception as e:
                print(f"Speechmatics session ({speaker}) failed, переподключаюсь через 2с: {e}")
                await asyncio.sleep(2)

    def _mic_loop(self) -> None:
        self._ready.wait()
        q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            q.put(bytes(indata))

        with sd.InputStream(
            samplerate=MIC_SAMPLE_RATE, channels=1, dtype="int16", callback=callback, device=_pick_mic_device()
        ):
            while self.running:
                try:
                    chunk = q.get(timeout=1)
                except queue.Empty:
                    continue
                self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, chunk)
        self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, None)

    def _system_audio_loop(self) -> None:
        if not SYSTEM_AUDIO_DUMP_PATH or not os.path.exists(SYSTEM_AUDIO_DUMP_PATH):
            print(
                'SystemAudioDump не найден (задай SYSTEM_AUDIO_DUMP_PATH) — канал '
                '"Собеседник" пропущен, работает только микрофон'
            )
            return
        self._ready.wait()
        proc = subprocess.Popen([SYSTEM_AUDIO_DUMP_PATH], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        bytes_per_frame = 2 * 2  # int16 * 2 channels (SystemAudioDump выдаёт стерео)
        ratecv_state = None
        buf = b""
        try:
            while self.running:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                usable = len(buf) - (len(buf) % bytes_per_frame)
                if usable == 0:
                    continue
                frame_bytes, buf = buf[:usable], buf[usable:]
                stereo = np.frombuffer(frame_bytes, dtype=np.int16).reshape(-1, 2)
                mono = stereo.mean(axis=1).astype(np.int16).tobytes()
                resampled, ratecv_state = audioop.ratecv(
                    mono, 2, 1, SYS_SAMPLE_RATE, MIC_SAMPLE_RATE, ratecv_state
                )
                self._loop.call_soon_threadsafe(self._sys_queue.put_nowait, resampled)
        finally:
            self._loop.call_soon_threadsafe(self._sys_queue.put_nowait, None)
            proc.terminate()
