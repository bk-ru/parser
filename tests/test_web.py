from __future__ import annotations

import logging
from typing import Any

from fastapi.testclient import TestClient

import site_parser.api.web as web


def _create_client(monkeypatch: Any) -> TestClient:
    monkeypatch.setenv("SITE_PARSER_TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
    app = web.create_app()
    return TestClient(app)


def test_parse_endpoint_applies_overrides(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_parse_site(start_url: str, *, settings: Any) -> dict[str, Any]:
        captured["start_url"] = start_url
        captured["settings"] = settings
        return {"url": "https://example.com", "emails": [], "phones": [], "diagnostics": {"foo": "bar"}}

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
    assert response.json() == {"url": "https://example.com", "emails": [], "phones": []}


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


def test_logs_endpoints_return_and_clear_logs(monkeypatch: Any) -> None:
    client = _create_client(monkeypatch)
    client.post("/api/logs/clear")

    logging.getLogger("site_parser.http").info("test log entry")
    response = client.get("/api/logs")

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert any("test log entry" in item["message"] for item in payload["items"])

    clear_response = client.post("/api/logs/clear")
    assert clear_response.status_code == 200

    response_after_clear = client.get("/api/logs")
    assert response_after_clear.status_code == 200
    assert response_after_clear.json()["items"] == []


def test_parse_emits_live_logs_with_default_level(monkeypatch: Any) -> None:
    def fake_parse_site(start_url: str, *, settings: Any) -> dict[str, Any]:
        return {"url": start_url, "emails": [], "phones": []}

    monkeypatch.setattr(web, "parse_site", fake_parse_site)
    client = _create_client(monkeypatch)
    client.post("/api/logs/clear")

    response = client.post("/api/parse", json={"url": "https://example.com"})
    assert response.status_code == 200

    logs_payload = client.get("/api/logs").json()
    messages = [item["message"] for item in logs_payload["items"]]
    assert any("Запрос парсинга" in message for message in messages)
