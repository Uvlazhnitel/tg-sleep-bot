import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.exceptions import MissingConfigurationError, UpstreamServiceError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().require_openai_api_key()
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
