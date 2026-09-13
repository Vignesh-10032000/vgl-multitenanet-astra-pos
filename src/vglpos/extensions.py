"""Flask extension instances, deliberately uninitialised.

WHY this module exists: blueprints, services and repositories import extension
handles from here without importing the app factory, which prevents circular
imports. ``create_app`` is the only code that calls ``init_app`` — and only
after configuration has been applied (the P0-6 bug class: an extension
initialised before config silently keeps defaults).
"""

from __future__ import annotations

from celery import Celery
from flask_caching import Cache
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all models (SQLAlchemy 2.x typed style)."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)
jwt = JWTManager()
celery = Celery("vglpos")
