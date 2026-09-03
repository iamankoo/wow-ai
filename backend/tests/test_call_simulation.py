"""End-to-end simulated-call test: real STT-shaped -> WowAgent -> TTS-shaped
-> telephony flow, using the deterministic simulators (see
app/simulation/call_simulator.py) plus WowAgent for real orchestration
(policy/tools/state) - the same test doubles as test_agent_orchestrator.py
for context/memory so no database is required.

This is the closest thing Phase 1 has to a demonstrable "realistic
simulated personal call" (see docs/ARCHITECTURE.md "Definition of done"):
everything except the audio source/sink is the real code path.
"""

from app.agent.context_profile_repository import InMemoryContextProfileRepository
from app.agent.orchestrator import WowAgent, build_default_tool_registry
from app.agent.summary_repository import InMemorySummaryRepository
from app.agent.user_settings_repository import InMemoryUserSettingsRepository
from app.brain.state_repository import InMemoryStateRepository
from app.interfaces.context_engine import ConversationContext
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider
from app.providers.stt.simulated import SimulatedSTTProvider
from app.providers.telephony.simulated import SimulatedTelephonyProvider
from app.providers.tts.simulated import SimulatedTTSProvider
from app.simulation.call_simulator import run_simulated_call
from tests.agent_fakes import FakeContextEngine, InMemoryMemoryStore


async def test_simulated_call_full_lifecycle():
    memory_store = InMemoryMemoryStore()
    context = ConversationContext(
        user_id="u1",
        contact={"id": "contact-1", "name": "Priya", "relationship": "friend"},
    )
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(),
        FakeContextEngine(context),
        InMemoryStateRepository(),
        tools,
    )

    result = await run_simulated_call(
        agent=agent,
        stt=SimulatedSTTProvider(),
        tts=SimulatedTTSProvider(),
        telephony=SimulatedTelephonyProvider(),
        user_id="u1",
        caller_number="+19999999999",
        conversation_id="conv-1",
        script=[
            "Hi there!",
            "Can you take a message for him?",
            "Thanks, bye!",
        ],
    )

    assert result.answered is True
    assert result.ended is True
    assert len(result.turns) == 3

    greeting, message, goodbye = result.turns
    assert greeting.action_type == "greeting"
    assert "How can I help" in greeting.reply_text
    assert message.action_type == "take_message"
    assert goodbye.action_type == "goodbye"


async def test_simulated_call_produces_outbound_audio_for_every_turn():
    memory_store = InMemoryMemoryStore()
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(),
        FakeContextEngine(),
        InMemoryStateRepository(),
        tools,
    )
    telephony = SimulatedTelephonyProvider()

    result = await run_simulated_call(
        agent=agent,
        stt=SimulatedSTTProvider(),
        tts=SimulatedTTSProvider(),
        telephony=telephony,
        user_id="u1",
        caller_number=None,
        script=["Hello!", "Bye!"],
    )

    log = telephony.call_log(result.call_id)
    assert len(log.outbound_audio) == len(result.turns) == 2
    assert log.inbound_audio == [b"Hello!", b"Bye!"]


async def test_simulated_call_turn_count_persists_via_agent_state():
    memory_store = InMemoryMemoryStore()
    tools = build_default_tool_registry(
        memory_store,
        InMemorySummaryRepository(),
        InMemoryContextProfileRepository(),
        InMemoryUserSettingsRepository(),
    )
    agent = WowAgent(
        RuleBasedLanguageModelProvider(),
        FakeContextEngine(),
        InMemoryStateRepository(),
        tools,
    )

    result = await run_simulated_call(
        agent=agent,
        stt=SimulatedSTTProvider(),
        tts=SimulatedTTSProvider(),
        telephony=SimulatedTelephonyProvider(),
        user_id="u1",
        caller_number=None,
        conversation_id="conv-42",
        script=["Hello!", "Are you free?", "Bye!"],
    )

    assert [t.action_type for t in result.turns] == ["greeting", "check_availability", "goodbye"]
