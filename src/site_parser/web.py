from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from site_parser.parser import parse_site
from site_parser.settings import ParserSettings

logger = logging.getLogger("site_parser.web")


class ParseRequest(BaseModel):
    """HTTP-запрос на запуск парсинга."""

    url: str = Field(min_length=1)
    config: str | None = None
    overrides: dict[str, Any] | None = None


def _coerce_bool(value: Any) -> bool:
    """Приводит значение к bool."""

    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError("Boolean value is missing")
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _coerce_float(value: Any, *, name: str, min_value: float, max_value: float) -> float:
    """Приводит и валидирует float-параметр."""

    number = float(value)
    if number < min_value or number > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")
    return number


def _coerce_int(value: Any, *, name: str, min_value: int, max_value: int) -> int:
    """Приводит и валидирует int-параметр."""

    number = int(value)
    if number < min_value or number > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")
    return number


def _coerce_regions(value: Any) -> tuple[str, ...] | None:
    """Нормализует список регионов телефонов."""

    if value is None:
        return None
    parts: list[str] = []
    if isinstance(value, str):
        parts.extend(value.replace(";", ",").split(","))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if item is None:
                continue
            parts.append(str(item))
    else:
        raise ValueError("phone_regions must be string or array")

    normalized = []
    for item in parts:
        cleaned = item.strip().upper()
        if cleaned and cleaned != "ZZ":
            normalized.append(cleaned)
    deduped = tuple(dict.fromkeys(normalized))
    return deduped or None


def _coerce_domain_allowlist(value: Any) -> tuple[str, ...] | None:
    """Нормализует allowlist доменов e-mail."""

    if value is None:
        return None
    parts: list[str] = []
    if isinstance(value, str):
        parts.extend(value.replace(";", ",").split(","))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if item is None:
                continue
            parts.append(str(item))
    else:
        raise ValueError("email_domain_allowlist must be string or array")

    normalized = []
    for item in parts:
        cleaned = item.strip().lower().lstrip("@").lstrip(".")
        if cleaned:
            normalized.append(cleaned)
    deduped = tuple(dict.fromkeys(normalized))
    return deduped or None


def _coerce_log_level(value: Any) -> str:
    """Валидирует уровень логирования."""

    level = str(value).strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Invalid log_level: {value!r}")
    return level


def _coerce_user_agent(value: Any) -> str:
    """Валидирует user-agent."""

    text = str(value).strip()
    if not text:
        raise ValueError("user_agent must not be empty")
    if len(text) > 512:
        raise ValueError("user_agent is too long")
    return text


_OVERRIDE_CASTERS: dict[str, Any] = {
    "max_pages": lambda value: _coerce_int(value, name="max_pages", min_value=1, max_value=5000),
    "max_depth": lambda value: _coerce_int(value, name="max_depth", min_value=0, max_value=50),
    "max_seconds": lambda value: _coerce_float(value, name="max_seconds", min_value=1.0, max_value=3600.0),
    "max_concurrency": lambda value: _coerce_int(value, name="max_concurrency", min_value=1, max_value=64),
    "request_timeout": lambda value: _coerce_float(value, name="request_timeout", min_value=0.5, max_value=120.0),
    "user_agent": _coerce_user_agent,
    "include_query": _coerce_bool,
    "phone_regions": _coerce_regions,
    "email_domain_allowlist": _coerce_domain_allowlist,
    "focused_crawling": _coerce_bool,
    "max_body_bytes": lambda value: _coerce_int(value, name="max_body_bytes", min_value=1024, max_value=50_000_000),
    "max_links_per_page": lambda value: _coerce_int(value, name="max_links_per_page", min_value=1, max_value=5000),
    "retry_total": lambda value: _coerce_int(value, name="retry_total", min_value=0, max_value=10),
    "retry_backoff_factor": lambda value: _coerce_float(
        value,
        name="retry_backoff_factor",
        min_value=0.0,
        max_value=10.0,
    ),
    "log_level": _coerce_log_level,
}


def _apply_overrides(settings: ParserSettings, overrides: dict[str, Any] | None) -> ParserSettings:
    """Применяет переопределения настроек с валидацией."""

    if overrides is None:
        return settings
    if not isinstance(overrides, dict):
        raise ValueError("Поле overrides должно быть объектом")

    normalized: dict[str, Any] = {}
    for key, value in overrides.items():
        caster = _OVERRIDE_CASTERS.get(key)
        if caster is None:
            raise ValueError(f"Неподдерживаемое переопределение: {key}")
        normalized[key] = caster(value)
    return replace(settings, **normalized)


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Читает список значений из env (через запятую)."""

    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    parts = [item.strip() for item in raw.split(",")]
    return tuple(item for item in parts if item)


def create_app() -> FastAPI:
    """Создаёт FastAPI-приложение для UI/API режима."""

    app = FastAPI(title="site-parser API", version="0.1.0")
    trusted_hosts = _env_list("SITE_PARSER_TRUSTED_HOSTS", ("127.0.0.1", "localhost"))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(trusted_hosts))

    cors_origins = _env_list(
        "SITE_PARSER_CORS_ORIGINS",
        (
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Возвращает статус API."""

        return {"status": "ok"}

    @app.post("/api/parse")
    def parse_endpoint(payload: ParseRequest) -> dict[str, Any]:
        """Запускает парсинг сайта и возвращает контакты."""

        start_url = payload.url.strip()
        if not start_url:
            raise HTTPException(status_code=422, detail="url is required")
        try:
            settings = ParserSettings.from_env_and_file(payload.config)
            settings = _apply_overrides(settings, payload.overrides)
            return parse_site(start_url, settings=settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=f"Config file not found: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected parser error")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()


def main() -> None:
    """Запускает API сервер."""

    host = os.environ.get("SITE_PARSER_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SITE_PARSER_API_PORT", "8000"))
    reload_mode = os.environ.get("SITE_PARSER_API_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    workers = int(os.environ.get("SITE_PARSER_API_WORKERS", "1"))
    uvicorn.run(
        "site_parser.web:app",
        host=host,
        port=port,
        reload=reload_mode,
        workers=1 if reload_mode else max(1, workers),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
