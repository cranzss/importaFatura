"""Create and configure the FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fatura_parser.api.auth_routes import router as auth_router
from fatura_parser.database import (
    DEFAULT_DATABASE_PATH,
    Database,
    create_database,
)


DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


class HealthResponse(BaseModel):
    """Response returned when the API is available."""

    status: str


def create_app(
    *,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    secure_cookies: bool = False,
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS,
) -> FastAPI:
    """Build one configured FastAPI application instance."""
    if "*" in allowed_origins:
        raise ValueError(
            "credentialed CORS requires explicit allowed origins"
        )

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncIterator[None]:
        database = create_database(database_path)
        application.state.database = database
        try:
            yield
        finally:
            database.close()

    application = FastAPI(
        title="Fatura Parser API",
        description="API local para importar e consultar faturas.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.secure_cookies = secure_cookies
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(auth_router)

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Verificar se a API está disponível",
    )
    def health_check() -> HealthResponse:
        """Confirm that the API process can receive requests."""
        return HealthResponse(status="ok")

    return application


app = create_app()
