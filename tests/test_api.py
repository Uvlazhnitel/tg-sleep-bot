from fastapi.testclient import TestClient

from app.api.routes import get_chat_service
from app.core.config import get_settings
from app.core.exceptions import UpstreamServiceError
from app.main import create_app


class StubChatService:
    def __init__(self, reply: str = "Test reply") -> None:
        self.reply = reply

    def generate_reply(self, message: str, history: list[dict]) -> str:
        return self.reply


class FailingChatService:
    def generate_reply(self, message: str, history: list[dict]) -> str:
        raise UpstreamServiceError("boom")


def build_client(service_override):
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: service_override
    return app


def test_health_check(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    with TestClient(build_client(StubChatService())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_reply(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    with TestClient(build_client(StubChatService("Sleep reply"))) as client:
        response = client.post("/chat", json={"message": "I slept badly."})

    assert response.status_code == 200
    assert response.json() == {"reply": "Sleep reply"}


def test_chat_accepts_history(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    payload = {
        "message": "What should I do tonight?",
        "history": [
            {"role": "user", "content": "I keep snoozing alarms."},
            {"role": "assistant", "content": "Let's anchor your 09:00 wake time."},
        ],
    }

    with TestClient(build_client(StubChatService("Plan for tonight"))) as client:
        response = client.post("/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"reply": "Plan for tonight"}


def test_chat_rejects_invalid_history_role(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    payload = {
        "message": "Hello",
        "history": [{"role": "system", "content": "Invalid"}],
    }

    with TestClient(build_client(StubChatService())) as client:
        response = client.post("/chat", json=payload)

    assert response.status_code == 422


def test_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    with TestClient(build_client(StubChatService())) as client:
        response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422


def test_chat_returns_502_on_upstream_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    with TestClient(build_client(FailingChatService())) as client:
        response = client.post("/chat", json={"message": "I cannot sleep."})

    assert response.status_code == 502
    assert response.json() == {"detail": "Upstream model request failed."}
