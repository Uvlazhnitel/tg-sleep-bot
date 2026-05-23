from app.core.config import get_settings
from app.models.chat import ChatResponse, HistoryMessage
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.integration_repository import IntegrationRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.pending_memory_confirmation_repository import (
    PendingMemoryConfirmationRepository,
)
from app.repositories.reminder_repository import ReminderRepository
from app.repositories.session_state_repository import SessionStateRepository
from app.repositories.settings_repository import SettingsRepository
from app.services.chat_service import ChatService
from app.services.insight_service import InsightService
from app.services.integration_service import CalendarService, HealthDataService
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
from app.services.openai_client import OpenAIResponseService
from app.services.reminder_service import ReminderService
from app.services.safety_classifier import SafetyClassifierService
from app.services.settings_service import SettingsService


def build_memory_service_for_user(user_id: str) -> MemoryService:
    settings = get_settings()
    repository = MemoryRepository(settings.database_path)
    service = MemoryService(repository=repository, user_id=user_id)
    service.ensure_seed_memories()
    return service


def build_knowledge_service() -> KnowledgeService:
    settings = get_settings()
    return KnowledgeService(settings.knowledge_cards_path)


def build_chat_service_for_user(user_id: str) -> ChatService:
    settings = get_settings()
    memory_service = build_memory_service_for_user(user_id)
    knowledge_service = build_knowledge_service()
    memory_transparency_service = MemoryTransparencyService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        advice_trace_repository=AdviceTraceRepository(settings.database_path),
        session_state_repository=SessionStateRepository(settings.database_path),
        pending_confirmation_repository=PendingMemoryConfirmationRepository(
            settings.database_path
        ),
    )
    openai_service = OpenAIResponseService(settings)
    settings_service = SettingsService(
        repository=SettingsRepository(settings.database_path, settings.default_timezone),
        insight_repository=InsightRepository(settings.database_path),
        user_id=user_id,
    )
    integration_repository = IntegrationRepository(settings.database_path)
    insight_service = InsightService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        openai_service=openai_service,
        advice_trace_repository=AdviceTraceRepository(settings.database_path),
        insight_repository=InsightRepository(settings.database_path),
    )
    return ChatService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        openai_service=openai_service,
        safety_classifier=SafetyClassifierService(),
        memory_transparency_service=memory_transparency_service,
        insight_service=insight_service,
        settings_service=settings_service,
        reminder_service=ReminderService(
            repository=ReminderRepository(settings.database_path),
            user_id=user_id,
        ),
        calendar_service=CalendarService(
            repository=integration_repository,
            user_id=user_id,
        ),
        health_data_service=HealthDataService(
            repository=integration_repository,
            user_id=user_id,
        ),
        debug_metadata_allowed=settings.debug_metadata_allowed,
    )


def generate_chat_reply(
    user_id: str,
    message: str,
    history: list[HistoryMessage] | None = None,
    session_id: str | None = None,
    include_debug: bool = False,
) -> ChatResponse:
    chat_service = build_chat_service_for_user(user_id)
    return chat_service.generate_reply(
        message=message,
        history=history or [],
        session_id=session_id,
        include_debug=include_debug,
    )
