"""End-to-end simulated-call harness (see docs "Engineering principle: do
not fake functionality" - this module is the honest local stand-in for
real telephony/hardware, not a claim that real calls are being handled).

Drives a scripted caller conversation through the *real* orchestration
stack - `SpeechToTextProvider` -> `AgentRuntime` (WowBrain or WowAgent) ->
`TextToSpeechProvider` -> `TelephonyProvider` - using the deterministic
simulators in `app/providers/{stt,tts,telephony}/simulated.py`. Everything
downstream of "what counts as audio" is the real code path a production
telephony integration would drive; only the audio source/sink is
simulated. This is what `docs/ARCHITECTURE.md` "Definition of done" refers
to as the local demonstration of a realistic simulated personal call.

Turn detection here is intentionally simple: a caller line is treated as
one complete turn once its `SimulatedSTTStreamSession` reports
`is_final=True` (a sentence-ending line). Real VAD/barge-in timing is not
simulated - see docs "Current limitations".
"""

import uuid
from dataclasses import dataclass, field

from app.agent.call_recorder import CallRecorder
from app.interfaces.agent_runtime import AgentRuntime
from app.interfaces.stt import SpeechToTextProvider, TranscriptionResult
from app.interfaces.tts import TextToSpeechProvider
from app.models.call import CallDirection
from app.models.transcript import Speaker
from app.providers.telephony.simulated import SimulatedTelephonyProvider


@dataclass
class SimulatedTurn:
    caller_text: str
    transcript: str
    reply_text: str
    action_type: str
    policy_decision: str | None
    tool_results: list[dict]


@dataclass
class SimulatedCallResult:
    call_id: str
    turns: list[SimulatedTurn] = field(default_factory=list)
    answered: bool = False
    ended: bool = False


async def run_simulated_call(
    *,
    agent: AgentRuntime,
    stt: SpeechToTextProvider,
    tts: TextToSpeechProvider,
    telephony: SimulatedTelephonyProvider,
    user_id: str,
    caller_number: str | None,
    script: list[str],
    call_id: str | None = None,
    conversation_id: str | None = None,
    recorder: CallRecorder | None = None,
    contact_id: str | None = None,
) -> SimulatedCallResult:
    """Run one full simulated call: answer -> (per scripted line: caller
    "speaks" -> STT -> agent -> TTS -> telephony sends audio back) -> end.

    `script` is the caller's side of the conversation, one complete
    utterance per entry (each should read as a finished sentence - see the
    module docstring's turn-detection note).

    `recorder`, when given, persists the call into `Call`/`Conversation`/
    `TranscriptSegment`/`Summary` (docs "Call recording / transcript") -
    the call/conversation ids it mints are then authoritative, so
    `call_id`/`conversation_id` must not be passed alongside it.
    """
    if recorder is not None and (call_id is not None or conversation_id is not None):
        raise ValueError(
            "call_id/conversation_id are minted by `recorder` when one is given - "
            "do not pass them separately."
        )

    db_call = db_conversation = None
    if recorder is not None:
        db_call, db_conversation = await recorder.start_call(
            user_id=user_id,
            caller_number=caller_number,
            direction=CallDirection.INBOUND,
            contact_id=contact_id,
        )
        call_id = str(db_call.id)
        conversation_id = str(db_conversation.id)

    call_id = call_id or str(uuid.uuid4())
    result = SimulatedCallResult(call_id=call_id)

    await telephony.answer_call(call_id)
    result.answered = True

    stream = await stt.start_stream()
    captured: list[TranscriptionResult] = []

    async def on_audio(chunk: bytes) -> None:
        transcription = await stream.feed(chunk)
        if transcription is not None:
            captured.append(transcription)

    await telephony.on_audio_received(call_id, on_audio)

    for caller_line in script:
        captured.clear()
        await telephony.inject_caller_audio(call_id, caller_line.encode("utf-8"))
        if not captured or not captured[-1].is_final:
            continue  # not a complete turn yet (see module docstring)

        transcript = captured[-1].text
        action = await agent.handle_input(
            user_id=user_id,
            text=transcript,
            conversation_id=conversation_id,
            caller_number=caller_number,
        )

        reply_text = action.payload.get("reply", "")
        audio_out = await tts.synthesize(reply_text)
        await telephony.send_audio(call_id, audio_out)

        if recorder is not None:
            await recorder.record_turn(
                conversation_id=conversation_id, speaker=Speaker.CALLER, text=transcript
            )
            await recorder.record_turn(
                conversation_id=conversation_id, speaker=Speaker.ASSISTANT, text=reply_text
            )

        result.turns.append(
            SimulatedTurn(
                caller_text=caller_line,
                transcript=transcript,
                reply_text=reply_text,
                action_type=action.type,
                policy_decision=action.payload.get("policy_decision"),
                tool_results=action.payload.get("tool_results", []),
            )
        )

    await stream.close()
    await telephony.end_call(call_id)
    result.ended = True

    if recorder is not None:
        summary_text = "\n".join(
            f"{'Caller' if i % 2 == 0 else 'WOW'}: {line}"
            for turn in result.turns
            for i, line in enumerate((turn.transcript, turn.reply_text))
        )
        await recorder.end_call(call=db_call, conversation=db_conversation, summary_text=summary_text)

    return result
