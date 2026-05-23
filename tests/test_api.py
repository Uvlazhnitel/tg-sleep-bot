from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import get_chat_service
from app.core.config import get_settings
from app.main import create_app
from app.models.extractor import MemoryExtractionResult
from app.models.memory import MemoryCreateRequest
from app.repositories.memory_repository import MemoryRepository
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService


class StubOpenAIService:
    def __init__(self, reply: str = "Test reply", extraction: MemoryExtractionResult | None = None):
        self.reply = reply
        self.extraction = extraction or MemoryExtractionResult(memory_updates=[], ignored=[])
        self.last_memories = []

    def generate_assistant_reply(self, message, history, relevant_memories):
        self.last_memories = relevant_memories
        return self.reply

    def extract_memory_updates(self, user_message, assistant_reply, relevant_memories):
        return self.extraction


class FailingExtractorOpenAIService(StubOpenAIService):
    def extract_memory_updates(self, user_message, assistant_reply, relevant_memories):
        from app.core.exceptions import UpstreamServiceError

        raise UpstreamServiceError("extractor failed")


def build_client(monkeypatch, tmp_path, chat_service=None):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    get_settings.cache_clear()

    app = create_app()
    if chat_service is not None:
        app.dependency_overrides[get_chat_service] = lambda: chat_service
    return app


def test_health_check(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_memory_returns_seeded_memories(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.get("/memory")

    assert response.status_code == 200
    assert len(response.json()["memories"]) >= 6


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


def test_chat_memory_summary_intent(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.post("/chat", json={"message": "What do you remember about me?"})

    assert response.status_code == 200
    assert "Here is what I currently remember about you" in response.json()["reply"]


def test_chat_forget_intent_archives_matching_memory(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.post("/chat", json={"message": "Forget that I often snooze alarms."})
        assert response.status_code == 200

        memories = client.get("/memory").json()["memories"]

    assert "I forgot this memory" in response.json()["reply"]
    assert all("snoozing alarms" not in memory["content"] for memory in memories)


def test_chat_update_goal_intent(monkeypatch, tmp_path):
    with TestClient(build_client(monkeypatch, tmp_path)) as client:
        response = client.post(
            "/chat", json={"message": "Change my wake-up goal to 08:30."}
        )
        memories = client.get("/memory").json()["memories"]

    assert response.status_code == 200
    assert "08:30" in response.json()["reply"]
    assert any(memory["type"] == "fixed_goal" and "08:30" in memory["content"] for memory in memories)


def test_chat_includes_relevant_memory_context(monkeypatch, tmp_path):
    repository = MemoryRepository(str(tmp_path / "service.db"))
    memory_service = MemoryService(repository, "default_user")
    memory_service.ensure_seed_memories()
    memory_service.create_memory(
        MemoryCreateRequest(
            type="worked_before",
            content="Morning light helped the user get out of bed.",
            confidence=0.9,
            source="manual",
        )
    )
    openai_service = StubOpenAIService("Try morning light again.")
    chat_service = ChatService(memory_service=memory_service, openai_service=openai_service)

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I am struggling to get out of bed."})

    assert response.status_code == 200
    assert any("Morning light helped" in memory.content for memory in openai_service.last_memories)


def test_chat_returns_reply_when_memory_extraction_fails(monkeypatch, tmp_path):
    repository = MemoryRepository(str(tmp_path / "service.db"))
    memory_service = MemoryService(repository, "default_user")
    memory_service.ensure_seed_memories()
    chat_service = ChatService(
        memory_service=memory_service,
        openai_service=FailingExtractorOpenAIService("Still keep 09:00 tomorrow."),
    )

    app = build_client(monkeypatch, tmp_path, chat_service=chat_service)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "I slept badly."})

    assert response.status_code == 200
    assert response.json()["reply"] == "Still keep 09:00 tomorrow."
