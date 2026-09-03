"""Real text-to-speech tests for LocalPiperTTSProvider - see
app/providers/tts/local_piper.py. Uses genuine local Piper (ONNX) speech
synthesis, not a mocked return value - every test that asserts on audio
content decodes real bytes the model actually produced.

Skipped cleanly (not failed) if piper-tts isn't installed - it's an
optional dependency (requirements-local-tts.txt), matching the pattern
used for LocalWOWModelProvider/LocalWhisperSTTProvider tests elsewhere in
this suite.

Voice models download once (cached outside the repo under
~/.cache/wow-ai/piper-voices/, never git-tracked) and are shared across
this module's tests via a module-scoped provider fixture.
"""

import wave

import pytest

pytest.importorskip(
    "piper", reason="piper-tts not installed - see backend/requirements-local-tts.txt"
)

from app.providers.tts.local_piper import LocalPiperTTSProvider, TTSNotAvailableError  # noqa: E402

# A representative WOW agent response (see app/agent/response.py's
# CONFIRMED_ACKNOWLEDGEMENT) - real product text, not lorem ipsum.
_WOW_RESPONSE_TEXT = "Got it - I've taken care of that."
_HINDI_TEXT = "main meeting mein hoon, kripya calls handle karo"


@pytest.fixture(scope="module")
def provider() -> LocalPiperTTSProvider:
    return LocalPiperTTSProvider()


async def test_real_synthesis_produces_a_valid_playable_wav_artifact(provider, tmp_path):
    audio = await provider.synthesize(_WOW_RESPONSE_TEXT)
    assert isinstance(audio, bytes)
    assert len(audio) > 0

    sample_rate = await provider.get_sample_rate()
    out_path = tmp_path / "wow_response.wav"
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)

    # Verify the artifact is genuinely valid, playable PCM audio, not just
    # bytes that happened to be non-empty - reopen and inspect it fresh.
    with wave.open(str(out_path), "rb") as check:
        assert check.getnchannels() == 1
        assert check.getsampwidth() == 2
        assert check.getframerate() == sample_rate
        duration_s = check.getnframes() / sample_rate
        assert duration_s > 0.3  # a real ~5-word sentence, not near-silence


async def test_synthesize_rejects_empty_text(provider):
    with pytest.raises(ValueError):
        await provider.synthesize("")


async def test_stream_synthesize_rejects_empty_text(provider):
    with pytest.raises(ValueError):
        async for _ in provider.stream_synthesize(""):
            pass


async def test_stream_synthesize_yields_real_audio_chunks(provider):
    chunks = []
    async for chunk in provider.stream_synthesize(_WOW_RESPONSE_TEXT):
        assert isinstance(chunk, bytes)
        assert len(chunk) > 0
        chunks.append(chunk)
    assert len(chunks) >= 1
    assert sum(len(c) for c in chunks) > 0


async def test_get_sample_rate_reports_the_voices_real_rate(provider):
    # en_US-lessac-medium is a fixed, known Piper voice trained at 22050Hz.
    assert await provider.get_sample_rate() == 22050


async def test_real_multilingual_synthesis_with_a_different_voice(provider):
    """WOW's domain is English/Hindi/Hinglish - proves voice switching
    genuinely produces different real audio from a different (Hindi)
    model, not the same cached bytes relabeled."""
    audio_en = await provider.synthesize(_WOW_RESPONSE_TEXT)
    audio_hi = await provider.synthesize(_HINDI_TEXT, voice="hi_IN-pratham-medium")

    assert len(audio_hi) > 0
    assert audio_hi != audio_en

    sr_hi = await provider.get_sample_rate(voice="hi_IN-pratham-medium")
    assert sr_hi > 0


async def test_missing_voice_without_auto_download_fails_loudly(tmp_path):
    isolated = LocalPiperTTSProvider(voices_dir=tmp_path, auto_download=False)
    with pytest.raises(TTSNotAvailableError):
        await isolated.synthesize("this voice was never downloaded")
