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
from typing import Any


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
    return logger


def log_fields(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """Build the `extra=` payload for a log call: `logger.info("msg", extra=log_fields(account_id=x))`."""
    return {"fields": kwargs}
