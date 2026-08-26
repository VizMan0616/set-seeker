import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SESSION_COOKIE_NAME = "setseeker_session"
SESSION_COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60  # ~10 years: effectively permanent


class SessionMiddleware(BaseHTTPMiddleware):
    """Issues/reads the anonymous long-lived session cookie (ADR 0007).

    Cookie-only: never touches the database. Persistence of the session row
    happens lazily via repository.user_data when something actually stores data.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        is_new = not session_id
        if is_new:
            session_id = uuid.uuid4().hex

        request.state.session_id = session_id
        response = await call_next(request)

        if is_new:
            response.set_cookie(
                SESSION_COOKIE_NAME,
                session_id,
                max_age=SESSION_COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
            )
        return response
