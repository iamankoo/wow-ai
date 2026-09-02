"""SimulatedTTSProvider - see app/providers/tts/simulated.py."""

from app.providers.tts.simulated import SimulatedTTSProvider


async def test_synthesize_returns_utf8_bytes_of_text():
    provider = SimulatedTTSProvider()
    audio = await provider.synthesize("Hello there")
    assert audio == b"Hello there"


async def test_stream_synthesize_yields_words_in_order():
    provider = SimulatedTTSProvider()
    chunks = [chunk async for chunk in provider.stream_synthesize("Hello there friend")]
    assert b"".join(chunks) == b"Hello there friend"
    assert chunks[0] == b"Hello "
    assert chunks[-1] == b"friend"
