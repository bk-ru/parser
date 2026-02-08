from __future__ import annotations

from urllib.parse import SplitResult, urlsplit, urlunsplit


def strip_www(hostname: str) -> str:
    """Удаляет префикс www у доменного имени."""
    host = hostname.strip().lower()
    if host.startswith("www."):
        return host[4:]
    return host


def hostname_key(url: str) -> str:
    """Возвращает нормализованный ключ домена для сравнения."""
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        raise ValueError(f"URL hostname is missing: {url!r}")
    return strip_www(hostname)


def origin(url: str) -> str:
    """Возвращает origin (scheme://host[:port])."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"URL is not absolute: {url!r}")
    return f"{parts.scheme}://{parts.netloc}"


def normalize_url(url: str, *, include_query: bool) -> str:
    """Нормализует URL для дедупликации."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {parts.scheme!r}")

    hostname = parts.hostname
    if not hostname:
        raise ValueError(f"URL hostname is missing: {url!r}")

    hostname = hostname.lower()
    port = parts.port
    has_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if (port is None or has_default_port) else f"{hostname}:{port}"
    path = parts.path or "/"
    query = parts.query if include_query else ""
    normalized = SplitResult(scheme, netloc, path, query, "").geturl()
    return urlunsplit(urlsplit(normalized))


def is_same_domain(url: str, *, base_hostname_key: str) -> bool:
    """Проверяет, что URL относится к тому же домену."""
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return False
    return strip_www(host) == base_hostname_key


def infer_phone_region(url: str) -> str:
    """Пытается определить регион телефона по TLD домена."""
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        return "ZZ"

    tld = hostname.strip(".").split(".")[-1].lower()
    mapping: dict[str, str] = {
        "ru": "RU",
        "by": "BY",
        "kz": "KZ",
        "ua": "UA",
        "kg": "KG",
        "uz": "UZ",
        "am": "AM",
        "az": "AZ",
        "ge": "GE",
        "md": "MD",
        "ee": "EE",
        "lv": "LV",
        "lt": "LT",
        "pl": "PL",
        "de": "DE",
        "fr": "FR",
        "it": "IT",
        "es": "ES",
        "pt": "PT",
        "nl": "NL",
        "be": "BE",
        "ch": "CH",
        "at": "AT",
        "se": "SE",
        "no": "NO",
        "fi": "FI",
        "dk": "DK",
        "ie": "IE",
        "uk": "GB",
        "gb": "GB",
        "us": "US",
        "ca": "CA",
        "au": "AU",
        "nz": "NZ",
        "jp": "JP",
        "cn": "CN",
        "in": "IN",
    }

    return mapping.get(tld, "ZZ")
