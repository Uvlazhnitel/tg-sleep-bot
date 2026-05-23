import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import initialize_database
from app.core.exceptions import MemoryNotFoundError, MissingConfigurationError, UpstreamServiceError
from app.repositories.memory_repository import MemoryRepository
from app.services.knowledge_service import KnowledgeService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.require_openai_api_key()
    initialize_database(settings.database_path)
    MemoryService(
        repository=MemoryRepository(settings.database_path),
        user_id=settings.default_user_id,
    ).ensure_seed_memories()
    KnowledgeService(settings.knowledge_cards_path).list_knowledge_cards()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sleep Assistant Chatbot API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(MissingConfigurationError)
    async def handle_missing_configuration(
        request: Request, exc: MissingConfigurationError
    ) -> JSONResponse:
        logger.error("Missing configuration for %s: %s", request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(UpstreamServiceError)
    async def handle_upstream_error(
        request: Request, exc: UpstreamServiceError
    ) -> JSONResponse:
        logger.warning("Upstream OpenAI error for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "Upstream model request failed."},
        )

    @app.exception_handler(MemoryNotFoundError)
    async def handle_memory_not_found(
        request: Request, exc: MemoryNotFoundError
    ) -> JSONResponse:
        logger.warning("Memory not found for %s: %s", request.url.path, exc)
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unexpected error for %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )

    app.include_router(router)
    return app


app = create_app()
