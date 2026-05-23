from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.models.chat import ChatRequest, ChatResponse, HealthResponse
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
from app.repositories.memory_repository import MemoryRepository
from app.repositories.advice_trace_repository import AdviceTraceRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.pending_memory_confirmation_repository import (
    PendingMemoryConfirmationRepository,
)
from app.repositories.session_state_repository import SessionStateRepository
from app.services.chat_service import ChatService
from app.services.knowledge_service import KnowledgeService
from app.services.insight_service import InsightService
from app.services.memory_service import MemoryService
from app.services.memory_transparency_service import MemoryTransparencyService
from app.services.openai_client import OpenAIResponseService
from app.services.safety_classifier import SafetyClassifierService

router = APIRouter()


def get_memory_service() -> MemoryService:
    settings = get_settings()
    repository = MemoryRepository(settings.database_path)
    return MemoryService(repository=repository, user_id=settings.default_user_id)


def get_knowledge_service() -> KnowledgeService:
    settings = get_settings()
    return KnowledgeService(settings.knowledge_cards_path)


def get_chat_service(
    memory_service: MemoryService = Depends(get_memory_service),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> ChatService:
    settings = get_settings()
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
        debug_metadata_allowed=settings.debug_metadata_allowed,
    )


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
