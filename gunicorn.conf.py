"""Gunicorn production settings and Prometheus worker lifecycle hook."""

from prometheus_client import multiprocess

bind = "0.0.0.0:8000"
workers = 2
accesslog = "-"
timeout = 60
graceful_timeout = 30


def child_exit(_server, worker) -> None:  # type: ignore[no-untyped-def]
    """Mark dead workers so multiprocess gauges exclude their stale files."""
    multiprocess.mark_process_dead(worker.pid)
