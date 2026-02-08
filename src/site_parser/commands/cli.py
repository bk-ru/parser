from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace

from site_parser.config.settings import ParserSettings
from site_parser.core.parser import parse_site
from site_parser.infra.safe_logging import sanitize_for_log

logger = logging.getLogger("site_parser.cli")


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    args = _parse_args(argv)
    settings = ParserSettings.from_env_and_file(args.config)
    if args.log_level:
        settings = replace(settings, log_level=args.log_level)

    _configure_logging(settings.log_level)
    logger.debug("Эффективные настройки CLI: %s", sanitize_for_log(settings))

    try:
        result = parse_site(args.start_url, settings=settings)
    except ValueError as exc:
        logging.getLogger("site_parser").error("%s", exc)
        return 2

    indent = 2 if args.pretty else None
    json.dump(result, sys.stdout, ensure_ascii=False, indent=indent)
    sys.stdout.write("\n")
    return 0


def _configure_logging(log_level: str) -> None:
    """Настраивает логирование приложения."""
    level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Парсит аргументы командной строки."""
    parser = argparse.ArgumentParser(prog="site-parser")
    parser.add_argument("start_url")
    parser.add_argument("--config")
    parser.add_argument("--log-level")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)
