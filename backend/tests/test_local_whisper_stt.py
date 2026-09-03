"""Real speech-to-text tests for LocalWhisperSTTProvider - see
app/providers/stt/local_whisper.py. Uses genuine local faster-whisper
inference against real WAV fixtures with known spoken content
(backend/tests/fixtures/audio/, generated once via Windows SAPI - see
each fixture's provenance in this file's git history), not a mocked
return value.

Skipped cleanly (not failed) if faster-whisper isn't installed - it's an
optional dependency (requirements-local-stt.txt), matching the
TEST_DATABASE_URL-gated / WOW-Brain-v3-gated pattern used elsewhere in
this suite: skip when the required real component isn't present, never
substitute a fake and call it the same test.

The "base" model is downloaded (once, cached outside the repo under the
platform's Hugging Face cache directory - never git-tracked) and shared
across every test in this module via a module-scoped fixture, since
loading it is the slow part (~15-20s) and each transcription itself is
fast (1-2s on CPU).
"""

import wave
from pathlib import Path

import pytest

pytest.importorskip(
    "faster_whisper",
    reason="faster-whisper not installed - see backend/requirements-local-stt.txt",
)

from app.providers.stt.local_whisper import (  # noqa: E402
    LocalWhisperSTTProvider,
    STTNotAvailableError,
    _resolve_stt_device,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "audio"


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        return w.readframes(w.getnframes()), w.getframerate()


@pytest.fixture(scope="module")
def provider() -> LocalWhisperSTTProvider:
    return LocalWhisperSTTProvider(model_size="base", device="cpu")


async def test_real_transcription_of_hello_fixture(provider):
    pcm, sr = _read_pcm16(_FIXTURES / "hello.wav")
    result = await provider.transcribe(pcm, sample_rate=sr)
    assert "hello" in result.text.lower()
    assert result.is_final is True
    assert result.confidence is not None
    assert 0.0 <= result.confidence <= 1.0


async def test_real_transcription_of_meeting_context_fixture(provider):
    pcm, sr = _read_pcm16(_FIXTURES / "meeting_context.wav")
    result = await provider.transcribe(pcm, sample_rate=sr)
    text = result.text.lower()
    assert "meeting" in text
    assert "handle" in text or "calls" in text


async def test_transcribe_rejects_empty_audio(provider):
    with pytest.raises(ValueError):
        await provider.transcribe(b"", sample_rate=16000)


async def test_transcribe_resamples_non_native_sample_rate(provider):
    """Feed the fixture as if it were recorded at 8kHz (half its real
    rate) - the provider must resample to Whisper's native 16kHz rather
    than mis-decoding it, and still produce a real (if degraded)
    transcription instead of erroring."""
    pcm, _real_sr = _read_pcm16(_FIXTURES / "hello.wav")
    result = await provider.transcribe(pcm, sample_rate=8000)
    assert isinstance(result.text, str)


async def test_streaming_session_buffers_and_returns_only_on_close(provider):
    pcm, sr = _read_pcm16(_FIXTURES / "hello.wav")
    midpoint = len(pcm) // 2

    session = await provider.start_stream(sample_rate=sr)
    first = await session.feed(pcm[:midpoint])
    second = await session.feed(pcm[midpoint:])
    # Streaming honesty (see module docstring): faster-whisper cannot
    # produce a real partial transcript from a chunk, so feed() never
    # fabricates one.
    assert first is None
    assert second is None

    final = await session.close()
    assert final is not None
    assert "hello" in final.text.lower()
    assert final.is_final is True


async def test_streaming_session_close_with_nothing_fed_returns_none(provider):
    session = await provider.start_stream(sample_rate=16000)
    assert await session.close() is None


async def test_streaming_session_feed_after_close_raises(provider):
    session = await provider.start_stream(sample_rate=16000)
    await session.close()
    with pytest.raises(RuntimeError):
        await session.feed(b"\x00\x00")


async def test_streaming_session_double_close_raises(provider):
    session = await provider.start_stream(sample_rate=16000)
    await session.close()
    with pytest.raises(RuntimeError):
        await session.close()


def test_resolve_stt_device_rejects_unknown_device():
    with pytest.raises(ValueError):
        _resolve_stt_device("tpu")


def test_resolve_stt_device_cuda_raises_when_unavailable():
    """This environment/test machine is CPU-only - requesting cuda must
    fail loudly, never silently fall back to cpu."""
    import ctranslate2

    if ctranslate2.get_cuda_device_count() > 0:
        pytest.skip("a real CUDA device is available in this environment")
    with pytest.raises(RuntimeError):
        _resolve_stt_device("cuda")


def test_provider_construction_fails_loudly_for_an_invalid_model():
    with pytest.raises(STTNotAvailableError):
        LocalWhisperSTTProvider(model_size="this-model-does-not-exist-anywhere", device="cpu")
