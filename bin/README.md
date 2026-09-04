# SystemAudioDump

Not written for this project — a macOS system-audio capture binary from
[cheating-daddy](https://github.com/sohzm/cheating-daddy) by
[sohzm](https://github.com/sohzm) (Soham), licensed under the
[GNU GPLv3](./LICENSE) (see that file in this same directory, or the
canonical text at https://www.gnu.org/licenses/gpl-3.0.txt).

Bundled here unmodified, straight from
`cheating-daddy/src/assets/SystemAudioDump` in the upstream repository, so
`live_audio.py`'s system-audio channel ("Собеседник" — the other side of a
call) works without anyone needing a separate manual copy or an
`export SYSTEM_AUDIO_DUMP_PATH=...` step. Source for this exact binary:
https://github.com/sohzm/cheating-daddy/tree/master/src/assets

Without it (e.g. on Linux/Windows, where it doesn't apply at all), only the
microphone channel ("Ты") works — see `live_audio.py`'s own comment for the
graceful-degradation logic.
