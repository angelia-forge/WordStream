from typing import cast

from fastapi import APIRouter, Request, Response

from app.config import AuthMode
from app.dependencies import AccessDep, ConfigDep
from app.exceptions import AppError
from app.schemas.auth import LoginRequest, LoginResponse, SessionResponse
from app.security import LoginRateLimiter, SessionManager, verify_shared_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    config: ConfigDep,
) -> LoginResponse:
    if config.auth_mode is AuthMode.DISABLED:
        raise AppError(
            "AUTH_DISABLED",
            "Authentication is disabled",
            status_code=409,
        )

    client_id = request.client.host if request.client else "unknown"
    limiter = cast(LoginRateLimiter, request.app.state.login_rate_limiter)
    limiter.ensure_allowed(client_id)
    if not verify_shared_password(payload.password, config):
        limiter.record_failure(client_id)
        raise AppError("UNAUTHORIZED", "Invalid credentials", status_code=401)

    limiter.clear(client_id)
    token, session = SessionManager(config).create()
    response.set_cookie(
        config.session_cookie_name,
        token,
        max_age=config.session_max_age_seconds,
        httponly=True,
        secure=config.secure_cookies,
        samesite="lax",
        path="/",
    )
    return LoginResponse(authenticated=True, csrf_token=session.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, config: ConfigDep, _: AccessDep) -> Response:
    response.delete_cookie(
        config.session_cookie_name,
        secure=config.secure_cookies,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.status_code = 204
    return response


@router.get("/session", response_model=SessionResponse)
def session(_: AccessDep) -> SessionResponse:
    return SessionResponse(authenticated=True)
