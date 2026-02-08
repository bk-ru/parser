from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class _LogEntry:
    id: int
    timestamp: str
    level: str
    logger: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
        }


class InMemoryLogBuffer(logging.Handler):
    """Хранит последние логи в памяти для UI."""

    def __init__(self, *, max_records: int = 3000) -> None:
        super().__init__()
        self._records: deque[_LogEntry] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._next_id = 1
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            self.handleError(record)
            return

        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().strftime("%H:%M:%S")
        with self._lock:
            entry = _LogEntry(
                id=self._next_id,
                timestamp=timestamp,
                level=record.levelname,
                logger=record.name,
                message=message,
            )
            self._records.append(entry)
            self._next_id += 1

    def list(self, *, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        effective_limit = max(1, min(limit, 1000))
        with self._lock:
            items = [entry.as_dict() for entry in self._records if entry.id > after]
        return items[:effective_limit]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._next_id = 1


_buffer = InMemoryLogBuffer()
_install_lock = threading.Lock()
_installed = False


def install_live_log_handler() -> InMemoryLogBuffer:
    """Подключает буфер логов к логгерам приложения один раз."""
    global _installed
    with _install_lock:
        if _installed:
            return _buffer

        logging.getLogger("site_parser").addHandler(_buffer)
        _installed = True
        return _buffer


def get_live_log_buffer() -> InMemoryLogBuffer:
    """Возвращает буфер логов."""
    return _buffer
