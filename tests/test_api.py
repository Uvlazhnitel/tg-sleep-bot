from fastapi.testclient import TestClient

from app.api.routes import get_chat_service
from app.core.config import get_settings
from app.main import create_app
from app.models.extractor import MemoryExtractionResult
from app.models.insight import InsightGenerationResult, InsightPreferenceUpdateRequest
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.insight_repository import InsightRepository
from app.models.memory import MemoryCreateRequest
from app.repositories.memory_repository import MemoryRepository
from app.repositories.pending_memory_confirmation_repository import (
    PendingMemoryConfirmationRepository,
)
from app.repositories.session_state_repository import SessionStateRepository
from app.services.chat_service import ChatService
from app.services.knowledge_service import KnowledgeService
from app.services.insight_service import InsightService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
from app.services.safety_classifier import SafetyClassifierService


class StubOpenAIService:
    def __init__(
        self,
        reply: str = "Test reply",
        extraction: MemoryExtractionResult | None = None,
        insight_generation: InsightGenerationResult | None = None,
    ):
        self.reply = reply
        self.extraction = extraction or MemoryExtractionResult(
            memory_updates=[],
            ignored=[],
        )
        self.insight_generation = insight_generation or InsightGenerationResult(
            should_create_insight=False,
            insights=[],
            reason_if_none="Not enough evidence.",
        )
        self.last_memories = []
        self.last_knowledge_cards = []
        self.last_personalization_context = ""
        self.last_safety_classification = None

    def generate_assistant_reply(
        self,
        message,
        history,
        relevant_memories,
        relevant_knowledge_cards,
        personalization_context,
        safety_classification,
    ):
        self.last_memories = relevant_memories
        self.last_knowledge_cards = relevant_knowledge_cards
        self.last_personalization_context = personalization_context
        self.last_safety_classification = safety_classification
        return self.reply

    def extract_memory_updates(self, user_message, assistant_reply, relevant_memories):
        return self.extraction

    def generate_insight_candidates(
        self,
        user_message,
        history,
        recent_traces,
        memories,
        relevant_knowledge_cards,
        last_insight_at,
        max_candidates,
    ):
        return self.insight_generation


class FailingExtractorOpenAIService(StubOpenAIService):
    def extract_memory_updates(self, user_message, assistant_reply, relevant_memories):
        from app.core.exceptions import UpstreamServiceError

        raise UpstreamServiceError("extractor failed")


def build_client(monkeypatch, tmp_path, chat_service=None, *, app_env="production"):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("KNOWLEDGE_CARDS_PATH", "app/data/knowledge_cards.json")
    get_settings.cache_clear()

    app = create_app()
    if chat_service is not None:
        app.dependency_overrides[get_chat_service] = lambda: chat_service
    return app


def build_chat_service(tmp_path, openai_service, *, debug_metadata_allowed=False):
    database_path = str(tmp_path / "api.db")
    repository = MemoryRepository(database_path)
    memory_service = MemoryService(repository, "default_user")
    memory_service.ensure_seed_memories()
    knowledge_service = KnowledgeService("app/data/knowledge_cards.json")
    transparency_service = MemoryTransparencyService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        advice_trace_repository=AdviceTraceRepository(database_path),
        session_state_repository=SessionStateRepository(database_path),
        pending_confirmation_repository=PendingMemoryConfirmationRepository(database_path),
    )
    insight_service = InsightService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        openai_service=openai_service,
        advice_trace_repository=AdviceTraceRepository(database_path),
        insight_repository=InsightRepository(database_path),
    )
    return ChatService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        openai_service=openai_service,
        safety_classifier=SafetyClassifierService(),
        memory_transparency_service=transparency_service,
        insight_service=insight_service,
        debug_metadata_allowed=debug_metadata_allowed,
    )


