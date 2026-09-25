"""Public interface for the HTTP API package."""

from fatura_parser.api.app import app, create_app


__all__ = ["app", "create_app"]
