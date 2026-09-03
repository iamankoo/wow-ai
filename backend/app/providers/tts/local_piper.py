"""LocalPiperTTSProvider - real text-to-speech using Piper (a fast,
self-hosted neural TTS engine, ONNX-based), with zero dependency on any
hosted TTS API (see docs "Engineering principle: do not fake
functionality").

Implements the pre-existing TextToSpeechProvider contract
(backend/app/interfaces/tts.py) that Phase 1 defined but never
implemented - `SimulatedTTSProvider` remains available as a
deterministic test double; this is the genuine synthesis engine, the
same pattern `LocalWOWModelProvider`/`LocalWhisperSTTProvider` already
established.

piper is only imported inside this module's methods, matching those
providers' lazy-import discipline - a deployment that never enables real
TTS does not need it installed at all (see requirements-local-tts.txt).

Voice models: resolved by Piper's own naming convention
(e.g. "en_US-lessac-medium", "hi_IN-pratham-medium" - <lang>_<REGION>-
<name>-<quality>) and downloaded on first use via piper's own
`download_voice()` helper into a local cache directory - never inside
this repo, never git-tracked (default: `~/.cache/wow-ai/piper-voices/`).
Each resolved voice's `PiperVoice` is kept in memory after first load so
repeated calls with the same voice never reload the model.

Output format (the interface itself only says "return complete audio
bytes" / "yield audio chunks", no format field): raw 16-bit signed
little-endian PCM, mono, at the loaded voice's native sample rate (a
Piper voice's own training sample rate, commonly 22050Hz - use
`get_sample_rate()` to find out for a given voice; this is additive
information the ABC has no field for, not a change to the interface).

CPU-bound synthesis is offloaded to a worker thread (`asyncio.to_thread`)
so it never blocks the event loop other in-flight requests share.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.interfaces.tts import TextToSpeechProvider

_DEFAULT_VOICES_DIR = Path.home() / ".cache" / "wow-ai" / "piper-voices"


class TTSNotAvailableError(RuntimeError):
    """Raised when LocalPiperTTSProvider cannot load/synthesize with a real voice."""


class LocalPiperTTSProvider(TextToSpeechProvider):
    def __init__(
        self,
        *,
        default_voice: str = "en_US-lessac-medium",
        voices_dir: str | Path | None = None,
        use_cuda: bool = False,
        auto_download: bool = True,
    ):
        try:
            import piper  # noqa: F401
        except ImportError as e:
            raise TTSNotAvailableError(
                "LocalPiperTTSProvider requires piper-tts, which is not installed. "
                "Install backend/requirements-local-tts.txt, or use SimulatedTTSProvider "
                "for development without real TTS."
            ) from e

        self._default_voice = default_voice
        self._voices_dir = Path(voices_dir) if voices_dir else _DEFAULT_VOICES_DIR
        self._voices_dir.mkdir(parents=True, exist_ok=True)
        self._use_cuda = use_cuda
        self._auto_download = auto_download
        self._loaded_voices: dict[str, object] = {}

    def _resolve_voice(self, voice_name: str):
        """Synchronous - only ever called from a worker thread via
        asyncio.to_thread, never directly on the event loop (model
        loading/downloading is real, potentially slow, blocking I/O)."""
        cached = self._loaded_voices.get(voice_name)
        if cached is not None:
            return cached

        from piper import PiperVoice
        from piper.download_voices import download_voice

        model_path = self._voices_dir / f"{voice_name}.onnx"
        config_path = self._voices_dir / f"{voice_name}.onnx.json"
        if not (model_path.exists() and config_path.exists()):
            if not self._auto_download:
                raise TTSNotAvailableError(
                    f"Piper voice '{voice_name}' not found under {self._voices_dir} "
                    "and auto_download is disabled."
                )
            try:
                download_voice(voice_name, self._voices_dir)
            except Exception as e:  # noqa: BLE001 - surface a clear, actionable error
                raise TTSNotAvailableError(
                    f"Failed to download Piper voice '{voice_name}': {e}"
                ) from e

        try:
            voice = PiperVoice.load(model_path, config_path, use_cuda=self._use_cuda)
        except Exception as e:  # noqa: BLE001
            raise TTSNotAvailableError(
                f"Failed to load Piper voice '{voice_name}' from {model_path}: {e}"
            ) from e

        self._loaded_voices[voice_name] = voice
        return voice

    async def get_sample_rate(self, voice: str | None = None) -> int:
        """Not part of TextToSpeechProvider - additive, informational-only
        helper the media pipeline (Block 5) needs to interpret the raw PCM
        bytes synthesize()/stream_synthesize() return, since the ABC has
        no field for it."""
        voice_name = voice or self._default_voice
        piper_voice = await asyncio.to_thread(self._resolve_voice, voice_name)
        return piper_voice.config.sample_rate

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        if not text or not text.strip():
            raise ValueError("synthesize() requires non-empty text")
        voice_name = voice or self._default_voice
        return await asyncio.to_thread(self._synthesize_sync, text, voice_name)

    def _synthesize_sync(self, text: str, voice_name: str) -> bytes:
        piper_voice = self._resolve_voice(voice_name)
        chunks = list(piper_voice.synthesize(text))
        if not chunks:
            raise TTSNotAvailableError(f"Piper produced no audio for voice '{voice_name}'")
        return b"".join(c.audio_int16_bytes for c in chunks)

    async def stream_synthesize(
        self, text: str, *, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        if not text or not text.strip():
            raise ValueError("stream_synthesize() requires non-empty text")
        voice_name = voice or self._default_voice
        piper_voice = await asyncio.to_thread(self._resolve_voice, voice_name)

        # piper_voice.synthesize() returns a synchronous generator (each
        # advance is CPU-bound onnxruntime work) - pull it one chunk at a
        # time via asyncio.to_thread so the event loop is never blocked,
        # while still yielding incrementally rather than materializing the
        # whole utterance first (which would defeat a *streaming* method).
        gen = piper_voice.synthesize(text)
        iterator = iter(gen)
        _SENTINEL = object()
        while True:
            chunk = await asyncio.to_thread(next, iterator, _SENTINEL)
            if chunk is _SENTINEL:
                break
            yield chunk.audio_int16_bytes