def test_health_check(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_memory_returns_seeded_memories(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.get("/memory")

    assert response.status_code == 200
    memory = response.json()["memories"][0]
    assert len(response.json()["memories"]) >= 6
    assert "evidence_count" in memory
    assert "positive_count" in memory
    assert "negative_count" in memory


def test_post_patch_delete_memory(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        created = client.post(
            "/memory",
            json={
                "type": "worked_before",
                "content": "Morning light helped the user get out of bed.",
                "confidence": 0.9,
                "source": "manual",
            },
        )
        assert created.status_code == 200
        memory_id = created.json()["id"]

        updated = client.patch(
            f"/memory/{memory_id}",
            json={"content": "Morning light helps with waking up.", "confidence": 0.95},
        )
        assert updated.status_code == 200
        assert updated.json()["content"] == "Morning light helps with waking up."

        deleted = client.delete(f"/memory/{memory_id}")
        assert deleted.status_code == 200
        assert deleted.json()["is_archived"] is True


def test_memory_feedback_endpoint_updates_counts(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        created = client.post(
            "/memory",
            json={
                "type": "hypothesis",
                "content": "Late caffeine may be linked to early awakenings.",
                "confidence": 0.4,
                "source": "manual",
            },
        ).json()

        updated = client.post(
            "/memory/feedback",
            json={"memory_id": created["id"], "feedback": "confirmed"},
        )

    assert updated.status_code == 200
    assert updated.json()["confidence"] >= 0.5
    assert updated.json()["evidence_count"] >= 2


def test_chat_memory_summary_intent(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.post("/chat", json={"message": "What do you remember about me?"})

    assert response.status_code == 200
    assert "I currently remember:" in response.json()["reply"]
    assert "Goal:" in response.json()["reply"]
    assert "Preferences:" in response.json()["reply"]


def test_chat_feedback_helped_creates_memory(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Try morning light tomorrow."),
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "message": "That helped yesterday.",
                "history": [{"role": "assistant", "content": "Try morning light tomorrow."}],
            },
        )

    assert response.status_code == 200
    assert "I'll remember that this helped" in response.json()["reply"]
    assert any(
        memory.type == "worked_before" for memory in chat_service.memory_service.list_memories()
    )


def test_chat_feedback_did_not_work_creates_memory(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Set more alarms."),
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "message": "That didn't work for me.",
                "history": [{"role": "assistant", "content": "Set more alarms."}],
            },
        )

    assert response.status_code == 200
    assert "I'll avoid leaning on that next time" in response.json()["reply"]
    assert any(
        memory.type == "did_not_work" for memory in chat_service.memory_service.list_memories()
    )


def test_chat_ambiguous_feedback_asks_clarifying_question(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Reply."),
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "That helped yesterday."})

    assert response.status_code == 200
    assert "What part helped" in response.json()["reply"]


def test_forget_that_i_snooze_archives_correct_memory(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Reply."))
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Forget that I snooze alarms."})

    assert response.status_code == 200
    assert "removed that memory" in response.json()["reply"]
    assert any(
        memory.is_archived
        for memory in chat_service.memory_service.list_memories(include_archived=True)
        if "snoozing alarms" in memory.content
    )


def test_ambiguous_delete_asks_for_clarification(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Reply."))
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="hypothesis",
            content="Late caffeine may affect sleep.",
            confidence=0.5,
            source="manual",
        )
    )
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="preference",
            content="User prefers not to drink coffee after lunch.",
            confidence=0.9,
            source="manual",
        )
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Forget everything about caffeine."})

    assert response.status_code == 200
    assert "Which one should I remove?" in response.json()["reply"]


def test_chat_includes_relevant_memory_and_knowledge_context(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Try morning light again."))
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Morning light helped the user get out of bed.",
            confidence=0.9,
            source="manual",
            positive_count=1,
        )
    )
    openai_service = chat_service.openai_service

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I keep snoozing my alarms and feel groggy every morning."},
        )

    assert response.status_code == 200
    assert any("Morning light helped" in memory.content for memory in openai_service.last_memories)
    assert any(card.topic == "snoozing" for card in openai_service.last_knowledge_cards)
    assert "Worked before:" in openai_service.last_personalization_context
    assert "Relevant User Memories" not in openai_service.last_personalization_context


def test_hypotheses_are_not_presented_as_facts_in_prompt_context(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Reply."))
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="hypothesis",
            content="Late caffeine may be linked to early awakenings.",
            confidence=0.4,
            source="manual",
        )
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Why am I waking early?"})

    assert response.status_code == 200
    assert "Hypotheses to treat cautiously:" in chat_service.openai_service.last_personalization_context
    assert "confidence: low" in chat_service.openai_service.last_personalization_context


