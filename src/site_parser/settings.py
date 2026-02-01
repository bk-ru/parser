from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


def _coerce_bool(value: Any) -> bool:
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
    max_pages: int = 200
    max_depth: int = 5
    max_seconds: float = 30.0
    max_concurrency: int = 4
    request_timeout: float = 10.0
    user_agent: str = "site-parser/0.1.0"
    include_query: bool = False
    phone_default_region: str | None = None
    focused_crawling: bool = True
    max_body_bytes: int = 2_000_000
    max_links_per_page: int = 200
    retry_total: int = 2
    retry_backoff_factor: float = 0.5
    log_level: str = "INFO"

    @classmethod
    def from_env_and_file(cls, config_path: str | None = None) -> ParserSettings:
        file_path = config_path or os.environ.get("PARSER_CONFIG_FILE") or os.environ.get("PARSER_CONFIG")

        data: dict[str, Any] = {}
        if file_path:
            data.update(_read_config_file(Path(file_path)))

        data.update(_read_settings_from_env(os.environ))
        return cls(**_filter_known_fields(cls, data))


def _filter_known_fields(settings_cls: type[ParserSettings], data: dict[str, Any]) -> dict[str, Any]:
    known = {field_name for field_name in settings_cls.__dataclass_fields__.keys()}
    return {k: v for k, v in data.items() if k in known}


def _read_settings_from_env(environ: dict[str, str]) -> dict[str, Any]:
    mapping: dict[str, tuple[str, Any]] = {
        "max_pages": ("PARSER_MAX_PAGES", int),
        "max_depth": ("PARSER_MAX_DEPTH", int),
        "max_seconds": ("PARSER_MAX_SECONDS", float),
        "max_concurrency": ("PARSER_MAX_CONCURRENCY", int),
        "request_timeout": ("PARSER_REQUEST_TIMEOUT", float),
        "user_agent": ("PARSER_USER_AGENT", str),
        "include_query": ("PARSER_INCLUDE_QUERY", _coerce_bool),
        "phone_default_region": ("PARSER_PHONE_DEFAULT_REGION", str),
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
    return result
