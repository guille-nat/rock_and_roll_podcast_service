from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app


def test_unexpected_exception_uses_error_envelope_without_details(
    auth_headers: dict[str, str],
) -> None:
    def broken_session() -> None:
        raise RuntimeError("connection refused: secret-host")

    app.dependency_overrides[get_session] = broken_session
    try:
        # Starlette re-raises after handling; the client must not propagate it.
        response = TestClient(app, raise_server_exceptions=False).get(
            "/podcasts", headers=auth_headers
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
    assert "secret-host" not in response.text


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
