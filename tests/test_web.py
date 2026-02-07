from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import site_parser.web as web


def _create_client(monkeypatch: Any) -> TestClient:
    monkeypatch.setenv("SITE_PARSER_TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
    app = web.create_app()
    return TestClient(app)


def test_parse_endpoint_applies_overrides(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_parse_site(start_url: str, *, settings: Any) -> dict[str, Any]:
        captured["start_url"] = start_url
        captured["settings"] = settings
        return {"url": "https://example.com", "emails": [], "phones": []}

    monkeypatch.setattr(web, "parse_site", fake_parse_site)
    client = _create_client(monkeypatch)

    response = client.post(
        "/api/parse",
        json={
            "url": "https://example.com",
            "overrides": {
                "max_depth": 0,
                "max_pages": 15,
                "focused_crawling": False,
                "phone_regions": "RU,BY",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.com"
    assert captured["start_url"] == "https://example.com"
    assert captured["settings"].max_depth == 0
    assert captured["settings"].max_pages == 15
    assert captured["settings"].focused_crawling is False
    assert captured["settings"].phone_regions == ("RU", "BY")


def test_parse_endpoint_rejects_unknown_override(monkeypatch: Any) -> None:
    client = _create_client(monkeypatch)
    response = client.post(
        "/api/parse",
        json={
            "url": "https://example.com",
            "overrides": {"unknown_field": 1},
        },
    )

    assert response.status_code == 400
    assert "Неподдерживаемое переопределение" in response.json()["detail"]


def test_parse_endpoint_rejects_invalid_override_value(monkeypatch: Any) -> None:
    client = _create_client(monkeypatch)
    response = client.post(
        "/api/parse",
        json={
            "url": "https://example.com",
            "overrides": {"max_pages": 0},
        },
    )

    assert response.status_code == 400
    assert "max_pages must be between" in response.json()["detail"]
