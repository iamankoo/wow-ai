"""chunk_pcm16 (app/media/pipeline.py) - pure, no real audio libs needed,
runs unconditionally. Phase 6 Part E/J's voice-command route depends on
this splitting a whole recording into frame-sized pieces correctly (see
its own docstring for why handing a VadStreamSession one giant chunk
would silently drop the trailing SPEECH_END event and the speech in it).
"""

from app.media.pipeline import chunk_pcm16


def test_splits_into_exact_frame_sized_chunks():
    # 16kHz, 30ms frames = 480 samples/frame = 960 bytes/frame (16-bit).
    audio = b"\x01\x02" * 480 * 3  # exactly 3 whole frames
    chunks = list(chunk_pcm16(audio, sample_rate=16000, frame_duration_ms=30))

    assert len(chunks) == 3
    assert all(len(c) == 960 for c in chunks)
    assert b"".join(chunks) == audio


def test_a_short_trailing_partial_frame_is_preserved_not_dropped():
    frame_bytes = 960
    audio = (b"\x01\x02" * 480 * 2) + b"\x03\x04" * 10  # 2 full frames + 20 leftover bytes
    chunks = list(chunk_pcm16(audio, sample_rate=16000, frame_duration_ms=30))

    assert len(chunks) == 3
    assert len(chunks[0]) == frame_bytes
    assert len(chunks[1]) == frame_bytes
    assert len(chunks[2]) == 20
    assert b"".join(chunks) == audio


def test_empty_audio_yields_no_chunks():
    assert list(chunk_pcm16(b"", sample_rate=16000)) == []


def test_respects_the_given_sample_rate_for_frame_size():
    # 8kHz, 30ms frames = 240 samples/frame = 480 bytes/frame.
    audio = b"\x00\x00" * 240 * 2
    chunks = list(chunk_pcm16(audio, sample_rate=8000, frame_duration_ms=30))

    assert len(chunks) == 2
    assert all(len(c) == 480 for c in chunks)
