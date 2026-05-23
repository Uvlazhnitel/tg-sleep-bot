from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.models.memory import MemoryCreateRequest, MemoryRecord, MemorySummaryResponse, MemoryUpdateRequest
from app.repositories.memory_repository import MemoryRepository
from app.models.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.chat_service import ChatService
from app.services.memory_service import MemoryService
from app.services.openai_client import OpenAIResponseService

router = APIRouter()


def get_memory_service() -> MemoryService:
    settings = get_settings()
    repository = MemoryRepository(settings.database_path)
    return MemoryService(repository=repository, user_id=settings.default_user_id)


def get_chat_service(
    memory_service: MemoryService = Depends(get_memory_service),
) -> ChatService:
    return ChatService(
        memory_service=memory_service,
        openai_service=OpenAIResponseService(get_settings()),
    )


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    reply = chat_service.generate_reply(
        message=payload.message,
        history=payload.history,
    )
    return ChatResponse(reply=reply)


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
