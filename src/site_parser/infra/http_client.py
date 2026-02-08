from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from site_parser.config.settings import ParserSettings
from site_parser.core.urls import normalize_url

logger = logging.getLogger("site_parser.http")


@dataclass(frozen=True)
class FetchedPage:
    """Нормализованная страница после HTTP-запроса."""

    final_url: str
    text: str


@dataclass(frozen=True)
class FetchOutcome:
    """Результат попытки загрузки страницы."""

    page: FetchedPage | None
    reason: str

    @property
    def ok(self) -> bool:
        return self.page is not None


class HttpClient:
    """HTTP-клиент парсера с retry-политикой и потоковыми сессиями."""

    def __init__(self, settings: ParserSettings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session
        self._local = threading.local()

    def fetch(self, url: str) -> FetchOutcome:
        session = self._get_session()
        headers = {"User-Agent": self._settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
        logger.info("HTTP GET %s", url)
        try:
            with session.get(
                url,
                headers=headers,
                timeout=self._settings.request_timeout,
                allow_redirects=True,
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    logger.info("HTTP %s %s -> status=%s", "GET", url, response.status_code)
                    logger.debug("Skipping %s with status_code=%s", url, response.status_code)
                    return FetchOutcome(page=None, reason="http_status")

                if not _is_allowed_content_type(response.headers.get("Content-Type", "")):
                    logger.info(
                        "HTTP %s %s -> unsupported content-type=%s",
                        "GET",
                        url,
                        response.headers.get("Content-Type", ""),
                    )
                    return FetchOutcome(page=None, reason="content_type")

                body = _read_limited_body(response, self._settings.max_body_bytes)
                text = body.decode(response.encoding or "utf-8", errors="replace")
                final_url = normalize_url(response.url, include_query=self._settings.include_query)
                logger.info("HTTP %s %s -> status=%s", "GET", url, response.status_code)
                return FetchOutcome(page=FetchedPage(final_url=final_url, text=text), reason="ok")
        except ValueError as exc:
            logger.debug("Normalize URL error for %s: %s", url, exc)
            return FetchOutcome(page=None, reason="url_normalize")
        except requests.RequestException as exc:
            logger.debug("Request error for %s: %s", url, exc)
            return FetchOutcome(page=None, reason="request_error")

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        session = getattr(self._local, "session", None)
        if session is None:
            session = _create_session(self._settings)
            self._local.session = session
        return session


def _create_session(settings: ParserSettings) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=settings.retry_total,
        backoff_factor=settings.retry_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _is_allowed_content_type(content_type: str) -> bool:
    value = (content_type or "").lower()
    if not value:
        return True
    allowed = ("text/html", "application/xhtml+xml", "text/plain")
    return any(token in value for token in allowed)


def _read_limited_body(response: requests.Response, max_bytes: int) -> bytes:
    collected = bytearray()
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        collected.extend(chunk)
        if len(collected) > max_bytes:
            logger.debug("Response body exceeded max_body_bytes=%s for %s", max_bytes, response.url)
            break
    return bytes(collected[:max_bytes])
