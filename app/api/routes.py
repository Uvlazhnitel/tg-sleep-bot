from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.models.chat import ChatRequest, ChatResponse, HealthResponse
from app.models.integration import (
    IntegrationConnectRequest,
    IntegrationSummaryResponse,
)
from app.models.insight import (
    InsightPreferenceRecord,
    InsightPreferenceUpdateRequest,
    InsightRecord,
    InsightSummaryResponse,
    InsightUpdateRequest,
)
from app.models.memory_control import MemorySessionStateRecord, MemorySessionToggleRequest
from app.models.memory import (
    MemoryCreateRequest,
    MemoryFeedbackRequest,
    MemoryRecord,
    MemorySummaryResponse,
    MemoryUpdateRequest,
)
from app.models.reminder import (
    DueReminderResponse,
    ReminderCreateRequest,
    ReminderRecord,
    ReminderSummaryResponse,
    ReminderUpdateRequest,
)
from app.models.settings import FeatureListResponse, UserSettingsRecord, UserSettingsUpdateRequest
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.integration_repository import IntegrationRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.pending_memory_confirmation_repository import (
    PendingMemoryConfirmationRepository,
)
from app.repositories.reminder_repository import ReminderRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.session_state_repository import SessionStateRepository
from app.services.chat_service import ChatService
from app.services.chat_runtime import (
    build_chat_service_for_user,
    build_knowledge_service,
    build_memory_service_for_user,
)
from app.services.integration_service import CalendarService, HealthDataService
from app.services.insight_service import InsightService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
from app.services.reminder_service import ReminderService
from app.services.settings_service import SettingsService
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


def get_memory_service() -> MemoryService:
    settings = get_settings()
    return build_memory_service_for_user(settings.default_user_id)


def get_knowledge_service() -> KnowledgeService:
    return build_knowledge_service()


def get_chat_service(
    _: MemoryService = Depends(get_memory_service),
    __: KnowledgeService = Depends(get_knowledge_service),
) -> ChatService:
    settings = get_settings()
    return build_chat_service_for_user(settings.default_user_id)


def get_insight_service(
    memory_service: MemoryService = Depends(get_memory_service),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> InsightService:
    settings = get_settings()
    return InsightService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        openai_service=OpenAIResponseService(settings),
        advice_trace_repository=AdviceTraceRepository(settings.database_path),
        insight_repository=InsightRepository(settings.database_path),
    )


def get_settings_service() -> SettingsService:
    settings = get_settings()
    return SettingsService(
        repository=SettingsRepository(settings.database_path, settings.default_timezone),
        insight_repository=InsightRepository(settings.database_path),
        user_id=settings.default_user_id,
    )


def get_reminder_service() -> ReminderService:
    settings = get_settings()
    return ReminderService(
        repository=ReminderRepository(settings.database_path),
        user_id=settings.default_user_id,
    )


def get_calendar_service() -> CalendarService:
    settings = get_settings()
    return CalendarService(
        repository=IntegrationRepository(settings.database_path),
        user_id=settings.default_user_id,
    )


def get_health_data_service() -> HealthDataService:
    settings = get_settings()
    return HealthDataService(
        repository=IntegrationRepository(settings.database_path),
        user_id=settings.default_user_id,
    )


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return chat_service.generate_reply(
        message=payload.message,
        history=payload.history,
        session_id=payload.session_id,
        include_debug=payload.include_debug,
    )


