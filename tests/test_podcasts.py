import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Podcast


@pytest.fixture
def catalogue(db_session: Session) -> list[Podcast]:
    rows = [
        Podcast(source_id=1, title="Beatles Stories", author="Ann", genre="Music", country="GBR"),
        Podcast(source_id=2, title="Punk Hour", author="Bob", genre="Music", country="USA"),
        Podcast(source_id=3, title="Rock History", author="Cid", genre="History", country="USA"),
        Podcast(source_id=4, title="Metal Talk", author="Dee Beatle", genre="Music", country="usa"),
    ]
    db_session.add_all(rows)
    db_session.flush()
    return rows


def _titles(payload: dict[str, object]) -> list[str]:
    items = payload["items"]
    assert isinstance(items, list)
    return [item["title"] for item in items]


def test_list_is_paginated_and_ordered_by_title(
    client: TestClient, auth_headers: dict[str, str], catalogue: list[Podcast]
) -> None:
    first = client.get("/podcasts", params={"limit": 2}, headers=auth_headers).json()
    second = client.get("/podcasts", params={"limit": 2, "offset": 2}, headers=auth_headers).json()

    assert first["total"] == 4
    assert (first["limit"], first["offset"]) == (2, 0)
    assert _titles(first) == ["Beatles Stories", "Metal Talk"]
    assert _titles(second) == ["Punk Hour", "Rock History"]


def test_list_filters_by_genre_and_country_case_insensitively(
    client: TestClient, auth_headers: dict[str, str], catalogue: list[Podcast]
) -> None:
    response = client.get(
        "/podcasts", params={"genre": "music", "country": "USA"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert _titles(response.json()) == ["Metal Talk", "Punk Hour"]
    assert response.json()["total"] == 2


def test_list_searches_title_and_author(
    client: TestClient, auth_headers: dict[str, str], catalogue: list[Podcast]
) -> None:
    response = client.get("/podcasts", params={"q": "beatle"}, headers=auth_headers)

    assert _titles(response.json()) == ["Beatles Stories", "Metal Talk"]


@pytest.mark.parametrize(
    ("titles", "q", "expected"),
    [
        (["50% Off Rock", "500 Songs"], "50%", ["50% Off Rock"]),
        (["Rock_Talk", "Rock Talk"], "k_T", ["Rock_Talk"]),
    ],
)
def test_list_search_treats_like_wildcards_literally(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    titles: list[str],
    q: str,
    expected: list[str],
) -> None:
    db_session.add_all(Podcast(source_id=i, title=t, author="A") for i, t in enumerate(titles, 1))
    db_session.flush()

    response = client.get("/podcasts", params={"q": q}, headers=auth_headers)

    assert _titles(response.json()) == expected


def test_list_search_ignores_surrounding_whitespace(
    client: TestClient, auth_headers: dict[str, str], catalogue: list[Podcast]
) -> None:
    padded = client.get("/podcasts", params={"q": "  beatle "}, headers=auth_headers).json()
    plain = client.get("/podcasts", params={"q": "beatle"}, headers=auth_headers).json()

    assert _titles(padded) == _titles(plain) == ["Beatles Stories", "Metal Talk"]


@pytest.mark.parametrize("q", ["", "   "])
def test_list_rejects_blank_search(client: TestClient, auth_headers: dict[str, str], q: str) -> None:
    response = client.get("/podcasts", params={"q": q}, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["query", "q"]


def test_list_rejects_invalid_pagination_with_error_envelope(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/podcasts", params={"limit": 0}, headers=auth_headers)

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["loc"] == ["query", "limit"]


def test_get_podcast_returns_all_fields(
    client: TestClient, auth_headers: dict[str, str], catalogue: list[Podcast]
) -> None:
    response = client.get(f"/podcasts/{catalogue[0].id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == 1
    assert body["title"] == "Beatles Stories"
    assert body["color_palette"] is None
    assert body["created_at"] is not None


def test_get_missing_podcast_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/podcasts/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Podcast 999999 not found"}
    }
