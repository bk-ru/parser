from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


def _coerce_bool(value: Any) -> bool:
    """Приводит значение к bool с валидацией."""
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError("Boolean value is missing")
    text = str(value).strip().lower()
    truthy = {"1", "true", "yes", "y", "on"}
    falsy = {"0", "false", "no", "n", "off"}
    if text in truthy:
        return True
    if text in falsy:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _read_config_file(path: Path) -> dict[str, Any]:
    """Читает конфиг из TOML или JSON."""
    if not path.exists():
        raise FileNotFoundError(str(path))

    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("parser"), dict):
            return dict(data["parser"])
        return dict(data)
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    raise ValueError(f"Unsupported config file format: {suffix}")


@dataclass(frozen=True)
class ParserSettings:
    """Настройки парсера с поддержкой env и файла."""
    max_pages: int = 200
    max_depth: int = 5
    max_seconds: float = 30.0
    max_concurrency: int = 4
    request_timeout: float = 10.0
    user_agent: str = "site-parser/0.1.0"
    include_query: bool = False
    phone_regions: tuple[str, ...] | None = None
    email_domain_allowlist: tuple[str, ...] | None = None
    focused_crawling: bool = True
    max_body_bytes: int = 2_000_000
    max_links_per_page: int = 200
    retry_total: int = 2
    retry_backoff_factor: float = 0.5
    log_level: str = "INFO"

    @classmethod
    def from_env_and_file(cls, config_path: str | None = None) -> ParserSettings:
        """Загружает настройки из файла и переменных окружения."""
        file_path = config_path or os.environ.get("PARSER_CONFIG_FILE") or os.environ.get("PARSER_CONFIG")

        data: dict[str, Any] = {}
        if file_path:
            data.update(_read_config_file(Path(file_path)))

        data.update(_read_settings_from_env(os.environ))
        if "phone_regions" in data:
            data["phone_regions"] = _normalize_regions(data.get("phone_regions"))
        if "email_domain_allowlist" in data:
            data["email_domain_allowlist"] = _normalize_domain_suffixes(data.get("email_domain_allowlist"))
        return cls(**_filter_known_fields(cls, data))


def _filter_known_fields(settings_cls: type[ParserSettings], data: dict[str, Any]) -> dict[str, Any]:
    """Оставляет только поля, определённые в ParserSettings."""
    known = {field_name for field_name in settings_cls.__dataclass_fields__.keys()}
    return {k: v for k, v in data.items() if k in known}


def _read_settings_from_env(environ: dict[str, str]) -> dict[str, Any]:
    """Читает настройки из переменных окружения."""
    mapping: dict[str, tuple[str, Any]] = {
        "max_pages": ("PARSER_MAX_PAGES", int),
        "max_depth": ("PARSER_MAX_DEPTH", int),
        "max_seconds": ("PARSER_MAX_SECONDS", float),
        "max_concurrency": ("PARSER_MAX_CONCURRENCY", int),
        "request_timeout": ("PARSER_REQUEST_TIMEOUT", float),
        "user_agent": ("PARSER_USER_AGENT", str),
        "include_query": ("PARSER_INCLUDE_QUERY", _coerce_bool),
        "phone_regions": ("PARSER_PHONE_REGIONS", str),
        "email_domain_allowlist": ("PARSER_EMAIL_DOMAIN_ALLOWLIST", str),
        "focused_crawling": ("PARSER_FOCUSED_CRAWLING", _coerce_bool),
        "max_body_bytes": ("PARSER_MAX_BODY_BYTES", int),
        "max_links_per_page": ("PARSER_MAX_LINKS_PER_PAGE", int),
        "retry_total": ("PARSER_RETRY_TOTAL", int),
        "retry_backoff_factor": ("PARSER_RETRY_BACKOFF_FACTOR", float),
        "log_level": ("PARSER_LOG_LEVEL", str),
    }

    result: dict[str, Any] = {}
    for field_name, (env_name, caster) in mapping.items():
        raw = environ.get(env_name)
        if raw is None or raw == "":
            continue
        result[field_name] = caster(raw)

    if "phone_regions" not in result:
        fallback_region = environ.get("PARSER_PHONE_DEFAULT_REGION")
        if fallback_region:
            result["phone_regions"] = fallback_region
    return result


def _normalize_regions(value: Any) -> tuple[str, ...] | None:
    """Нормализует список регионов для телефонов."""
    if value is None:
        return None
    parts: list[str] = []
    if isinstance(value, str):
        raw_parts = value.replace(";", ",").split(",")
        parts.extend(raw_parts)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if item is None:
                continue
            parts.append(str(item))
    else:
        parts.append(str(value))

    normalized = []
    for part in parts:
        cleaned = str(part).strip().upper()
        if cleaned:
            normalized.append(cleaned)

    deduped = tuple(dict.fromkeys(normalized))
    return deduped or None


def _normalize_domain_suffixes(value: Any) -> tuple[str, ...] | None:
    """Нормализует список доменных суффиксов e‑mail."""
    if value is None:
        return None
    parts: list[str] = []
    if isinstance(value, str):
        raw_parts = value.replace(";", ",").split(",")
        parts.extend(raw_parts)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if item is None:
                continue
            parts.append(str(item))
    else:
        parts.append(str(value))

    normalized = []
    for part in parts:
        cleaned = str(part).strip().lower().lstrip("@").lstrip(".")
        if cleaned:
            normalized.append(cleaned)

    deduped = tuple(dict.fromkeys(normalized))
    return deduped or None
