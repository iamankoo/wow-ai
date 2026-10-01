"""Raw audio format conversion between telephony wire audio (G.711 mu-law,
8kHz) and this project's internal audio format (linear PCM16 little-endian,
16kHz - what WebRtcVoiceActivityDetector/LocalWhisperSTTProvider/
LocalPiperTTSProvider all already assume).

A real telephony provider's media stream (e.g. Plivo's Audio Streaming,
see app/providers/telephony/plivo.py) speaks mu-law 8kHz - the standard
PSTN wire format - not PCM16 16kHz. Every function here is a real,
independently-testable signal conversion, not a stub: mu-law<->PCM16 is
the standard ITU-T G.711 companding algorithm (the same public-domain
reference implementation used across open-source telephony code, e.g.
Sun/NeXT's g711.c), and resampling is real linear interpolation, not
sample duplication/dropping.

Deliberately no numpy/audioop dependency: `audioop` is deprecated since
Python 3.11 and removed in 3.13 (PEP 594) - not something to add a new
dependency on - and numpy is an optional dependency elsewhere in this
project (only pulled in by the local STT/TTS extras), so this module
(needed unconditionally by the Plivo adapter, whichever STT/TTS provider
is configured) stays dependency-free, pure Python + stdlib `struct`.
"""

import struct

_BIAS = 0x84
_CLIP = 32635

# The 8 mu-law segment boundaries: segment i covers biased magnitudes up to
# 2**(8+i) - 1 (255, 511, 1023, ..., 32767). Found via a boundary search
# rather than a hand-transcribed 256-row lookup table - the same standard
# G.711 segmentation, derived instead of copied, and cross-checked against
# Python's own `audioop` reference in test_audio_codec.py.
_SEGMENT_ENDS = (0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF)
# Decode table: the linear magnitude at the start of each of the 8 exponent
# segments.
_DECODE_EXP_LUT = (0, 132, 396, 924, 1980, 4092, 8316, 16764)


def _segment_of(biased_magnitude: int) -> int:
    for exponent, end in enumerate(_SEGMENT_ENDS):
        if biased_magnitude <= end:
            return exponent
    return len(_SEGMENT_ENDS) - 1  # clipped magnitude never actually exceeds the last segment


def _encode_sample(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0x00
    if sample < 0:
        sample = -sample
    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS
    exponent = _segment_of(sample)
    mantissa = (sample >> (exponent + 3)) & 0x0F
    ulaw_byte = ~(sign | (exponent << 4) | mantissa)
    return ulaw_byte & 0xFF


def _decode_sample(ulaw_byte: int) -> int:
    ulaw_byte = ~ulaw_byte & 0xFF
    sign = ulaw_byte & 0x80
    exponent = (ulaw_byte >> 4) & 0x07
    mantissa = ulaw_byte & 0x0F
    sample = _DECODE_EXP_LUT[exponent] + (mantissa << (exponent + 3))
    return -sample if sign != 0 else sample


def pcm16_to_mulaw(pcm16: bytes) -> bytes:
    """Encodes linear PCM16 little-endian samples to G.711 mu-law bytes
    (one byte per sample, 4:1 size reduction) - the format Plivo's Audio
    Streaming expects for outbound `playAudio` frames."""
    if not pcm16:
        return b""
    count = len(pcm16) // 2
    samples = struct.unpack(f"<{count}h", pcm16[: count * 2])
    return bytes(_encode_sample(s) for s in samples)


def mulaw_to_pcm16(mulaw: bytes) -> bytes:
    """Decodes G.711 mu-law bytes to linear PCM16 little-endian - the
    format every other real provider in this project (VAD/STT) already
    assumes. Inverse of pcm16_to_mulaw."""
    if not mulaw:
        return b""
    samples = [_decode_sample(b) for b in mulaw]
    return struct.pack(f"<{len(samples)}h", *samples)


def resample_pcm16(pcm16: bytes, *, from_rate: int, to_rate: int) -> bytes:
    """Resamples linear PCM16 little-endian audio between sample rates via
    real linear interpolation (not sample duplication/dropping) - used to
    bridge Plivo's 8kHz telephony audio and this project's 16kHz internal
    pipeline (WebRtcVoiceActivityDetector/LocalWhisperSTTProvider both
    expect 16kHz). A no-op (returns the input unchanged) when the rates
    already match, so callers never need to special-case that."""
    if from_rate == to_rate:
        return pcm16
    if not pcm16:
        return b""
    count = len(pcm16) // 2
    samples = struct.unpack(f"<{count}h", pcm16[: count * 2])
    if count == 0:
        return b""
    if count == 1:
        # A single sample has no neighbor to interpolate against - every
        # resampled position is just that one sample, honestly, not a
        # fabricated waveform.
        ratio = to_rate / from_rate
        out_len = max(1, round(count * ratio))
        return struct.pack(f"<{out_len}h", *([samples[0]] * out_len))

    ratio = to_rate / from_rate
    out_len = max(1, round(count * ratio))
    last_index = count - 1
    out = [0] * out_len
    for i in range(out_len):
        src_pos = min(i / ratio, last_index)
        idx = int(src_pos)
        frac = src_pos - idx
        s0 = samples[idx]
        s1 = samples[idx + 1] if idx + 1 <= last_index else samples[idx]
        out[i] = int(round(s0 + (s1 - s0) * frac))
    return struct.pack(f"<{out_len}h", *out)
