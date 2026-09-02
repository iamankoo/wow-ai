"""SimulatedSTTProvider - see app/providers/stt/simulated.py."""

from app.providers.stt.simulated import SimulatedSTTProvider


async def test_transcribe_full_buffer():
    provider = SimulatedSTTProvider()
    result = await provider.transcribe("hello there".encode("utf-8"))
    assert result.text == "hello there"
    assert result.is_final is True


async def test_stream_partial_then_final():
    provider = SimulatedSTTProvider()
    stream = await provider.start_stream()

    partial = await stream.feed("hello".encode("utf-8"))
    assert partial.is_final is False
    assert partial.text == "hello"

    final = await stream.feed("there.".encode("utf-8"))
    assert final.is_final is True
    assert final.text == "hello there."


async def test_stream_close_flushes_incomplete_buffer():
    provider = SimulatedSTTProvider()
    stream = await provider.start_stream()
    await stream.feed("half a sentence".encode("utf-8"))
    trailing = await stream.close()
    assert trailing.text == "half a sentence"
    assert trailing.is_final is True


async def test_feed_after_close_raises():
    provider = SimulatedSTTProvider()
    stream = await provider.start_stream()
    await stream.close()
    try:
        await stream.feed(b"too late")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


async def test_second_utterance_starts_a_fresh_buffer_after_a_final():
    provider = SimulatedSTTProvider()
    stream = await provider.start_stream()
    await stream.feed("first sentence.".encode("utf-8"))
    second = await stream.feed("second one.".encode("utf-8"))
    assert second.text == "second one."
