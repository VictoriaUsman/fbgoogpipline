"""Structured JSON logging for every Lambda handler, connector, and Glue job in this pipeline.

Nothing in this codebase should call bare `print()` or the stdlib logging default
formatter directly -- `get_logger(__name__)` is the one sanctioned entry point, so
CloudWatch Logs Insights queries can rely on every record being a single JSON object
with a stable set of top-level keys (`level`, `message`, `logger`, plus whatever is
passed via `extra=log_fields(...)`).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

_LOGGERS: list[logging.Logger] = []
_FILE_HANDLER: logging.Handler | None = None


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger configured to emit one JSON object per line to stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _LOGGERS.append(logger)
        if _FILE_HANDLER is not None:
            logger.addHandler(_FILE_HANDLER)
    return logger


def log_fields(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """Build the `extra=` payload for a log call: `logger.info("msg", extra=log_fields(account_id=x))`."""
    return {"fields": kwargs}


def enable_file_logging(log_path: Path | str) -> Path:
    """Attach a JSON file handler at `log_path` to every logger created so far, and to
    every logger `get_logger` creates from now on -- called once from
    `local_runner.run_pipeline.main()` so a full run's structured logs are durable on
    disk (CloudWatch Logs' role in a real deployment), not just printed to stdout and
    lost when the process exits.
    """
    global _FILE_HANDLER
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path)
    handler.setFormatter(_JsonFormatter())
    _FILE_HANDLER = handler
    for logger in _LOGGERS:
        logger.addHandler(handler)
    return path
