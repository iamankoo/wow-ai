"""WebRtcVoiceActivityDetector - real voice activity detection using
Google's WebRTC VAD (a genuine, telephony-purpose-built signal-processing
classifier - not a fake/heuristic stand-in), with zero cloud dependency
and no model download (it's a small, deterministic C algorithm, not a
neural model).

Implements the VoiceActivityDetector/VadStreamSession contract
(backend/app/interfaces/vad.py) that Phase 1 never had at all - the
previous punctuation-heuristic "turn detection" in
app/providers/stt/simulated.py explicitly documented itself as a
stand-in for exactly this. WebRTC's VAD was chosen specifically because
it was designed for real-time voice-call audio (the same domain WOW
operates in), works frame-by-frame on raw 16-bit PCM at telephony-typical
sample rates, and needs no model weights - "webrtcvad-wheels" (a
prebuilt-wheel distribution of the same "webrtcvad" API/algorithm) is
used here only because this development machine lacks a C++ build
toolchain to compile the original "webrtcvad" package from source; the
underlying algorithm and API are identical.

webrtcvad constrains audio to specific frame sizes (10/20/30ms) and
sample rates (8000/16000/32000/48000Hz) - a caller may feed chunks of
any size, so WebRtcVadStreamSession buffers and slices out complete
frames itself.

Debouncing: a single noisy/silent frame must not flip the state -
`speech_start_frames` (default 2 frames, 60ms at 30ms/frame) confirms
speech genuinely started before emitting SPEECH_START/BARGE_IN;
`silence_end_frames` (default 10 frames, 300ms) confirms a pause is
really the end of the caller's turn before emitting SPEECH_END/SILENCE -
matching common voice-assistant end-of-utterance pause thresholds.
"""

from app.interfaces.vad import VadResult, VadStreamSession, VoiceActivityDetector, VoiceActivityEvent

_SUPPORTED_SAMPLE_RATES = (8000, 16000, 32000, 48000)
_SUPPORTED_FRAME_DURATIONS_MS = (10, 20, 30)
_BYTES_PER_SAMPLE = 2  # 16-bit PCM


class WebRtcVadStreamSession(VadStreamSession):
    def __init__(
        self,
        *,
        sample_rate: int,
        frame_duration_ms: int,
        aggressiveness: int,
        speech_start_frames: int,
        silence_end_frames: int,
    ):
        import webrtcvad

        if sample_rate not in _SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"Unsupported VAD sample_rate {sample_rate}. Expected one of: "
                f"{', '.join(str(r) for r in _SUPPORTED_SAMPLE_RATES)}."
            )
        if frame_duration_ms not in _SUPPORTED_FRAME_DURATIONS_MS:
            raise ValueError(
                f"Unsupported VAD frame_duration_ms {frame_duration_ms}. Expected one of: "
                f"{', '.join(str(d) for d in _SUPPORTED_FRAME_DURATIONS_MS)}."
            )

        self._vad = webrtcvad.Vad(aggressiveness)
        self._sample_rate = sample_rate
        self._frame_bytes = int(sample_rate * frame_duration_ms / 1000) * _BYTES_PER_SAMPLE
        self._speech_start_frames = speech_start_frames
        self._silence_end_frames = silence_end_frames

        self._buffer = bytearray()
        self._playback_active = False
        self._reset_state()

    def _reset_state(self) -> None:
        self._in_speech = False
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._ever_spoke_this_turn = False
        self._silence_event_emitted = False
        # Deliberately NOT reset here - playback-active is not part of the
        # utterance state machine, see reset()'s docstring in the interface.

    async def feed(self, audio_chunk: bytes) -> VadResult:
        """Processes complete frames out of the buffer (leftover bytes
        from previous feed() calls plus this chunk). Stops and returns as
        soon as one state-transition event occurs, leaving any remaining
        already-buffered frames unprocessed for the *next* feed() call -
        a single feed() call surfacing at most one event this way means a
        caller who feeds a large chunk containing multiple transitions
        (e.g. a whole pre-recorded utterance in one call) never silently
        loses an earlier event to a later one overwriting it; it simply
        sees them one per call, exactly as a real continuous audio stream
        would deliver them over time."""
        self._buffer.extend(audio_chunk)

        event: VoiceActivityEvent | None = None
        while len(self._buffer) >= self._frame_bytes:
            frame = bytes(self._buffer[: self._frame_bytes])
            frame_is_speech = self._vad.is_speech(frame, self._sample_rate)
            candidate_event = self._process_frame(frame_is_speech)
            del self._buffer[: self._frame_bytes]
            if candidate_event is not None:
                event = candidate_event
                break

        return VadResult(event=event, is_speech=self._in_speech)

    def _process_frame(self, frame_is_speech: bool) -> VoiceActivityEvent | None:
        if frame_is_speech:
            self._consecutive_silence = 0
            if not self._in_speech:
                self._consecutive_speech += 1
                if self._consecutive_speech >= self._speech_start_frames:
                    self._in_speech = True
                    self._consecutive_speech = 0
                    was_playing = self._playback_active
                    self._ever_spoke_this_turn = True
                    self._silence_event_emitted = False
                    return VoiceActivityEvent.BARGE_IN if was_playing else VoiceActivityEvent.SPEECH_START
            return None

        # Silent frame.
        self._consecutive_speech = 0
        if self._in_speech:
            self._consecutive_silence += 1
            if self._consecutive_silence >= self._silence_end_frames:
                self._in_speech = False
                self._consecutive_silence = 0
                return VoiceActivityEvent.SPEECH_END
            return None

        # Already silent and never spoke this turn - detect sustained
        # "dead air" once, not every single frame.
        if not self._ever_spoke_this_turn and not self._silence_event_emitted:
            self._consecutive_silence += 1
            if self._consecutive_silence >= self._silence_end_frames:
                self._silence_event_emitted = True
                return VoiceActivityEvent.SILENCE
        return None

    async def notify_playback_started(self) -> None:
        self._playback_active = True

    async def notify_playback_stopped(self) -> None:
        self._playback_active = False

    async def reset(self) -> None:
        self._buffer.clear()
        self._reset_state()


class WebRtcVoiceActivityDetector(VoiceActivityDetector):
    """aggressiveness: webrtcvad's own 0-3 scale (0 = least aggressive
    about filtering out non-speech, 3 = most) - 2 is a reasonable default
    for typical call-quality audio, matching common usage of this
    library."""

    def __init__(
        self,
        *,
        aggressiveness: int = 2,
        speech_start_frames: int = 2,
        silence_end_frames: int = 10,
    ):
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness must be between 0 and 3 (webrtcvad's own scale)")
        self._aggressiveness = aggressiveness
        self._speech_start_frames = speech_start_frames
        self._silence_end_frames = silence_end_frames

    def start_session(
        self, *, sample_rate: int = 16000, frame_duration_ms: int = 30
    ) -> VadStreamSession:
        return WebRtcVadStreamSession(
            sample_rate=sample_rate,
            frame_duration_ms=frame_duration_ms,
            aggressiveness=self._aggressiveness,
            speech_start_frames=self._speech_start_frames,
            silence_end_frames=self._silence_end_frames,
        )
