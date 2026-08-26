from fastapi.testclient import TestClient

from app.main import create_app
from app.sessions import SESSION_COOKIE_NAME


def test_app_boots_and_session_middleware_issues_cookie():
    client = TestClient(create_app())

    first = client.get("/")
    assert first.status_code == 501  # route stub: not yet implemented
    assert first.cookies.get(SESSION_COOKIE_NAME)

    second = client.get("/")
    assert second.status_code == 501
    # Known session: the cookie is not re-issued.
    assert SESSION_COOKIE_NAME not in second.cookies
