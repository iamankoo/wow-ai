"""Real voice-activity-detection tests for WebRtcVoiceActivityDetector -
see app/providers/vad/webrtc_vad.py. Uses the real WebRTC VAD algorithm
(via the webrtcvad-wheels prebuilt distribution) against the same real
speech WAV fixture Block 2's STT tests use
(backend/tests/fixtures/audio/meeting_context.wav) - genuine signal
processing over genuine recorded-equivalent speech, not a mock.

Skipped cleanly (not failed) if webrtcvad isn't installed - it's an
optional dependency (requirements-local-vad.txt), matching the pattern
used for the other real-provider tests in this suite, even though this
one is much lighter (no model download) than faster-whisper/piper.
"""

import wave
from pathlib import Path

import pytest

pytest.importorskip(
    "webrtcvad", reason="webrtcvad not installed - see backend/requirements-local-vad.txt"
)

from app.interfaces.vad import VoiceActivityEvent  # noqa: E402
from app.providers.vad.webrtc_vad import WebRtcVoiceActivityDetector  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "meeting_context.wav"
_FRAME_MS = 30


def _read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate()


async def _feed_all(session, pcm: bytes, sample_rate: int, chunk_bytes: int | None = None):
    """Feeds `pcm` through `session` in chunks (default: one VAD frame's
    worth at a time, the realistic case for continuous streaming audio)
    and returns every (event, is_speech) the session reported. A single
    feed() call surfaces at most one event (see feed()'s docstring), so
    this also does a final drain pass with empty chunks in case any
    already-buffered-but-unprocessed frames are still waiting after the
    real audio has all been delivered."""
    events = []
    step = chunk_bytes or (int(sample_rate * _FRAME_MS / 1000) * 2)
    for i in range(0, len(pcm), step):
        result = await session.feed(pcm[i : i + step])
        if result.event is not None:
            events.append((result.event, result.is_speech))
    for _ in range(5):  # drain: flush any remaining whole frames still buffered
        result = await session.feed(b"")
        if result.event is None:
            break
        events.append((result.event, result.is_speech))
    return events


async def test_real_speech_fixture_triggers_speech_start_then_speech_end():
    pcm, sr = _read_pcm16(_FIXTURE)
    vad = WebRtcVoiceActivityDetector()
    session = vad.start_session(sample_rate=sr, frame_duration_ms=_FRAME_MS)

    events = await _feed_all(session, pcm, sr)

    assert [e for e, _ in events] == [VoiceActivityEvent.SPEECH_START, VoiceActivityEvent.SPEECH_END]
    assert events[0][1] is True   # is_speech at speech_start
    assert events[1][1] is False  # is_speech at speech_end


async def test_chunked_delivery_of_arbitrary_size_still_detects_speech():
    """The interface must accept any chunk size, not just whole-buffer or
    frame-aligned feeds - buffers internally to the fixed frame size."""
    pcm, sr = _read_pcm16(_FIXTURE)
    vad = WebRtcVoiceActivityDetector()
    session = vad.start_session(sample_rate=sr, frame_duration_ms=_FRAME_MS)

    # 137 bytes: deliberately NOT aligned to the frame size, to prove the
    # session buffers correctly across ragged chunk boundaries.
    events = await _feed_all(session, pcm, sr, chunk_bytes=137)

    kinds = [e for e, _ in events]
    assert VoiceActivityEvent.SPEECH_START in kinds
    assert VoiceActivityEvent.SPEECH_END in kinds


async def test_sustained_silence_triggers_a_single_silence_event():
    sample_rate = 16000
    frame_bytes = int(sample_rate * _FRAME_MS / 1000) * 2
    silence = b"\x00\x00" * (frame_bytes // 2) * 30  # 30 silent frames = 900ms

    vad = WebRtcVoiceActivityDetector(silence_end_frames=10)
    session = vad.start_session(sample_rate=sample_rate, frame_duration_ms=_FRAME_MS)

    events = await _feed_all(session, silence, sample_rate)

    assert events == [(VoiceActivityEvent.SILENCE, False)]  # fires once, not every frame


async def test_barge_in_detected_when_speech_starts_during_playback():
    pcm, sr = _read_pcm16(_FIXTURE)
    vad = WebRtcVoiceActivityDetector()
    session = vad.start_session(sample_rate=sr, frame_duration_ms=_FRAME_MS)

    await session.notify_playback_started()
    events = await _feed_all(session, pcm, sr)

    assert events[0][0] == VoiceActivityEvent.BARGE_IN


async def test_no_barge_in_when_playback_was_stopped_before_speech():
    pcm, sr = _read_pcm16(_FIXTURE)
    vad = WebRtcVoiceActivityDetector()
    session = vad.start_session(sample_rate=sr, frame_duration_ms=_FRAME_MS)

    await session.notify_playback_started()
    await session.notify_playback_stopped()
    events = await _feed_all(session, pcm, sr)

    assert events[0][0] == VoiceActivityEvent.SPEECH_START


async def test_reset_clears_speech_state_but_not_playback_flag():
    pcm, sr = _read_pcm16(_FIXTURE)
    vad = WebRtcVoiceActivityDetector()
    session = vad.start_session(sample_rate=sr, frame_duration_ms=_FRAME_MS)

    await session.notify_playback_started()
    first_events = await _feed_all(session, pcm, sr)
    assert first_events[0][0] == VoiceActivityEvent.BARGE_IN

    await session.reset()
    # notify_playback_started() was never re-called after reset() -
    # reset() must not have cleared the playback-active flag either.
    second_events = await _feed_all(session, pcm, sr)
    assert second_events[0][0] == VoiceActivityEvent.BARGE_IN


def test_invalid_sample_rate_rejected():
    vad = WebRtcVoiceActivityDetector()
    with pytest.raises(ValueError):
        vad.start_session(sample_rate=11025, frame_duration_ms=_FRAME_MS)


def test_invalid_frame_duration_rejected():
    vad = WebRtcVoiceActivityDetector()
    with pytest.raises(ValueError):
        vad.start_session(sample_rate=16000, frame_duration_ms=25)


def test_aggressiveness_out_of_range_rejected():
    with pytest.raises(ValueError):
        WebRtcVoiceActivityDetector(aggressiveness=4)