def test_chat_returns_reply_when_memory_extraction_fails(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        FailingExtractorOpenAIService("Still keep 09:00 tomorrow."),
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I slept badly."})

    assert response.status_code == 200
    assert response.json()["reply"] == "Still keep 09:00 tomorrow."


def test_coffee_does_not_affect_me_downgrades_hypothesis(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Reply."))
    created = chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="hypothesis",
            content="Coffee may affect the user's sleep.",
            confidence=0.4,
            source="manual",
        )
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Coffee doesn't affect my sleep."},
        )

    refreshed = chat_service.memory_service.get_memory(created.id)
    assert response.status_code == 200
    assert "caffeine-related" in response.json()["reply"].lower() or "coffee" in response.json()["reply"].lower()
    assert refreshed.confidence < 0.4 or refreshed.is_archived is True


def test_change_wake_goal_updates_fixed_goal(monkeypatch, tmp_path):
    chat_service = build_chat_service(tmp_path, StubOpenAIService("Reply."))
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Change my wake-up goal to 08:30."},
        )

    assert response.status_code == 200
    assert "08:30" in response.json()["reply"]
    assert any(
        memory.type == "fixed_goal" and "08:30" in memory.content
        for memory in chat_service.memory_service.list_memories()
    )


def test_manual_insights_request_returns_pattern_summary(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Multiple alarms may reinforce snoozing",
                    "summary": "Multiple alarms seem to make snoozing easier for you.",
                    "evidence": [
                        "You have mentioned snoozing several times.",
                        "Many alarms did not help."
                    ],
                    "confidence": "high",
                    "suggested_experiment": "For the next 3 mornings, use one main alarm at 09:00 and one backup at 09:10 only."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="did_not_work",
            content="Many alarms did not help.",
            confidence=0.9,
            source="manual",
        )
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "What patterns do you notice?"})

    assert response.status_code == 200
    assert "strongest one" in response.json()["reply"].lower()
    assert "best experiment for this week" in response.json()["reply"].lower()
    assert "09:00" in response.json()["reply"]


