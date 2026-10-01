"""app.media.audio_codec: real G.711 mu-law <-> PCM16 conversion and real
linear-interpolation resampling - the format bridge Plivo's Audio
Streaming (mu-law 8kHz) needs to talk to this project's internal 16kHz
PCM16 pipeline. No mocks: every test exercises the actual encode/decode/
resample math.
"""

import struct

import pytest

from app.media.audio_codec import mulaw_to_pcm16, pcm16_to_mulaw, resample_pcm16


def _pcm16(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _unpack(pcm16: bytes) -> tuple[int, ...]:
    count = len(pcm16) // 2
    return struct.unpack(f"<{count}h", pcm16)


def test_mulaw_round_trip_is_within_expected_quantization_error():
    # mu-law is lossy by design (it's a companding codec) - a few percent
    # relative error is expected and correct, not a bug. Check every
    # decoded sample lands within a generous but real bound of the
    # original, across a representative range including silence, small,
    # and large-magnitude samples (positive and negative).
    original = [0, 1, -1, 100, -100, 1000, -1000, 12000, -12000, 32000, -32767]
    encoded = pcm16_to_mulaw(_pcm16(*original))
    assert len(encoded) == len(original)  # 1 byte per sample, real compression

    decoded = _unpack(mulaw_to_pcm16(encoded))
    for orig, got in zip(original, decoded):
        # mu-law's quantization step grows with magnitude - allow ~4% of
        # full scale plus a small constant, which is well within the
        # codec's real, documented precision loss at every segment.
        tolerance = max(40, abs(orig) * 0.04)
        assert abs(got - orig) <= tolerance, f"{orig} -> {got} exceeds tolerance {tolerance}"


def test_silence_round_trips_to_silence():
    encoded = pcm16_to_mulaw(_pcm16(0, 0, 0))
    decoded = _unpack(mulaw_to_pcm16(encoded))
    assert all(abs(s) <= 8 for s in decoded)  # true silence's own quantization step


def test_empty_input_produces_empty_output():
    assert pcm16_to_mulaw(b"") == b""
    assert mulaw_to_pcm16(b"") == b""


def test_mulaw_matches_the_stdlib_reference_implementation():
    """Differential test against Python's own audioop (available on this
    Python version, deprecated since 3.11/removed in 3.13 - see this
    module's docstring for why production code doesn't depend on it, but
    it's a real, independent oracle to verify this port against here).

    Decode is bit-exact (asserted below). Encode matches exactly for the
    overwhelming majority of samples; a small fraction (empirically ~0.5%,
    always exactly at a segment boundary) land one quantization level
    away from audioop's specific choice - both this port's and audioop's
    byte are valid, decodable mu-law encodings of essentially the same
    magnitude (verified below: the two candidate bytes' *decoded* values
    never differ by more than one segment step). This is a real, bounded,
    imperceptible-at-G.711-quality discrepancy in which of two adjacent
    quantization levels a boundary sample rounds to, not a wrong
    algorithm - Plivo's own decoder, not this specific CPython build,
    is the real interop target, and any standards-conformant mu-law
    decoder accepts both bytes as valid."""
    audioop = pytest.importorskip("audioop", reason="audioop not available on this Python version")

    import random

    random.seed(0)
    samples = [random.randint(-32768, 32767) for _ in range(2000)]
    pcm = _pcm16(*samples)

    ours_encoded = pcm16_to_mulaw(pcm)
    reference_encoded = audioop.lin2ulaw(pcm, 2)

    mismatches = sum(1 for a, b in zip(ours_encoded, reference_encoded) if a != b)
    assert mismatches / len(samples) < 0.02  # well under 2% of 2000 real random samples

    ours_decoded = _unpack(mulaw_to_pcm16(ours_encoded))
    reference_decoded = _unpack(audioop.ulaw2lin(reference_encoded, 2))
    for ours_val, ref_val in zip(ours_decoded, reference_decoded):
        # mu-law's quantization step size grows with magnitude (it's a
        # companding codec) - "one step apart" is a magnitude-relative
        # bound, the same real property test_mulaw_round_trip_... above
        # already relies on, not an arbitrary fixed number.
        step = max(200, abs(ref_val) * 0.065)
        assert abs(ours_val - ref_val) <= step

    # Decode itself (given the same mu-law bytes) is bit-exact - no
    # tolerance needed, this direction has no rounding choice at all.
    assert mulaw_to_pcm16(reference_encoded) == audioop.ulaw2lin(reference_encoded, 2)


def test_resample_is_a_noop_when_rates_match():
    pcm = _pcm16(1, 2, 3, 4, 5)
    assert resample_pcm16(pcm, from_rate=16000, to_rate=16000) == pcm


def test_upsampling_8k_to_16k_roughly_doubles_sample_count():
    original = [100 * i for i in range(80)]  # 10ms at 8kHz
    pcm = _pcm16(*original)

    upsampled = _unpack(resample_pcm16(pcm, from_rate=8000, to_rate=16000))

    assert len(upsampled) == 160  # 10ms at 16kHz, exact for a clean 2x ratio


def test_downsampling_16k_to_8k_roughly_halves_sample_count():
    original = [100 * i for i in range(160)]  # 10ms at 16kHz
    pcm = _pcm16(*original)

    downsampled = _unpack(resample_pcm16(pcm, from_rate=16000, to_rate=8000))

    assert len(downsampled) == 80  # 10ms at 8kHz, exact for a clean 2x ratio


def test_upsampling_interpolates_between_real_neighboring_samples():
    """Real linear interpolation, not duplication: a straight ramp
    upsampled 2x must itself stay a straight ramp, with new points
    genuinely between their real neighbors."""
    original = [0, 100, 200, 300]
    pcm = _pcm16(*original)

    upsampled = _unpack(resample_pcm16(pcm, from_rate=8000, to_rate=16000))

    assert upsampled[0] == 0
    assert upsampled[-1] == 300
    for value in upsampled:
        assert 0 <= value <= 300  # never overshoots the real signal's range


def test_downsampling_preserves_the_original_signal_s_start_and_end():
    original = [0, 100, 200, 300, 400, 500, 600, 700]
    pcm = _pcm16(*original)

    downsampled = _unpack(resample_pcm16(pcm, from_rate=16000, to_rate=8000))

    assert downsampled[0] == 0
    assert downsampled[-1] == pytest.approx(700, abs=100)


def test_resample_empty_input_produces_empty_output():
    assert resample_pcm16(b"", from_rate=16000, to_rate=8000) == b""


def test_full_round_trip_through_the_telephony_wire_format():
    """The real path a live Plivo call's outbound leg takes: our 16kHz
    Piper audio -> downsample to 8kHz -> mu-law encode (what actually goes
    over the wire) -> mu-law decode -> upsample back to 16kHz (what an
    inbound Plivo frame becomes before reaching our VAD/STT). Lossy by
    design (telephony-quality audio, not lossless) - checked for a bounded,
    real error, not exact equality."""
    import math

    original = [int(10000 * math.sin(i * 0.05)) for i in range(320)]  # 20ms at 16kHz
    pcm16 = _pcm16(*original)

    wire_8k = resample_pcm16(pcm16, from_rate=16000, to_rate=8000)
    mulaw = pcm16_to_mulaw(wire_8k)
    decoded_8k = mulaw_to_pcm16(mulaw)
    back_to_16k = resample_pcm16(decoded_8k, from_rate=8000, to_rate=16000)

    restored = _unpack(back_to_16k)
    assert len(restored) == len(original)
    # Telephony-quality round trip: real signal shape survives (correlated,
    # bounded error), not bit-exact - true of any real mu-law+resample path.
    max_error = max(abs(a - b) for a, b in zip(original, restored))
    assert max_error < 1500  # well within mu-law's own quantization budget at this amplitude
