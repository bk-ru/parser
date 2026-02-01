from __future__ import annotations

import posixpath
import re
from urllib.parse import urlsplit

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_KEYWORD_WEIGHTS: dict[str, int] = {
    "contact": -50,
    "contacts": -50,
    "support": -40,
    "help": -25,
    "about": -20,
    "impressum": -50,
    "legal": -20,
    "privacy": -20,
    "policy": -15,
    "terms": -15,
    "faq": -10,
    "feedback": -10,
    "company": -5,
    "team": -5,
    "docs": 40,
    "doc": 20,
    "spec": 30,
    "rfc": 40,
    "archive": 30,
    "blog": 20,
    "news": 20,
    "press": 20,
    "media": 20,
    "release": 10,
    "releases": 10,
    "changelog": 10,
    "events": 10,
    "jobs": 10,
    "careers": 10,
}

_EXTENSION_WEIGHTS: dict[str, int] = {
    "pdf": 250,
    "zip": 300,
    "7z": 300,
    "rar": 300,
    "tar": 300,
    "gz": 300,
    "bz2": 300,
    "xz": 300,
    "exe": 300,
    "msi": 300,
    "dmg": 300,
    "iso": 300,
    "png": 200,
    "jpg": 200,
    "jpeg": 200,
    "gif": 200,
    "webp": 200,
    "svg": 100,
    "ico": 100,
    "css": 100,
    "js": 100,
    "json": 80,
    "xml": 80,
    "txt": 50,
    "md": 50,
    "rss": 80,
}


def url_priority_score(url: str) -> int:
    """Возвращает приоритет URL для фокусированного обхода (меньше — лучше)."""
    parts = urlsplit(url)
    path = (parts.path or "/").lower()
    query = (parts.query or "").lower()

    tokens = set(_TOKEN_RE.findall(f"{path}?{query}" if query else path))
    score = sum(_KEYWORD_WEIGHTS.get(token, 0) for token in tokens)

    if query:
        score += 10

    segments = [p for p in path.split("/") if p]
    score += min(len(segments), 10)

    ext = posixpath.splitext(path)[1].lstrip(".").lower()
    if ext:
        score += _EXTENSION_WEIGHTS.get(ext, 0)

    if path in {"/", "/index.html", "/index.htm"}:
        score -= 5

    return score
