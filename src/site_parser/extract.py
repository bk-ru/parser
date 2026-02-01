from __future__ import annotations

import html
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
    """Извлекает значения href из ссылок."""
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


def extract_emails(
    text: str, *, allowlist: Iterable[str] | None = None, soup: BeautifulSoup | None = None
) -> set[str]:
    """Извлекает и валидирует e‑mail адреса из текста и mailto."""
    allowed_domains = _normalize_email_domains(allowlist)
    emails = {_normalize_email(c, allowed_domains=allowed_domains) for c in _iter_emails_from_text(text)}
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
                emails.add(_normalize_email(address, allowed_domains=allowed_domains))
        emails.update(_extract_cloaked_emails(soup, allowed_domains))
    return {email for email in emails if email}


def extract_phones(text: str, *, regions: Iterable[str] | None, soup: BeautifulSoup | None = None) -> set[str]:
    """Извлекает телефонные номера, используя phonenumbers."""
    phones: set[str] = set()
    effective_regions = _normalize_regions(regions)

    for region in effective_regions:
        for m in PhoneNumberMatcher(text, region, leniency=Leniency.VALID):
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
                parsed = _parse_phone_with_regions(normalized, effective_regions)
                if parsed is None:
                    continue

            if parsed and _is_valid(parsed):
                phones.add(_format_phone(parsed))
    return phones


def _iter_emails_from_text(text: str) -> Iterable[str]:
    """Итерирует кандидатов e‑mail из текста по regex."""
    for match in _EMAIL_RE.finditer(text):
        yield match.group(0).strip(".,;:()[]<>\"'")


def _parse_mailto(href: str) -> str | None:
    """Возвращает e‑mail из mailto-ссылки."""
    raw = href.split(":", 1)[1]
    raw = raw.split("?", 1)[0]
    raw = unquote(raw)
    first = raw.split(",", 1)[0].strip()
    return first or None


def _extract_cloaked_emails(soup: BeautifulSoup, allowed_domains: tuple[str, ...]) -> set[str]:
    """Извлекает e‑mail из типичных JS‑обфускаций (например, Joomla)."""
    emails: set[str] = set()
    for script in soup.find_all("script"):
        script_text = script.string if script.string is not None else script.get_text()
        if not script_text:
            continue
        if "cloak" not in script_text and "addy" not in script_text:
            continue
        variables: dict[str, str] = {}
        for statement in _split_js_statements(script_text):
            statement = statement.strip()
            if not statement:
                continue
            match = re.match(r"(?:var\s+)?(addy_text[a-z0-9]+|addy[a-z0-9]+)\s*=\s*(.+)", statement, re.I)
            if not match:
                continue
            var_name = match.group(1)
            expr = match.group(2)
            value = _eval_js_concat(expr, variables)
            if value:
                variables[var_name] = value
                if "@" in value:
                    normalized = _normalize_email(value, allowed_domains=allowed_domains)
                    if normalized:
                        emails.add(normalized)
    return emails


def _eval_js_concat(expr: str, variables: dict[str, str]) -> str:
    """Простейшая обработка JS‑конкатенации строк и известных переменных."""
    tokens = []
    token_re = re.compile(
        r"'([^'\\\\]*(?:\\\\.[^'\\\\]*)*)'|\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"|([A-Za-z_][A-Za-z0-9_]*)"
    )
    for match in token_re.finditer(expr):
        literal = match.group(1) or match.group(2)
        ident = match.group(3)
        if literal is not None:
            literal = literal.replace("\\\\'", "'").replace("\\\\\\\\", "\\\\")
            tokens.append(html.unescape(literal))
        elif ident is not None:
            tokens.append(variables.get(ident, ""))
    return "".join(tokens)


