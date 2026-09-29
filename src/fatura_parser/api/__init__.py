"""Public interface for the HTTP API package."""

from fatura_parser.api.app import DEFAULT_ALLOWED_ORIGINS, app, create_app
from fatura_parser.api.auth_routes import SESSION_COOKIE_NAME


__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "SESSION_COOKIE_NAME",
    "app",
    "create_app",
]
