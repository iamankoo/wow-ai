"""LocalWhisperSTTProvider - real speech-to-text using faster-whisper
(CTranslate2-accelerated Whisper), with zero dependency on any hosted
speech API (see docs "Engineering principle: do not fake functionality").

This is the real implementation of the SpeechToTextProvider contract
(backend/app/interfaces/stt.py) that Phase 1 defined but never
implemented - `SimulatedSTTProvider` remains available as a deterministic
test double for orchestration-layer tests; this is the genuine ASR
engine, the same "provider satisfies the existing interface, verified
with real inference" pattern `LocalWOWModelProvider` already established
for the reasoning model.

faster-whisper/ctranslate2 are only imported inside this module's
methods, never at module import time, matching LocalWOWModelProvider's
lazy-import discipline - a deployment that never enables real STT does
not need them installed at all (see requirements-local-stt.txt).

Audio format contract (the interface itself only says "raw audio bytes"
and takes sample_rate separately, implying no container/encoding): raw
16-bit signed little-endian PCM, mono, at the given sample_rate - the
universal raw format, and what real telephony/Android audio APIs
typically hand off.

Language handling for English/Hindi/Hinglish: Whisper is multilingual
and this provider defaults to per-utterance language auto-detection
(`language=None`), which is the honest choice for code-switched
Hindi-English speech - there is no dedicated "Hinglish" mode in Whisper,
and forcing a single language would mis-transcribe genuinely mixed
utterances. A specific language can still be forced via the `language`
constructor argument when the caller knows it in advance.

Streaming honesty: faster-whisper does not perform true incremental/
partial ASR decoding - feeding one chunk cannot honestly produce a
meaningful partial transcript. `LocalWhisperSTTStreamSession.feed()`
therefore buffers audio and returns None (no fabricated partial result);
`close()` runs one real transcription over everything buffered and
returns the final result. This is the accurate behavior for a
Whisper-family model used this way, not a shortcut - see docs "do not
fake functionality". The interface's chunked-delivery contract is still
honored (audio can be fed incrementally); only the *partial-result*
promise is left honestly unfulfilled.
"""

import math

from app.interfaces.stt import STTStreamSession, SpeechToTextProvider, TranscriptionResult

_SUPPORTED_DEVICES = ("auto", "cpu", "cuda")
_WHISPER_SAMPLE_RATE = 16000


class STTNotAvailableError(RuntimeError):
    """Raised when LocalWhisperSTTProvider cannot load a real model."""


def _resolve_stt_device(requested: str) -> str:
    """CTranslate2 device-string resolution - deliberately independent of
    app.ml.device.resolve_inference_device (that one requires torch;
    faster-whisper/CTranslate2 does not, so using it here would force a
    torch install just to use real STT without also enabling
    MODEL_PROVIDER=local_wow)."""
    import ctranslate2

    requested = (requested or "cpu").lower()
    if requested not in _SUPPORTED_DEVICES:
        raise ValueError(
            f"Unsupported STT device '{requested}'. Expected one of: "
            f"{', '.join(_SUPPORTED_DEVICES)}."
        )
    if requested == "cuda":
        if ctranslate2.get_cuda_device_count() == 0:
            raise RuntimeError(
                "STT device 'cuda' was requested but no CUDA device was detected."
            )
        return "cuda"
    if requested == "auto":
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    return "cpu"


def _pcm16_bytes_to_float32(audio: bytes):
    import numpy as np

    if len(audio) % 2 != 0:
        raise ValueError("PCM16 audio buffer must have an even number of bytes")
    samples = np.frombuffer(audio, dtype="<i2")
    return samples.astype(np.float32) / 32768.0


