from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_api_key
from app.errors import register_exception_handlers
from tests.conftest import TEST_API_KEY

# No protected router exists yet, so the dependency is exercised on a throwaway app.
# Once /podcasts lands these tests move to the real route.
_router = APIRouter(dependencies=[Depends(require_api_key)])


@_router.get("/protected")
def protected() -> dict[str, bool]:
    return {"ok": True}


_app = FastAPI()
register_exception_handlers(_app)
_app.include_router(_router)
_client = TestClient(_app)


def test_missing_api_key_returns_401() -> None:
    response = _client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthenticated", "message": "Missing or invalid API key"}
    }


def test_wrong_api_key_returns_401() -> None:
    response = _client.get("/protected", headers={"X-API-Key": "nope"})

    assert response.status_code == 401


def test_valid_api_key_is_accepted() -> None:
    response = _client.get("/protected", headers={"X-API-Key": TEST_API_KEY})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_key_scheme_is_documented_in_openapi() -> None:
    schemes = _app.openapi()["components"]["securitySchemes"]

    assert schemes["APIKeyHeader"] == {"type": "apiKey", "in": "header", "name": "X-API-Key"}