@router.get("/memory", response_model=MemorySummaryResponse)
def list_memory(
    include_archived: bool = Query(default=False),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemorySummaryResponse:
    memories = memory_service.list_memories(include_archived=include_archived)
    return MemorySummaryResponse(memories=memories)


@router.post("/memory", response_model=MemoryRecord)
def create_memory(
    payload: MemoryCreateRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return memory_service.create_memory(payload)


@router.patch("/memory/{memory_id}", response_model=MemoryRecord)
def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return memory_service.update_memory(memory_id, payload)


@router.delete("/memory/{memory_id}", response_model=MemoryRecord)
def delete_memory(
    memory_id: str,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return memory_service.archive_memory(memory_id)


@router.post("/memory/feedback", response_model=MemoryRecord)
def feedback_memory(
    payload: MemoryFeedbackRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return memory_service.apply_feedback(payload.memory_id, payload.feedback)


@router.post("/memory/disable", response_model=MemorySessionStateRecord)
def disable_memory(
    payload: MemorySessionToggleRequest,
) -> MemorySessionStateRecord:
    settings = get_settings()
    memory_service = get_memory_service()
    knowledge_service = get_knowledge_service()
    service = MemoryTransparencyService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        advice_trace_repository=AdviceTraceRepository(settings.database_path),
        session_state_repository=SessionStateRepository(settings.database_path),
        pending_confirmation_repository=PendingMemoryConfirmationRepository(
            settings.database_path
        ),
    )
    return service.set_memory_disabled_for_session(payload.session_id, enabled=False)


@router.post("/memory/enable", response_model=MemorySessionStateRecord)
def enable_memory(
    payload: MemorySessionToggleRequest,
) -> MemorySessionStateRecord:
    settings = get_settings()
    memory_service = get_memory_service()
    knowledge_service = get_knowledge_service()
    service = MemoryTransparencyService(
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        advice_trace_repository=AdviceTraceRepository(settings.database_path),
        session_state_repository=SessionStateRepository(settings.database_path),
        pending_confirmation_repository=PendingMemoryConfirmationRepository(
            settings.database_path
        ),
    )
    return service.set_memory_disabled_for_session(payload.session_id, enabled=True)


@router.get("/insights", response_model=InsightSummaryResponse)
def list_insights(
    include_archived: bool = Query(default=False),
    insight_service: InsightService = Depends(get_insight_service),
) -> InsightSummaryResponse:
    return InsightSummaryResponse(
        insights=insight_service.list_insights(include_archived=include_archived)
    )


@router.patch("/insights/{insight_id}", response_model=InsightRecord)
def update_insight(
    insight_id: str,
    payload: InsightUpdateRequest,
    insight_service: InsightService = Depends(get_insight_service),
) -> InsightRecord:
    updated = insight_service.insight_repository.update_insight(
        insight_id,
        insight_service.memory_service.user_id,
        payload,
    )
    return updated


@router.post("/insights/preferences", response_model=InsightPreferenceRecord)
def update_insight_preferences(
    payload: InsightPreferenceUpdateRequest,
    insight_service: InsightService = Depends(get_insight_service),
) -> InsightPreferenceRecord:
    return insight_service.update_preferences(payload)


@router.get("/settings", response_model=UserSettingsRecord)
def get_settings_endpoint(
    settings_service: SettingsService = Depends(get_settings_service),
) -> UserSettingsRecord:
    return settings_service.get_user_settings()


@router.patch("/settings", response_model=UserSettingsRecord)
def update_settings_endpoint(
    payload: UserSettingsUpdateRequest,
    settings_service: SettingsService = Depends(get_settings_service),
) -> UserSettingsRecord:
    return settings_service.update_user_settings(payload)


@router.get("/settings/features", response_model=FeatureListResponse)
def get_enabled_features(
    settings_service: SettingsService = Depends(get_settings_service),
) -> FeatureListResponse:
    return FeatureListResponse(enabled_features=settings_service.list_enabled_features())


@router.post("/settings/features/{feature}/enable", response_model=UserSettingsRecord)
def enable_feature(
    feature: str,
    settings_service: SettingsService = Depends(get_settings_service),
) -> UserSettingsRecord:
    return settings_service.enable_feature(feature)  # type: ignore[arg-type]


@router.post("/settings/features/{feature}/disable", response_model=UserSettingsRecord)
def disable_feature(
    feature: str,
    settings_service: SettingsService = Depends(get_settings_service),
) -> UserSettingsRecord:
    return settings_service.disable_feature(feature)  # type: ignore[arg-type]


@router.get("/reminders", response_model=ReminderSummaryResponse)
def list_reminders(
    reminder_service: ReminderService = Depends(get_reminder_service),
) -> ReminderSummaryResponse:
    return ReminderSummaryResponse(reminders=reminder_service.list_reminders())


@router.post("/reminders", response_model=ReminderRecord)
def create_reminder(
    payload: ReminderCreateRequest,
    reminder_service: ReminderService = Depends(get_reminder_service),
) -> ReminderRecord:
    return reminder_service.create_reminder(payload)


@router.patch("/reminders/{reminder_id}", response_model=ReminderRecord)
def update_reminder(
    reminder_id: str,
    payload: ReminderUpdateRequest,
    reminder_service: ReminderService = Depends(get_reminder_service),
) -> ReminderRecord:
    return reminder_service.update_reminder(reminder_id, payload)


@router.delete("/reminders/{reminder_id}", response_model=ReminderRecord | None)
def delete_reminder(
    reminder_id: str,
    reminder_service: ReminderService = Depends(get_reminder_service),
) -> ReminderRecord | None:
    return reminder_service.delete_reminder(reminder_id)


@router.post("/reminders/send-due", response_model=DueReminderResponse)
def send_due_reminders(
    reminder_service: ReminderService = Depends(get_reminder_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> DueReminderResponse:
    return reminder_service.send_due_reminders(
        settings_service.get_user_settings().notification_quiet_hours
    )


@router.post("/integrations/calendar/connect", response_model=IntegrationSummaryResponse)
def connect_calendar(
    payload: IntegrationConnectRequest,
    calendar_service: CalendarService = Depends(get_calendar_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> IntegrationSummaryResponse:
    calendar_service.connect(payload.provider_name)
    settings_service.enable_feature("calendar")
    return IntegrationSummaryResponse(connections=calendar_service.list_connections())


@router.post("/integrations/calendar/disconnect", response_model=IntegrationSummaryResponse)
def disconnect_calendar(
    calendar_service: CalendarService = Depends(get_calendar_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> IntegrationSummaryResponse:
    calendar_service.disconnect()
    settings_service.disable_feature("calendar")
    return IntegrationSummaryResponse(connections=calendar_service.list_connections())


@router.delete("/integrations/calendar/data", response_model=dict)
def delete_calendar_data(
    calendar_service: CalendarService = Depends(get_calendar_service),
) -> dict:
    return {"detail": calendar_service.delete_data()}


@router.post("/integrations/health/connect", response_model=IntegrationSummaryResponse)
def connect_health(
    payload: IntegrationConnectRequest,
    health_data_service: HealthDataService = Depends(get_health_data_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> IntegrationSummaryResponse:
    timezone = settings_service.get_effective_timezone()
    health_data_service.connect(payload.provider_name, timezone)
    settings_service.enable_feature("health_data")
    return IntegrationSummaryResponse(connections=health_data_service.list_connections())


@router.post("/integrations/health/disconnect", response_model=IntegrationSummaryResponse)
def disconnect_health(
    health_data_service: HealthDataService = Depends(get_health_data_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> IntegrationSummaryResponse:
    health_data_service.disconnect()
    settings_service.disable_feature("health_data")
    return IntegrationSummaryResponse(connections=health_data_service.list_connections())


@router.delete("/integrations/health/data", response_model=dict)
def delete_health_data(
    health_data_service: HealthDataService = Depends(get_health_data_service),
) -> dict:
    deleted = health_data_service.delete_data()
    return {"deleted_count": deleted}
