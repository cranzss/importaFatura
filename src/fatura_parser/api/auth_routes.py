"""HTTP endpoints for cookie-based local authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from fatura_parser.api.dependencies import get_database_session
from fatura_parser.auth import (
    DEFAULT_SESSION_LIFETIME,
    authenticate_user,
    create_user_session,
    resolve_session_user,
    revoke_user_session,
)
from fatura_parser.database import User


SESSION_COOKIE_NAME = "fatura_session"
_SESSION_MAX_AGE_SECONDS = int(DEFAULT_SESSION_LIFETIME.total_seconds())
_INVALID_CREDENTIALS_DETAIL = "invalid email or password"
_AUTHENTICATION_REQUIRED_DETAIL = "authentication required"

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class LoginRequest(BaseModel):
    """Credentials accepted by the login endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Non-sensitive user fields safe to return to a client."""

    model_config = ConfigDict(extra="forbid", strict=True)

    email: str


def _secure_cookies_enabled(request: Request) -> bool:
    """Read the environment-specific cookie transport setting."""
    return bool(request.app.state.secure_cookies)


def _set_session_cookie(
    response: Response,
    request: Request,
    token: str,
) -> None:
    """Attach a protected session cookie to a successful response."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookies_enabled(request),
        samesite="strict",
        path="/",
    )


def _delete_session_cookie(response: Response, request: Request) -> None:
    """Expire the browser cookie using the same attributes as login."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=_secure_cookies_enabled(request),
        samesite="strict",
        path="/",
    )


def require_current_user(
    request: Request,
    session: DatabaseSession,
) -> User:
    """Resolve the request cookie or reject unauthenticated access."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = (
        resolve_session_user(session, token)
        if token is not None
        else None
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_AUTHENTICATION_REQUIRED_DETAIL,
        )

    return user


CurrentUser = Annotated[User, Depends(require_current_user)]


@router.post(
    "/login",
    response_model=UserResponse,
    summary="Entrar com e-mail e senha",
)
def login(
    credentials: LoginRequest,
    response: Response,
    request: Request,
    session: DatabaseSession,
) -> UserResponse:
    """Create a server-side session and return its opaque cookie."""
    user = authenticate_user(
        session,
        email=credentials.email,
        password=credentials.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS_DETAIL,
        )

    session_token = create_user_session(session, user_id=user.id)
    session.commit()
    _set_session_cookie(response, request, session_token.value)

    return UserResponse(email=user.email)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Consultar o usuário autenticado",
)
def get_current_user(user: CurrentUser) -> UserResponse:
    """Return the user represented by the current session cookie."""
    return UserResponse(email=user.email)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerrar a sessão atual",
)
def logout(
    request: Request,
    session: DatabaseSession,
) -> Response:
    """Revoke the server-side session and expire the browser cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        revoke_user_session(session, token)
    session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _delete_session_cookie(response, request)
    return response
