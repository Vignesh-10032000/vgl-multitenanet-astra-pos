"""Structured JSON logging for the whole process."""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import Processor


def configure_logging(*, level: str = "INFO") -> None:
    """Route ALL logging — structlog and stdlib — through one JSON pipeline.

    WHY one pipeline: gunicorn, SQLAlchemy and Celery log via stdlib. A single
    ``ProcessorFormatter`` keeps every line JSON with the same bound context
    (request_id, user_id, company_id), so log aggregation never has to parse
    two formats or correlate across them.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    # Replace, don't append: configure_logging runs once per create_app call and
    # duplicate handlers would double every log line in tests.
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
