from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

_SENSITIVE_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "cookie",
    "authorization",
    "proxy",
)


def sanitize_for_log(value: Any) -> Any:
    """Возвращает значение в безопасном для логов виде."""
    if is_dataclass(value):
        return _sanitize_mapping(asdict(value))
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_log(item) for item in value]
    return value


def _sanitize_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = str(key).strip().lower()
        if _is_sensitive_key(normalized_key):
            sanitized[str(key)] = _mask_value(value)
            continue
        sanitized[str(key)] = sanitize_for_log(value)
    return sanitized


def _is_sensitive_key(key: str) -> bool:
    return any(marker in key for marker in _SENSITIVE_KEY_MARKERS)


def _mask_value(value: Any) -> str:
    if value is None:
        return "***"
    text = str(value).strip()
    if not text:
        return "***"
    if len(text) <= 6:
        return "***"
    return f"{text[:3]}***{text[-2:]}"
