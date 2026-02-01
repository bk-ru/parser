from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from heapq import heappop, heappush
from itertools import count
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from site_parser.focus import url_priority_score
from site_parser.extract import extract_emails, extract_links, extract_phones, is_probably_parseable_href
from site_parser.settings import ParserSettings
from site_parser.urls import hostname_key, infer_phone_region, is_same_domain, normalize_url, origin

logger = logging.getLogger("site_parser")


@dataclass(frozen=True)
class ParseResult:
    url: str
    emails: list[str]
    phones: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "emails": self.emails, "phones": self.phones}

    def as_json(self, *, ensure_ascii: bool = False, indent: int | None = None) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=ensure_ascii, indent=indent)


class SiteParser:
    def __init__(self, settings: ParserSettings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session
        self._local = threading.local()

    def parse(self, start_url: str) -> ParseResult:
        normalized_start = normalize_url(start_url, include_query=self._settings.include_query)
        base_hostname = hostname_key(normalized_start)
        phone_region = (self._settings.phone_default_region or "").strip().upper() or infer_phone_region(normalized_start)

        deadline = time.monotonic() + self._settings.max_seconds
        emails: set[str] = set()
        phones: set[str] = set()

        discovered: set[str] = {normalized_start}
        sequence = count()
        frontier: list[tuple[int, int, int, str]] = [(self._priority(normalized_start), 0, next(sequence), normalized_start)]
        effective_start = normalized_start
        max_concurrency = max(1, self._settings.max_concurrency)
        in_flight: dict[Any, tuple[str, int]] = {}
        scheduled = 0

        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            while frontier or in_flight:
                if time.monotonic() > deadline:
                    logger.info("Stopping crawl by max_seconds=%s", self._settings.max_seconds)
                    break

                while frontier and len(in_flight) < max_concurrency and scheduled < self._settings.max_pages:
                    _, depth, _, url = heappop(frontier)
                    future = executor.submit(self._fetch, url)
                    in_flight[future] = (url, depth)
                    scheduled += 1

                if not in_flight:
                    break

                timeout = max(0.0, deadline - time.monotonic())
                done, _ = wait(in_flight.keys(), timeout=timeout, return_when=FIRST_COMPLETED)
                if not done:
                    break

                for future in done:
                    url, depth = in_flight.pop(future)
                    try:
                        page = future.result()
                    except Exception as exc:
                        logger.debug("Fetch error for %s: %s", url, exc)
                        continue
                    if page is None:
                        continue

                    if url == normalized_start:
                        effective_start = page.final_url
                        base_hostname = hostname_key(effective_start)
                        if not (self._settings.phone_default_region or "").strip():
                            phone_region = infer_phone_region(effective_start)

                    soup = _safe_soup(page.text)
                    if soup is None:
                        continue

                    page_text = soup.get_text(" ", strip=True)
                    emails.update(extract_emails(page_text, soup=soup))
                    phones.update(extract_phones(page_text, region=phone_region, soup=soup))

                    if depth >= self._settings.max_depth:
                        continue

                    candidates: list[str] = []
                    for href in extract_links(soup)[: self._settings.max_links_per_page]:
                        if not is_probably_parseable_href(href):
                            continue
                        try:
                            absolute = urljoin(page.final_url, href)
                            normalized = normalize_url(absolute, include_query=self._settings.include_query)
                        except ValueError:
                            continue
                        if not is_same_domain(normalized, base_hostname_key=base_hostname):
                            continue
                        if normalized in discovered:
                            continue
                        candidates.append(normalized)

                    if self._settings.focused_crawling:
                        candidates.sort(key=url_priority_score)

                    for normalized in candidates:
                        if len(discovered) >= self._settings.max_pages:
                            break
                        discovered.add(normalized)
                        heappush(frontier, (self._priority(normalized), depth + 1, next(sequence), normalized))

        return ParseResult(
            url=origin(effective_start),
            emails=sorted(emails),
            phones=sorted(phones),
        )

    def _priority(self, url: str) -> int:
        if not self._settings.focused_crawling:
            return 0
        return url_priority_score(url)

    def _fetch(self, url: str) -> "_FetchedPage | None":
        session = self._get_session()
        headers = {"User-Agent": self._settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
        try:
            with session.get(
                url,
                headers=headers,
                timeout=self._settings.request_timeout,
                allow_redirects=True,
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    logger.debug("Skipping %s with status_code=%s", url, response.status_code)
                    return None
                if not _is_allowed_content_type(response.headers.get("Content-Type", "")):
                    return None
                body = _read_limited_body(response, self._settings.max_body_bytes)
                text = body.decode(response.encoding or "utf-8", errors="replace")
                final_url = normalize_url(response.url, include_query=self._settings.include_query)
                return _FetchedPage(final_url=final_url, text=text)
        except requests.RequestException as exc:
            logger.debug("Request error for %s: %s", url, exc)
            return None

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        session = getattr(self._local, "session", None)
        if session is None:
            session = _create_session(self._settings)
            self._local.session = session
        return session

@dataclass(frozen=True)
class _FetchedPage:
    final_url: str
    text: str

def parse_site(start_url: str, *, settings: ParserSettings | None = None) -> dict[str, Any]:
    effective_settings = settings or ParserSettings.from_env_and_file()
    return SiteParser(effective_settings).parse(start_url).as_dict()

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

def _safe_soup(text: str) -> BeautifulSoup | None:
    try:
        return BeautifulSoup(text, "html.parser")
    except Exception as exc:
        logger.debug("Soup parse error: %s", exc)
        return None

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
