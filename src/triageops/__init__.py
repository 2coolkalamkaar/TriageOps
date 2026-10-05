"""TriageOps — DevOps Incident Triage Agent."""

__version__ = "0.1.0"
__author__ = "TriageOps"

from .logging_config import setup_logging

# Set up default (human-readable) logging when the package is imported.
# CLI and API entry points can call setup_logging(json_logs=True) to override.
setup_logging()
