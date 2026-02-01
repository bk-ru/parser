from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest

from site_parser.parser import SiteParser
from site_parser.settings import ParserSettings


@dataclass(frozen=True)
class _ResponseSpec:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"


class _TestServer:
    def __init__(self, routes: dict[str, _ResponseSpec], host: str = "127.0.0.1") -> None:
        self._routes = dict(routes)
        self._requested: list[str] = []

        handler = self._make_handler()
        self._server = ThreadingHTTPServer((host, 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def requested(self) -> list[str]:
        return list(self._requested)

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        routes = self._routes
        requested = self._requested

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requested.append(self.path)
                path = urlsplit(self.path).path
                spec = routes.get(path) or _ResponseSpec(status=404, body="not found", content_type="text/plain")
                body = spec.body.encode("utf-8", errors="replace")
                self.send_response(spec.status)
                self.send_header("Content-Type", spec.content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return Handler


@pytest.fixture()
def test_server() -> _TestServer:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
Root@Example.com
8 (800) 555-35-35
<a href="/contact">contact</a>
<a href="/loop?x=1">loop</a>
</body></html>
""".strip(),
            ),
            "/contact": _ResponseSpec(
                status=200,
                body="""
<html><body>
<a href="mailto:sales@example.com?subject=Hello">mail</a>
<a href="tel:+1 (415) 555-2671">call</a>
</body></html>
""".strip(),
            ),
            "/loop": _ResponseSpec(
                status=200,
                body="""
<html><body>
<a href="/loop?x=2">loop</a>
</body></html>
""".strip(),
            ),
        }
    )
    server.start()
    yield server
    server.stop()


def test_parses_contacts_across_pages(test_server: _TestServer) -> None:
    settings = ParserSettings(
        max_pages=10,
        max_depth=3,
        max_seconds=5.0,
        request_timeout=1.0,
        user_agent="test",
        phone_regions=("RU",),
    )
    result = SiteParser(settings).parse(f"{test_server.base_url}/")

    assert result.url == test_server.base_url
    assert set(result.emails) == {"root@example.com", "sales@example.com"}
    assert set(result.phones) == {"+78005553535", "+14155552671"}


def test_does_not_crawl_other_hostnames() -> None:
    server_b = _TestServer(routes={"/": _ResponseSpec(status=200, body="evil@example.com")})
    server_b.start()

    try:
        external = server_b.base_url.replace("127.0.0.1", "localhost")
        server_a = _TestServer(
            routes={
                "/": _ResponseSpec(
                    status=200,
                body=f"""
<html><body>
a@example.com
<a href="{external}/">external</a>
</body></html>
""".strip(),
                )
            }
        )
        server_a.start()
        try:
            settings = ParserSettings(max_pages=10, max_depth=2, max_seconds=5.0, request_timeout=1.0, user_agent="test")
            result = SiteParser(settings).parse(f"{server_a.base_url}/")
            assert "a@example.com" in result.emails
            assert "evil@example.com" not in result.emails
        finally:
            server_a.stop()
    finally:
        server_b.stop()


def test_invalid_start_url_raises_value_error() -> None:
    settings = ParserSettings(max_pages=1, max_depth=0, max_seconds=1.0, request_timeout=0.1, user_agent="test")
    with pytest.raises(ValueError):
        SiteParser(settings).parse("not-a-url")


def test_filters_invalid_emails_from_text_and_mailto() -> None:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
good@example.com
a@b..com
<a href="mailto:good2%40example.com">good</a>
<a href="mailto:agmalis%26gmail.com">bad</a>
</body></html>
""".strip(),
            )
        }
    )
    server.start()
    try:
        settings = ParserSettings(max_pages=1, max_depth=0, max_seconds=5.0, request_timeout=1.0, user_agent="test")
        result = SiteParser(settings).parse(f"{server.base_url}/")
        assert set(result.emails) == {"good@example.com", "good2@example.com"}
    finally:
        server.stop()


