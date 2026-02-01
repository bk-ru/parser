from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import unquote, urlsplit

import phonenumbers
from bs4 import BeautifulSoup
from email_validator import EmailNotValidError, validate_email
from phonenumbers import Leniency, PhoneNumberMatcher, PhoneNumberFormat

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_IDD_CANDIDATE_RE = re.compile(r"(?:^|[^\d+])((?:00|011)[\s().-]*[1-9](?:[\s().-]*\d){6,})")

def extract_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for tag in soup.find_all(["a", "area"]):
        href = tag.get("href")
        if not href:
            continue
        href = str(href).strip()
        if not href:
            continue
        links.append(href)
    return links


def extract_emails(text: str, *, soup: BeautifulSoup | None = None) -> set[str]:
    emails = {_normalize_email(c) for c in _iter_emails_from_text(text)}
    if soup is not None:
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if not href:
                continue
            href = str(href).strip()
            if not href.lower().startswith("mailto:"):
                continue
            address = _parse_mailto(href)
            if address:
                emails.add(_normalize_email(address))
    return {email for email in emails if email}


def extract_phones(text: str, *, region: str, soup: BeautifulSoup | None = None) -> set[str]:
    phones: set[str] = set()
    effective_region = (region or "").strip().upper()

    if effective_region and effective_region != "ZZ":
        for m in PhoneNumberMatcher(text, effective_region, leniency=Leniency.VALID):
            if _is_valid(m.number):
                phones.add(_format_phone(m.number))

    for m in PhoneNumberMatcher(text, "ZZ", leniency=Leniency.VALID):
        if _is_valid(m.number):
            phones.add(_format_phone(m.number))

    for candidate in _iter_idd_candidates(text):
        parsed = _parse_phone(candidate, region="ZZ")
        if parsed and _is_valid(parsed):
            phones.add(_format_phone(parsed))

    if soup is not None:
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if not href:
                continue
            href = str(href).strip()
            if not href.lower().startswith("tel:"):
                continue
            phone = _parse_tel(href)
            if not phone:
                continue

            normalized = _normalize_idd_prefix(phone)
            if normalized.startswith("+"):
                parsed = _parse_phone(normalized, region="ZZ")
            else:
                if not effective_region or effective_region == "ZZ":
                    continue
                parsed = _parse_phone(normalized, region=effective_region)

            if parsed and _is_valid(parsed):
                phones.add(_format_phone(parsed))
    return phones


def _iter_emails_from_text(text: str) -> Iterable[str]:
    for match in _EMAIL_RE.finditer(text):
        yield match.group(0).strip(".,;:()[]<>\"'")


def _parse_mailto(href: str) -> str | None:
    raw = href.split(":", 1)[1]
    raw = raw.split("?", 1)[0]
    raw = unquote(raw)
    first = raw.split(",", 1)[0].strip()
    return first or None


def _parse_tel(href: str) -> str | None:
    raw = href.split(":", 1)[1]
    raw = raw.split("?", 1)[0]
    raw = raw.split(";", 1)[0]
    raw = unquote(raw).strip()
    return raw or None


def _normalize_email(candidate: str) -> str | None:
    value = candidate.strip()
    if not value:
        return None
    try:
        normalized = validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        return None
    return normalized.lower()


def _iter_idd_candidates(text: str) -> Iterable[str]:
    for match in _IDD_CANDIDATE_RE.finditer(text):
        normalized = _normalize_idd_prefix(match.group(1))
        if normalized.startswith("+"):
            yield normalized


def _normalize_idd_prefix(raw: str) -> str:
    value = raw.strip()
    if not value:
        return value
    return re.sub(r"^(?:00|011)", "+", value)


def _parse_phone(raw: str, *, region: str) -> phonenumbers.PhoneNumber | None:
    try:
        return phonenumbers.parse(raw, region=region or "ZZ")
    except phonenumbers.NumberParseException:
        return None


def _is_valid(number: phonenumbers.PhoneNumber) -> bool:
    return phonenumbers.is_possible_number(number) and phonenumbers.is_valid_number(number)


def _format_phone(number: phonenumbers.PhoneNumber) -> str:
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def is_probably_parseable_href(href: str) -> bool:
    lowered = href.strip().lower()
    if not lowered:
        return False
    schemes = {"mailto", "tel", "javascript", "data"}
    parts = urlsplit(lowered)
    if parts.scheme and parts.scheme in schemes:
        return False
    return True