def _split_js_statements(text: str) -> list[str]:
    """Разбивает JS на выражения, игнорируя ';' внутри строк."""
    parts: list[str] = []
    buffer: list[str] = []
    in_string = False
    escape = False
    quote_char = ""
    for ch in text:
        if in_string:
            buffer.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
        else:
            if ch in ("'", '"'):
                in_string = True
                quote_char = ch
                buffer.append(ch)
            elif ch == ";":
                parts.append("".join(buffer))
                buffer = []
            else:
                buffer.append(ch)
    if buffer:
        parts.append("".join(buffer))
    return parts


def _parse_tel(href: str) -> str | None:
    """Возвращает телефон из tel-ссылки."""
    raw = href.split(":", 1)[1]
    raw = raw.split("?", 1)[0]
    raw = raw.split(";", 1)[0]
    raw = unquote(raw).strip()
    return raw or None


def _normalize_email(candidate: str, *, allowed_domains: tuple[str, ...]) -> str | None:
    """Нормализует и валидирует e‑mail адрес."""
    value = candidate.strip()
    if not value:
        return None
    try:
        normalized = validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        return None
    normalized = normalized.lower()
    if allowed_domains and not _domain_allowed(normalized, allowed_domains):
        return None
    return normalized


def _iter_idd_candidates(text: str) -> Iterable[str]:
    """Ищет кандидатов с международным префиксом 00/011."""
    for match in _IDD_CANDIDATE_RE.finditer(text):
        normalized = _normalize_idd_prefix(match.group(1))
        if normalized.startswith("+"):
            yield normalized


def _normalize_idd_prefix(raw: str) -> str:
    """Заменяет международный префикс 00/011 на '+'."""
    value = raw.strip()
    if not value:
        return value
    return re.sub(r"^(?:00|011)", "+", value)


def _parse_phone(raw: str, *, region: str) -> phonenumbers.PhoneNumber | None:
    """Парсит телефон с указанным регионом."""
    try:
        return phonenumbers.parse(raw, region=region or "ZZ")
    except phonenumbers.NumberParseException:
        return None


def _parse_phone_with_regions(raw: str, regions: tuple[str, ...]) -> phonenumbers.PhoneNumber | None:
    """Пробует распарсить телефон по списку регионов."""
    if not regions:
        return None
    for region in regions:
        parsed = _parse_phone(raw, region=region)
        if parsed and _is_valid(parsed):
            return parsed
    return None


def _is_valid(number: phonenumbers.PhoneNumber) -> bool:
    """Проверяет валидность телефона."""
    return phonenumbers.is_possible_number(number) and phonenumbers.is_valid_number(number)


def _format_phone(number: phonenumbers.PhoneNumber) -> str:
    """Форматирует телефон в E.164."""
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def is_probably_parseable_href(href: str) -> bool:
    """Фильтрует href со служебными схемами."""
    lowered = href.strip().lower()
    if not lowered:
        return False
    schemes = {"mailto", "tel", "javascript", "data"}
    parts = urlsplit(lowered)
    if parts.scheme and parts.scheme in schemes:
        return False
    return True


def _normalize_regions(regions: Iterable[str] | None) -> tuple[str, ...]:
    """Нормализует список регионов (например RU, BY)."""
    if not regions:
        return ()
    normalized = []
    for region in regions:
        if not region:
            continue
        cleaned = str(region).strip().upper()
        if cleaned and cleaned != "ZZ":
            normalized.append(cleaned)
    return tuple(dict.fromkeys(normalized))


def _normalize_email_domains(allowlist: Iterable[str] | None) -> tuple[str, ...]:
    """Нормализует домены для allowlist."""
    if not allowlist:
        return ()
    normalized = []
    for item in allowlist:
        if not item:
            continue
        cleaned = str(item).strip().lower().lstrip("@").lstrip(".")
        if cleaned:
            normalized.append(cleaned)
    return tuple(dict.fromkeys(normalized))


def _domain_allowed(email: str, allowlist: tuple[str, ...]) -> bool:
    """Проверяет, разрешён ли домен e‑mail."""
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower()
    for suffix in allowlist:
        if domain == suffix or domain.endswith(f".{suffix}"):
            return True
    return False
