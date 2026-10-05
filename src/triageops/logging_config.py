"""
Logging configuration for TriageOps.

Sets up structured JSON logging for production use and
human-readable console logging for development.

Import and call setup_logging() early in the app (CLI entry point, API startup).
"""

import json
import logging
import os
import sys
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)


def setup_logging(json_logs: bool = False) -> None:
    """
    Configure root logger.

    Args:
        json_logs: If True, output JSON lines (for production / log ingestion).
                   If False, output human-readable text (for development).
    """
    level = os.environ.get("TRIAGEOPS_LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)

    if json_logs:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