def test_email_domain_allowlist_filters_domains() -> None:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
good@gmail.com
good@mail.ru
nope@yahoo.com
<a href="mailto:admin@sub.mail.ru">sub</a>
</body></html>
""".strip(),
            )
        }
    )
    server.start()
    try:
        settings = ParserSettings(
            max_pages=1,
            max_depth=0,
            max_seconds=5.0,
            request_timeout=1.0,
            user_agent="test",
            email_domain_allowlist=("gmail.com", "mail.ru"),
        )
        result = SiteParser(settings).parse(f"{server.base_url}/")
        assert set(result.emails) == {"good@gmail.com", "good@mail.ru", "admin@sub.mail.ru"}
    finally:
        server.stop()


def test_joomla_cloaked_email_extracted() -> None:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
<span id="cloak123">Адрес электронной почты защищен</span>
<script type="text/javascript">
document.getElementById('cloak123').innerHTML = '';
var addy123 = '&#105;nf&#111;' + '&#64;';
addy123 = addy123 + 'k&#97;gr&#105;f&#111;n' + '&#46;' + 'r&#117;';
var addy_text123 = '&#105;nf&#111;' + '&#64;' + 'k&#97;gr&#105;f&#111;n' + '&#46;' + 'r&#117;';
document.getElementById('cloak123').innerHTML += '<a href=\"mailto:' + addy123 + '\">' + addy_text123 + '</a>';
</script>
</body></html>
""".strip(),
            )
        }
    )
    server.start()
    try:
        settings = ParserSettings(max_pages=1, max_depth=0, max_seconds=5.0, request_timeout=1.0, user_agent="test")
        result = SiteParser(settings).parse(f"{server.base_url}/")
        assert "info@kagrifon.ru" in result.emails
    finally:
        server.stop()


def test_unknown_region_parses_only_international_and_idd() -> None:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
Local: 8 (800) 555-35-35
IDD: 00 7 953 640-53-68
<a href="/contact">contact</a>
</body></html>
""".strip(),
            ),
            "/contact": _ResponseSpec(
                status=200,
                body="""
<html><body>
<a href="tel:02081234567">local</a>
<a href="tel:00 1 415 555 2671">idd</a>
</body></html>
""".strip(),
            ),
        }
    )
    server.start()
    try:
        settings = ParserSettings(max_pages=10, max_depth=2, max_seconds=5.0, request_timeout=1.0, user_agent="test")
        result = SiteParser(settings).parse(f"{server.base_url}/")
        assert set(result.phones) == {"+79536405368", "+14155552671"}
    finally:
        server.stop()


def test_focused_crawling_prioritizes_contact_pages() -> None:
    server = _TestServer(
        routes={
            "/": _ResponseSpec(
                status=200,
                body="""
<html><body>
<a href="/docs">docs</a>
<a href="/contact">contact</a>
</body></html>
""".strip(),
            ),
            "/docs": _ResponseSpec(status=200, body="<html><body>docs</body></html>"),
            "/contact": _ResponseSpec(status=200, body="<html><body>contact@example.com</body></html>"),
        }
    )
    server.start()
    try:
        common = dict(max_pages=2, max_depth=1, max_seconds=5.0, request_timeout=1.0, user_agent="test")
        result_focused = SiteParser(ParserSettings(**common, focused_crawling=True)).parse(f"{server.base_url}/")
        assert "contact@example.com" in result_focused.emails

        result_plain = SiteParser(ParserSettings(**common, focused_crawling=False)).parse(f"{server.base_url}/")
        assert "contact@example.com" not in result_plain.emails
    finally:
        server.stop()


def test_settings_env_overrides_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "parser.toml"
    config_file.write_text("[parser]\nmax_pages = 1\n", encoding="utf-8")
    monkeypatch.setenv("PARSER_MAX_PAGES", "2")
    settings = ParserSettings.from_env_and_file(str(config_file))
    assert settings.max_pages == 2
