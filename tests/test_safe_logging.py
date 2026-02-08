from __future__ import annotations

from dataclasses import dataclass

from site_parser.infra.safe_logging import sanitize_for_log


@dataclass(frozen=True)
class _SampleConfig:
    api_key: str
    max_pages: int


def test_sanitize_for_log_masks_sensitive_mapping_keys() -> None:
    payload = {
        "api_key": "abcdefghijklmnopqrstuvwxyz",
        "token": "1234567890",
        "max_pages": 20,
    }

    sanitized = sanitize_for_log(payload)

    assert sanitized["max_pages"] == 20
    assert sanitized["api_key"] != payload["api_key"]
    assert sanitized["token"] != payload["token"]
    assert sanitized["api_key"].startswith("abc")
    assert sanitized["api_key"].endswith("yz")


def test_sanitize_for_log_masks_sensitive_dataclass_fields() -> None:
    settings = _SampleConfig(api_key="top-secret-key", max_pages=50)
    sanitized = sanitize_for_log(settings)

    assert sanitized["max_pages"] == 50
    assert sanitized["api_key"] != "top-secret-key"
    assert sanitized["api_key"].startswith("top")
