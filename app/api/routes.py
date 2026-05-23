from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.models.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.openai_client import OpenAIChatService

router = APIRouter()


def get_chat_service() -> OpenAIChatService:
    return OpenAIChatService(get_settings())


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    chat_service: OpenAIChatService = Depends(get_chat_service),
) -> ChatResponse:
    reply = chat_service.generate_reply(
        message=payload.message,
        history=payload.history,
    )
    return ChatResponse(reply=reply)
