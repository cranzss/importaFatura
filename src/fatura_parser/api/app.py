"""Create and configure the FastAPI application."""

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned when the API is available."""

    status: str


def create_app() -> FastAPI:
    """Build one configured FastAPI application instance."""
    application = FastAPI(
        title="Fatura Parser API",
        description="API local para importar e consultar faturas.",
        version="0.1.0",
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
