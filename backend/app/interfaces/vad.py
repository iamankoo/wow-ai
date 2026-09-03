"""Voice activity detection / turn-detection abstraction.

Phase 1's simulated STT stand-in used a punctuation heuristic
("ends with . ? !") to decide when a caller's turn is over - a
deliberate, honestly-labeled stand-in (see
app/providers/stt/simulated.py), never meant to survive into real audio.
Real audio has no punctuation: turn-taking has to be decided from the
audio signal itself. This interface is that seam, following the same
pattern as SpeechToTextProvider/TextToSpeechProvider/TelephonyProvider -
contract here, real self-hosted implementation in
app/providers/vad/webrtc_vad.py, zero cloud dependency either way.

A VAD session is stateful and per-call (mirrors STTStreamSession): it is
fed raw PCM16 mono audio chunks in real time and reports discrete
turn-taking events - speech starting, speech ending (the caller's turn
is over), sustained silence, and barge-in (the caller starts speaking
again while WOW's own synthesized audio is still being played out to
them - a real conversational interruption, distinct from ordinary
speech-start, and only detectable because the session is told when WOW's
own playback starts/stops).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class VoiceActivityEvent(str, Enum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    SILENCE = "silence"
    BARGE_IN = "barge_in"


@dataclass
class VadResult:
    """The VAD session's judgment after processing whatever complete
    audio frames a feed() call contained.

    `event` is None when nothing changed (still mid-speech or
    mid-silence, no new transition to report) - most feed() calls during
    a long utterance or a long pause return event=None, exactly as
    expected; `event` is only set on an actual state transition.
    """

    event: VoiceActivityEvent | None
    is_speech: bool


class VadStreamSession(ABC):
    """A stateful, per-call VAD session fed chunked audio in real time."""

    @abstractmethod
    async def feed(self, audio_chunk: bytes) -> VadResult:
        """Feed raw PCM16 mono audio bytes in (any chunk size - the
        session buffers to the fixed frame size the underlying detector
        requires), return the resulting VAD state/event."""

    @abstractmethod
    async def notify_playback_started(self) -> None:
        """Tell the session WOW's own TTS audio has started playing out
        to the caller - required to distinguish an ordinary speech-start
        from a barge-in (speech starting *while WOW is talking*)."""

    @abstractmethod
    async def notify_playback_stopped(self) -> None:
        """Tell the session WOW's own TTS audio playback has ended."""

    @abstractmethod
    async def reset(self) -> None:
        """Clear internal speech/silence state for a new turn - does not
        affect the playback-active flag, which reset() leaves untouched
        since it is not itself part of the utterance state machine."""


class VoiceActivityDetector(ABC):
    @abstractmethod
    def start_session(
        self, *, sample_rate: int = 16000, frame_duration_ms: int = 30
    ) -> VadStreamSession:
        """Start a new stateful VAD session for one call leg."""
