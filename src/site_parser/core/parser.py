from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from site_parser.config.settings import ParserSettings
from site_parser.core.extract import extract_emails, extract_links, extract_phones, is_probably_parseable_href
from site_parser.core.focus import url_priority_score
from site_parser.core.urls import hostname_key, infer_phone_region, is_same_domain, normalize_url, origin
from site_parser.infra.http_client import HttpClient

logger = logging.getLogger("site_parser")


@dataclass(frozen=True)
class ParseResult:
    """Результат парсинга: базовый URL и найденные контакты."""
    url: str
    emails: list[str]
    phones: list[str]
    diagnostics: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Возвращает результат в виде словаря."""
        payload = {"url": self.url, "emails": self.emails, "phones": self.phones}
        if self.diagnostics is not None:
            payload["diagnostics"] = self.diagnostics
        return payload

    def as_json(self, *, ensure_ascii: bool = False, indent: int | None = None) -> str:
        """Сериализует результат в JSON-строку."""
        return json.dumps(self.as_dict(), ensure_ascii=ensure_ascii, indent=indent)


class SiteParser:
    """Парсер сайта одного домена."""

    def __init__(self, settings: ParserSettings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._http_client = HttpClient(settings, session=session)

    def parse(self, start_url: str, *, include_diagnostics: bool = False) -> ParseResult:
        """Обходит сайт и возвращает найденные e‑mail и телефоны."""
        started_at = time.monotonic()
        logger.info("Старт парсинга: %s", start_url)
        normalized_start = normalize_url(start_url, include_query=self._settings.include_query)
        base_hostname = hostname_key(normalized_start)
        configured_regions = self._settings.phone_regions
        if configured_regions:
            phone_regions = tuple(r for r in configured_regions if r and r.strip().upper() != "ZZ")
            inferred_regions = False
        else:
            inferred = infer_phone_region(normalized_start)
            phone_regions = (inferred,) if inferred != "ZZ" else ()
            inferred_regions = True

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
        fetched_ok = 0
        fetched_failed = 0
        processed_pages = 0
        skipped_soup_parse = 0
        links_examined = 0
        links_enqueued = 0
        max_depth_reached = 0
        failure_reasons: dict[str, int] = defaultdict(int)
        stop_reason = "completed"

        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            while frontier or in_flight:
                if time.monotonic() > deadline:
                    logger.info("Stopping crawl by max_seconds=%s", self._settings.max_seconds)
                    stop_reason = "max_seconds"
                    break

                while frontier and len(in_flight) < max_concurrency and scheduled < self._settings.max_pages:
                    _, depth, _, url = heappop(frontier)
                    future = executor.submit(self._http_client.fetch, url)
                    in_flight[future] = (url, depth)
                    scheduled += 1

                if not in_flight:
                    if frontier and scheduled >= self._settings.max_pages:
                        stop_reason = "max_pages"
                    break

                timeout = max(0.0, deadline - time.monotonic())
                done, _ = wait(in_flight.keys(), timeout=timeout, return_when=FIRST_COMPLETED)
                if not done:
                    stop_reason = "max_seconds"
                    break

                for future in done:
                    url, depth = in_flight.pop(future)
                    max_depth_reached = max(max_depth_reached, depth)
                    try:
                        outcome = future.result()
                    except Exception as exc:
                        logger.debug("Fetch error for %s: %s", url, exc)
                        fetched_failed += 1
                        failure_reasons["future_exception"] += 1
                        continue
                    if not outcome.ok or outcome.page is None:
                        fetched_failed += 1
                        failure_reasons[outcome.reason] += 1
                        continue

                    fetched_ok += 1
                    page = outcome.page
                    if url == normalized_start:
                        effective_start = page.final_url
                        base_hostname = hostname_key(effective_start)
                        if inferred_regions:
                            inferred = infer_phone_region(effective_start)
                            phone_regions = (inferred,) if inferred != "ZZ" else ()

                    soup = _safe_soup(page.text)
                    if soup is None:
                        skipped_soup_parse += 1
                        continue

                    processed_pages += 1
                    page_text = soup.get_text(" ", strip=True)
                    emails.update(extract_emails(page_text, allowlist=self._settings.email_domain_allowlist, soup=soup))
                    phones.update(extract_phones(page_text, regions=phone_regions, soup=soup))

                    if depth >= self._settings.max_depth:
                        continue

                    candidates: list[str] = []
                    for href in extract_links(soup)[: self._settings.max_links_per_page]:
                        links_examined += 1
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
                        links_enqueued += 1
                        heappush(frontier, (self._priority(normalized), depth + 1, next(sequence), normalized))

        if stop_reason == "completed" and frontier and not in_flight and scheduled >= self._settings.max_pages:
            stop_reason = "max_pages"
        duration = round(time.monotonic() - started_at, 3)
        diagnostics = None
        if include_diagnostics:
            diagnostics = {
                "stop_reason": stop_reason,
                "duration_seconds": duration,
                "limits": {
                    "max_pages": self._settings.max_pages,
                    "max_depth": self._settings.max_depth,
                    "max_seconds": self._settings.max_seconds,
                },
                "counters": {
                    "scheduled_pages": scheduled,
                    "fetched_pages": fetched_ok,
                    "failed_pages": fetched_failed,
                    "processed_pages": processed_pages,
                    "skipped_soup_parse": skipped_soup_parse,
                    "discovered_urls": len(discovered),
                    "links_examined": links_examined,
                    "links_enqueued": links_enqueued,
                    "frontier_remaining": len(frontier),
                    "max_depth_reached": max_depth_reached,
                },
                "failure_reasons": dict(sorted(failure_reasons.items())),
                "contacts_found": {
                    "emails": len(emails),
                    "phones": len(phones),
                },
            }

        logger.info(
            "Финиш парсинга: emails=%s phones=%s pages=%s duration=%.3fs",
            len(emails),
            len(phones),
            scheduled,
            duration,
        )

        return ParseResult(
            url=origin(effective_start),
            emails=sorted(emails),
            phones=sorted(phones),
            diagnostics=diagnostics,
        )

    def _priority(self, url: str) -> int:
        """Возвращает приоритет URL для фокусированного обхода."""
        if not self._settings.focused_crawling:
            return 0
        return url_priority_score(url)


def parse_site(
    start_url: str,
    *,
    settings: ParserSettings | None = None,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Упрощённый API: парсинг сайта одним вызовом."""
    effective_settings = settings or ParserSettings.from_env_and_file()
    return SiteParser(effective_settings).parse(start_url, include_diagnostics=include_diagnostics).as_dict()


def _safe_soup(text: str) -> BeautifulSoup | None:
    """Парсит HTML в BeautifulSoup, возвращает None при ошибке."""
    try:
        return BeautifulSoup(text, "html.parser")
    except Exception as exc:
        logger.debug("Soup parse error: %s", exc)
    return None
