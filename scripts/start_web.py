"""Prepare the standalone demo runtime and launch Gunicorn."""

from __future__ import annotations

import os
import secrets
import subprocess


def _set_runtime_defaults() -> None:
    os.environ.setdefault("APP_ENV", "demo")
    os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/vglpos-demo.db")
    for name in (
        "SECRET_KEY",
        "JWT_SECRET_KEY",
        "OFFLINE_SYNC_SIGNING_SECRET",
        "METRICS_AUTH_TOKEN",
    ):
        os.environ.setdefault(name, secrets.token_urlsafe(48))


def main() -> None:
    _set_runtime_defaults()
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    os.execvp("gunicorn", ["gunicorn", "--config", "gunicorn.conf.py", "vglpos.app:create_app()"])


if __name__ == "__main__":
    main()
