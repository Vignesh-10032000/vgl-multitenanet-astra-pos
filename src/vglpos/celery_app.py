"""Celery process entry point: ``celery -A vglpos.celery_app worker``.

WHY this module exists: the celery CLI cannot invoke a factory expression the
way gunicorn can, so this is the one sanctioned place a process-level instance
is built — by calling the factory, per the no-module-level-app rule. Nothing
under ``src/vglpos`` imports this module.
"""

from __future__ import annotations

from celery import Celery

from vglpos.app import create_app

_flask_app = create_app()
celery: Celery = _flask_app.extensions["celery"]
