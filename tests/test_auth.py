from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TEST_API_KEY


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/podcasts")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthenticated", "message": "Missing or invalid API key"}
    }


def test_wrong_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/podcasts", headers={"X-API-Key": "nope"})

    assert response.status_code == 401


def test_valid_api_key_is_accepted(client: TestClient) -> None:
    response = client.get("/podcasts", headers={"X-API-Key": TEST_API_KEY})

    assert response.status_code == 200


def test_api_key_scheme_is_documented_in_openapi() -> None:
    schemes = app.openapi()["components"]["securitySchemes"]

    assert schemes["APIKeyHeader"] == {"type": "apiKey", "in": "header", "name": "X-API-Key"}
