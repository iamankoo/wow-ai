"""SimulatedTelephonyProvider - see app/providers/telephony/simulated.py."""

from app.providers.telephony.simulated import SimulatedTelephonyProvider


async def test_answer_and_end_call_update_log():
    telephony = SimulatedTelephonyProvider()
    await telephony.answer_call("call-1")
    log = telephony.call_log("call-1")
    assert log.answered is True
    assert log.ended is False

    await telephony.end_call("call-1")
    assert telephony.call_log("call-1").ended is True


async def test_send_audio_appends_to_outbound_log():
    telephony = SimulatedTelephonyProvider()
    await telephony.send_audio("call-1", b"hello")
    await telephony.send_audio("call-1", b"world")
    assert telephony.call_log("call-1").outbound_audio == [b"hello", b"world"]


async def test_inject_caller_audio_invokes_registered_handler():
    telephony = SimulatedTelephonyProvider()
    received = []

    async def handler(chunk: bytes) -> None:
        received.append(chunk)

    await telephony.on_audio_received("call-1", handler)
    await telephony.inject_caller_audio("call-1", b"hi")

    assert received == [b"hi"]
    assert telephony.call_log("call-1").inbound_audio == [b"hi"]


async def test_inject_caller_audio_without_handler_does_not_raise():
    telephony = SimulatedTelephonyProvider()
    await telephony.inject_caller_audio("call-1", b"hi")  # no handler registered
    assert telephony.call_log("call-1").inbound_audio == [b"hi"]


async def test_calls_are_isolated_by_call_id():
    telephony = SimulatedTelephonyProvider()
    await telephony.answer_call("call-1")
    assert telephony.call_log("call-2").answered is False