def _resample_linear(samples, orig_sr: int, target_sr: int):
    """Simple linear-interpolation resampler - avoids adding scipy/
    librosa as a dependency purely to reach Whisper's required 16kHz."""
    import numpy as np

    if orig_sr == target_sr or len(samples) <= 1:
        return samples
    duration = len(samples) / orig_sr
    target_len = max(1, int(round(duration * target_sr)))
    orig_x = np.linspace(0, duration, num=len(samples), endpoint=False)
    target_x = np.linspace(0, duration, num=target_len, endpoint=False)
    return np.interp(target_x, orig_x, samples).astype(np.float32)


def _confidence_from_segments(segments: list) -> float | None:
    """Whisper segments report avg_logprob (average log probability over
    the segment's tokens), not a bounded [0,1] confidence - exp() gives a
    reasonable, honestly-approximate probability-like value. None when
    there's nothing to compute it from (e.g. a silent buffer)."""
    logprobs = [s.avg_logprob for s in segments if getattr(s, "avg_logprob", None) is not None]
    if not logprobs:
        return None
    avg = sum(logprobs) / len(logprobs)
    return max(0.0, min(1.0, math.exp(avg)))


class LocalWhisperSTTStreamSession(STTStreamSession):
    def __init__(self, provider: "LocalWhisperSTTProvider", sample_rate: int):
        self._provider = provider
        self._sample_rate = sample_rate
        self._buffer = bytearray()
        self._closed = False

    async def feed(self, audio_chunk: bytes) -> TranscriptionResult | None:
        if self._closed:
            raise RuntimeError("feed() called after close()")
        self._buffer.extend(audio_chunk)
        # See module docstring "Streaming honesty" - no partial result.
        return None

    async def close(self) -> TranscriptionResult | None:
        if self._closed:
            raise RuntimeError("close() called twice")
        self._closed = True
        if not self._buffer:
            return None
        result = await self._provider.transcribe(
            bytes(self._buffer), sample_rate=self._sample_rate
        )
        self._buffer = bytearray()
        return result


class LocalWhisperSTTProvider(SpeechToTextProvider):
    """Loads a faster-whisper model once at construction time and reuses
    it for every transcription - mirrors LocalWOWModelProvider's
    load-once-at-init, fail-loud-if-unavailable discipline."""

    def __init__(
        self,
        *,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str | None = None,
        language: str | None = None,
        download_root: str | None = None,
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise STTNotAvailableError(
                "LocalWhisperSTTProvider requires faster-whisper, which is not "
                "installed. Install backend/requirements-local-stt.txt, or use "
                "SimulatedSTTProvider for development without real ASR."
            ) from e

        resolved_device = _resolve_stt_device(device)
        resolved_compute_type = compute_type or ("int8" if resolved_device == "cpu" else "float16")
        # None = auto-detect per utterance - the honest choice for
        # code-switched Hindi/English (Hinglish) speech, see module docstring.
        self._language = language

        try:
            self._model = WhisperModel(
                model_size,
                device=resolved_device,
                compute_type=resolved_compute_type,
                download_root=download_root,
            )
        except Exception as e:  # noqa: BLE001 - surface a clear, actionable error, never fall back silently
            raise STTNotAvailableError(
                f"Failed to load faster-whisper model '{model_size}' "
                f"(device={resolved_device}, compute_type={resolved_compute_type}): {e}"
            ) from e

    async def transcribe(self, audio: bytes, *, sample_rate: int = 16000) -> TranscriptionResult:
        if not audio:
            raise ValueError("transcribe() requires a non-empty audio buffer")

        samples = _pcm16_bytes_to_float32(audio)
        if sample_rate != _WHISPER_SAMPLE_RATE:
            samples = _resample_linear(samples, sample_rate, _WHISPER_SAMPLE_RATE)

        segments_iter, _info = self._model.transcribe(samples, language=self._language)
        segments = list(segments_iter)
        text = " ".join(s.text.strip() for s in segments).strip()
        confidence = _confidence_from_segments(segments)
        return TranscriptionResult(text=text, is_final=True, confidence=confidence)

    async def start_stream(self, *, sample_rate: int = 16000) -> STTStreamSession:
        return LocalWhisperSTTStreamSession(self, sample_rate)