def test_low_confidence_manual_insight_is_presented_as_hypothesis(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Late caffeine may affect sleep",
                    "summary": "Late caffeine may be affecting your sleep, but I would treat it as a hypothesis for now.",
                    "evidence": [
                        "You mentioned caffeine once.",
                        "A related knowledge card says caffeine can affect sleep."
                    ],
                    "confidence": "low",
                    "suggested_experiment": "Move evening caffeine earlier for a few days and keep the 09:00 wake time steady."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Do you see any sleep patterns?"})

    assert response.status_code == 200
    assert "possible hypothesis" in response.json()["reply"].lower()
    assert "hypothesis" in response.json()["reply"].lower()


def test_disable_proactive_insights_prevents_generation(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Keep 09:00 tomorrow.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Multiple alarms may reinforce snoozing",
                    "summary": "Multiple alarms seem to make snoozing easier for you.",
                    "evidence": [
                        "You mentioned snoozing repeatedly.",
                        "Many alarms did not help."
                    ],
                    "confidence": "high",
                    "suggested_experiment": "For the next 3 mornings, use one main alarm at 09:00 and one backup at 09:10 only."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    trace_repo = AdviceTraceRepository(str(tmp_path / "api.db"))
    for index in range(5):
        trace_repo.create_trace(
            user_id="default_user",
            session_id="s1",
            user_message=f"I snoozed again {index}",
            assistant_reply="Reply.",
            source_memory_ids=[],
            knowledge_card_ids=[],
            safety_category="A",
            is_private_mode=False,
        )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        disabled = client.post("/chat", json={"message": "Don't give me proactive insights."})
        response = client.post("/chat", json={"message": "I snoozed again and feel groggy."})

    assert disabled.status_code == 200
    assert response.status_code == 200
    assert "One useful pattern" not in response.json()["reply"]


def test_turn_insights_back_on_allows_proactive_generation(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Keep 09:00 tomorrow.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Multiple alarms may reinforce snoozing",
                    "summary": "Multiple alarms seem to make snoozing easier for you.",
                    "evidence": [
                        "You mentioned snoozing repeatedly.",
                        "Many alarms did not help."
                    ],
                    "confidence": "high",
                    "suggested_experiment": "For the next 3 mornings, use one main alarm at 09:00 and one backup at 09:10 only."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    trace_repo = AdviceTraceRepository(str(tmp_path / "api.db"))
    for index in range(5):
        trace_repo.create_trace(
            user_id="default_user",
            session_id="s1",
            user_message=f"I snoozed again {index}",
            assistant_reply="Reply.",
            source_memory_ids=[],
            knowledge_card_ids=[],
            safety_category="A",
            is_private_mode=False,
    )
    chat_service.insight_service.update_preferences(
        InsightPreferenceUpdateRequest(proactive_insights_enabled=False)
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        enabled = client.post("/chat", json={"message": "Turn insights back on."})
        response = client.post("/chat", json={"message": "I snoozed again and feel groggy."})

    assert enabled.status_code == 200
    assert response.status_code == 200
    assert "One useful pattern" in response.json()["reply"]


def test_private_mode_messages_are_not_used_for_insights(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=False,
            insights=[],
            reason_if_none="Not enough evidence.",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        client.post("/memory/disable", json={"session_id": "private-1"})
        client.post(
            "/chat",
            json={"message": "I snoozed again.", "session_id": "private-1"},
        )
        traces = AdviceTraceRepository(str(tmp_path / "api.db")).list_recent_traces(
            "default_user",
            include_private=False,
        )

    assert traces == []


def test_safety_red_flag_content_is_not_turned_into_casual_insight(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Please speak to a healthcare professional.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Possible sleep apnea pattern",
                    "summary": "You likely have sleep apnea.",
                    "evidence": ["You wake up gasping."],
                    "confidence": "medium",
                    "suggested_experiment": "Track this daily."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I wake up gasping at night."})

    assert response.status_code == 200
    assert "One useful pattern" not in response.json()["reply"]


def test_experiment_feedback_updates_worked_before_memory(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Morning light may help",
                    "summary": "Morning light may make it easier for you to wake at 09:00.",
                    "evidence": [
                        "You mentioned groggy mornings.",
                        "Morning light is supported by a knowledge card."
                    ],
                    "confidence": "medium",
                    "suggested_experiment": "Try getting bright light within 10 minutes of waking for the next 3 mornings."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        first = client.post("/chat", json={"message": "What should I experiment with this week?"})
        second = client.post("/chat", json={"message": "That experiment helped."})

    assert first.status_code == 200
    assert second.status_code == 200
    assert any(
        memory.type == "worked_before" and "bright light" in memory.content.lower()
        for memory in chat_service.memory_service.list_memories(include_archived=True)
    )


def test_dismissed_insight_is_not_repeatedly_shown(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Multiple alarms may reinforce snoozing",
                    "summary": "Multiple alarms seem to make snoozing easier for you.",
                    "evidence": [
                        "You mentioned snoozing repeatedly.",
                        "Many alarms did not help."
                    ],
                    "confidence": "high",
                    "suggested_experiment": "For the next 3 mornings, use one main alarm at 09:00 and one backup at 09:10 only."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        first = client.post("/chat", json={"message": "What patterns do you notice?"})
        dismiss = client.post("/chat", json={"message": "Dismiss this insight."})
        third = client.post("/chat", json={"message": "Why do you think that?"})

    assert first.status_code == 200
    assert dismiss.status_code == 200
    assert third.status_code == 200
    assert "specific advice" in third.json()["reply"].lower() or "recent insight" in third.json()["reply"].lower()


def test_why_do_you_think_that_explains_insight_evidence(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Reply.",
        insight_generation=InsightGenerationResult(
            should_create_insight=True,
            insights=[
                {
                    "title": "Multiple alarms may reinforce snoozing",
                    "summary": "Multiple alarms seem to make snoozing easier for you.",
                    "evidence": [
                        "You have mentioned snoozing several times.",
                        "Many alarms did not help."
                    ],
                    "confidence": "high",
                    "suggested_experiment": "For the next 3 mornings, use one main alarm at 09:00 and one backup at 09:10 only."
                }
            ],
            reason_if_none="",
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        client.post("/chat", json={"message": "What patterns do you notice?"})
        response = client.post("/chat", json={"message": "Why do you think that?"})

    assert response.status_code == 200
    assert "because" in response.json()["reply"].lower()
    assert "confident" in response.json()["reply"].lower() or "working pattern" in response.json()["reply"].lower()


def test_why_did_you_recommend_that_uses_recent_trace(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Avoid a late nap and keep your 09:00 wake time tomorrow."),
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        first = client.post(
            "/chat",
            json={
                "message": "I slept badly and want to nap late today.",
                "session_id": "s1",
            },
        )
        second = client.post(
            "/chat",
            json={
                "message": "Why did you recommend that?",
                "session_id": "s1",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "09:00" in second.json()["reply"]
    assert "general sleep guidance" in second.json()["reply"].lower()


def test_dont_remember_this_prevents_memory_saving_for_turn(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService(
            "Reply.",
            extraction=MemoryExtractionResult(
                memory_updates=[
                    {
                        "action": "create",
                        "type": "preference",
                        "content": "User wants detailed explanations.",
                        "confidence": 0.9,
                        "reason": "Explicit request.",
                    }
                ],
                ignored=[],
            ),
        ),
    )
    before = len(chat_service.memory_service.list_memories(include_archived=True))
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Don't remember this"})

    after = len(chat_service.memory_service.list_memories(include_archived=True))
    assert response.status_code == 200
    assert "won't save anything from this exchange" in response.json()["reply"]
    assert before == after


def test_session_private_mode_disables_memory_across_turns(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService(
            "Reply.",
            extraction=MemoryExtractionResult(
                memory_updates=[
                    {
                        "action": "create",
                        "type": "preference",
                        "content": "User wants detailed explanations.",
                        "confidence": 0.9,
                        "reason": "Explicit request.",
                    }
                ],
                ignored=[],
            ),
        ),
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        disabled = client.post(
            "/memory/disable",
            json={"session_id": "private-1"},
        )
        response = client.post(
            "/chat",
            json={
                "message": "I want more detailed explanations.",
                "session_id": "private-1",
            },
        )
        enabled = client.post(
            "/memory/enable",
            json={"session_id": "private-1"},
        )

    assert disabled.status_code == 200
    assert response.status_code == 200
    assert enabled.status_code == 200
    assert not any(
        "more detailed explanations" in memory.content.lower()
        for memory in chat_service.memory_service.list_memories(include_archived=True)
    )


def test_sensitive_memory_requires_confirmation_before_saving(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService(
            "Reply.",
            extraction=MemoryExtractionResult(
                memory_updates=[
                    {
                        "action": "create",
                        "type": "pattern",
                        "content": "User reported possible breathing-related sleep concerns; avoid treating this as a routine sleep hygiene issue.",
                        "confidence": 0.8,
                        "sensitivity": "sensitive",
                        "should_ask_user_before_saving": True,
                        "reason": "Medical-adjacent safety note.",
                    }
                ],
                ignored=[],
            ),
        ),
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        first = client.post(
            "/chat",
            json={
                "message": "I wake up gasping.",
                "session_id": "confirm-1",
            },
        )
        second = client.post(
            "/chat",
            json={
                "message": "yes",
                "session_id": "confirm-1",
            },
        )

    assert first.status_code == 200
    assert "Do you want me to remember this for future sleep advice?" in first.json()["reply"]
    assert second.status_code == 200
    assert "saved that for future sleep advice" in second.json()["reply"]


def test_normal_chat_response_hides_debug_metadata(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Keep 09:00 tomorrow and use morning light."),
        debug_metadata_allowed=True,
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service, app_env="development")
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I snoozed again."})

    assert response.status_code == 200
    assert "debug" not in response.json()


def test_dev_chat_response_can_include_debug_metadata(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Keep 09:00 tomorrow and use morning light."),
        debug_metadata_allowed=True,
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service, app_env="development")
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I snoozed again.", "include_debug": True},
        )

    assert response.status_code == 200
    assert response.json()["debug"]["memory_ids"]
    assert response.json()["debug"]["knowledge_card_ids"]
    assert "User goal:" in response.json()["debug"]["personalization_context"]
    assert response.json()["debug"]["safety_category"] == "A"
    assert response.json()["debug"]["should_prioritize_immediate_safety"] is False


def test_production_chat_response_suppresses_debug_metadata(monkeypatch, tmp_path):
    chat_service = build_chat_service(
        tmp_path,
        StubOpenAIService("Keep 09:00 tomorrow and use morning light."),
        debug_metadata_allowed=False,
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service, app_env="production")
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I snoozed again.", "include_debug": True},
        )

    assert response.status_code == 200
    assert "debug" not in response.json()


def test_normal_late_bedtime_is_category_a(monkeypatch, tmp_path):
    openai_service = StubOpenAIService("Keep 09:00 tomorrow.")
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I went to bed late yesterday. What should I do?"},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "A"


def test_a_few_bad_nights_is_category_b(monkeypatch, tmp_path):
    openai_service = StubOpenAIService("We can keep this simple today.")
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I have been sleeping badly for a few days."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "B"


def test_wake_up_gasping_is_category_c(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I cannot diagnose this, but waking up gasping is worth discussing with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I wake up gasping at night."})

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "C"
    assert "healthcare professional" in response.json()["reply"]


def test_partner_says_stop_breathing_is_category_c(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I cannot diagnose this, but possible breathing pauses during sleep are worth discussing with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "My partner says I stop breathing in my sleep."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "C"


def test_insomnia_for_four_weeks_is_category_c(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I cannot diagnose this, but insomnia lasting weeks is something to discuss with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I have had insomnia for 4 weeks."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "C"


def test_dangerous_sleepiness_while_driving_is_category_d(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "This sounds like an immediate safety issue. Do not drive while this sleepy. Please contact local emergency services or urgent support now."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I almost fell asleep while driving."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "D"
    assert "09:00" not in response.json()["reply"]


def test_self_harm_language_is_category_d(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "This sounds like an immediate safety issue. Please contact local emergency services or a crisis support line now."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I feel hopeless and I do not want to live."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "D"


def test_medication_dosage_question_does_not_get_dosage_advice(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I cannot recommend medication doses. Medication effects on sleep can vary, so it is best to discuss this with a clinician or pharmacist."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "What melatonin dose should I take for sleep?"},
        )

    assert response.status_code == 200
    assert "dose" in response.json()["reply"].lower()
    assert "clinician or pharmacist" in response.json()["reply"].lower()
    assert "mg" not in response.json()["reply"].lower()


def test_alcohol_as_sleep_aid_is_not_recommended(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I would not use alcohol as a sleep aid. If you are relying on it to sleep, it would be worth discussing that with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Should I use alcohol to fall asleep tonight?"},
        )

    assert response.status_code == 200
    assert "would not use alcohol as a sleep aid" in response.json()["reply"].lower()


def test_safety_category_overrides_personalization(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "Even if a longer nap feels helpful short term, waking up gasping is something worth discussing with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    chat_service.memory_service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Long naps helped the user recover after poor sleep.",
            confidence=0.9,
            source="manual",
            positive_count=2,
        )
    )
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I wake up gasping and want the quickest fix for tomorrow."},
        )

    assert response.status_code == 200
    assert openai_service.last_safety_classification.category == "C"
    assert "healthcare professional" in response.json()["reply"]


def test_assistant_does_not_expose_raw_classifier_json(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "I cannot diagnose this, but this is worth discussing with a healthcare professional."
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I wake up gasping."})

    assert response.status_code == 200
    assert "assistant_guidance" not in response.json()["reply"]
    assert "red_flags" not in response.json()["reply"]


def test_sensitive_crisis_details_are_not_saved_as_memory(monkeypatch, tmp_path):
    openai_service = StubOpenAIService(
        "This sounds like an immediate safety issue. Please contact local emergency services or a crisis support line now.",
        extraction=MemoryExtractionResult(
            memory_updates=[
                {
                    "action": "create",
                    "type": "pattern",
                    "content": "User wants to die after poor sleep.",
                    "confidence": 0.8,
                    "reason": "Sensitive crisis detail that should not persist.",
                }
            ],
            ignored=[],
        ),
    )
    chat_service = build_chat_service(tmp_path, openai_service)
    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "I want to die and I cannot keep going."},
        )

    assert response.status_code == 200
    assert all(
        "want to die" not in memory.content.lower()
        for memory in chat_service.memory_service.list_memories(include_archived=True)
    )


def test_memory_summary_does_not_expose_raw_json_or_ids(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.post("/chat", json={"message": "Show my memory."})

    assert response.status_code == 200
    assert '"id"' not in response.json()["reply"]
    assert "{" not in response.json()["reply"]
