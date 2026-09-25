"""Create and configure the FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from fatura_parser.database import (
    DEFAULT_DATABASE_PATH,
    Database,
    create_database,
)


class HealthResponse(BaseModel):
    """Response returned when the API is available."""

    status: str


def create_app(
    *,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> FastAPI:
    """Build one configured FastAPI application instance."""

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
