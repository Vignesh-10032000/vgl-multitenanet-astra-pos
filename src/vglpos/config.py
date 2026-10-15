"""Application configuration via Pydantic Settings.

One class per environment; ``create_app`` receives the class and instantiates
it, so every process (gunicorn worker, celery worker, test session) gets its
configuration from the same validated source instead of scattered ``os.environ``
reads.
"""

from __future__ import annotations

import os
from typing import Any

from celery.schedules import crontab
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.pool import StaticPool

_INSECURE_SECRET_VALUES: frozenset[str] = frozenset(
    {
        "",
        "change-me",
        "change_me",
        "changeme",
        "secret",
        "secret-key",
        "secretkey",
        "password",
        "dev",
        "development",
        "test",
        "testing",
    }
)

# Substrings that mark a value as a committed non-production default from this
# very file; production must refuse them even if someone copies them into env.
_INSECURE_SECRET_MARKERS: tuple[str, ...] = ("not-for-production", "dev-only-", "testing-only-")

_MIN_SECRET_LENGTH = 32


def normalize_database_url(value: str) -> str:
    """Select the installed Psycopg 3 driver for provider PostgreSQL URLs."""
    value = value.strip()
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            return "postgresql+psycopg://" + value[len(prefix) :]
    return value


class BaseConfig(BaseSettings):
    """Settings shared by every environment.

    WHY env-driven: rule 10 forbids hardcoded secrets/hostnames; everything
    here is overridable via environment variables or ``.env``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    DEBUG: bool = False
    TESTING: bool = False
    LOG_LEVEL: str = "INFO"

    SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    OFFLINE_SYNC_SIGNING_SECRET: str = ""
    JWT_ACCESS_TOKEN_EXPIRES: int = 900  # seconds
    JWT_REFRESH_TOKEN_EXPIRES: int = 604_800  # seconds (7 days)
    MFA_ISSUER_NAME: str = "VGL POS"
    WHATSAPP_WEBHOOK_URL: str = ""
    WHATSAPP_API_TOKEN: str = ""
    PUBLIC_RECEIPT_BASE_URL: str = ""
    OFFICIAL_WEBSITE_URL: str = ""
    SMS_WEBHOOK_URL: str = ""
    SMS_API_TOKEN: str = ""
    EMAIL_WEBHOOK_URL: str = ""
    EMAIL_API_TOKEN: str = ""
    EMAIL_FROM: str = ""
    PRODUCT_IMAGE_DIR: str = ""
    REPORT_ARTIFACT_DIR: str = "var/reports"
    METRICS_AUTH_TOKEN: str = ""
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    FEATURE_EINVOICE_ENABLED: bool = True
    FEATURE_EWAY_BILL_ENABLED: bool = True
    FEATURE_REPORT_JOBS_ENABLED: bool = True
    DEMO_MODE_ENABLED: bool = False

    IRP_NIC_AUTH_URL: str = ""
    IRP_NIC_GENERATE_URL: str = ""
    IRP_NIC_LOOKUP_URL: str = ""
    IRP_NIC_CANCEL_URL: str = ""
    IRP_NIC_EWAY_URL: str = ""
    IRP_NIC_USERNAME: str = ""
    IRP_NIC_PASSWORD: str = ""
    IRP_NIC_CLIENT_ID: str = ""
    IRP_NIC_CLIENT_SECRET: str = ""
    COMPLIANCE_ALERT_WEBHOOK_URL: str = ""
    COMPLIANCE_ALERT_API_TOKEN: str = ""

    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    CACHE_TYPE: str = "RedisCache"
    CACHE_DEFAULT_TIMEOUT: int = 300

    RATELIMIT_ENABLED: bool = True
    RATELIMIT_DEFAULT: str = "200 per minute"

    # Empty string means "use REDIS_URL"; separate vars exist so the broker can
    # move off the cache Redis without a code change.
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_driver(cls, value: str) -> str:
        return normalize_database_url(value)

    def _engine_options(self) -> dict[str, Any]:
        """Connection-pool sizing for PostgreSQL.

        WHY pre_ping/recycle: POS terminals sit behind flaky retail networks and
        NAT timeouts; stale pooled connections must be detected, not surfaced as
        checkout errors.
        """
        return {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }

    def flask_config(self) -> dict[str, Any]:
        """Materialise the Flask config mapping.

        WHY explicit keys instead of ``model_dump``: only keys listed here can
        reach ``app.config``, so a new settings field never leaks into Flask (or
        an extension) by accident.
        """
        return {
            "APP_ENV": self.APP_ENV,
            "DEBUG": self.DEBUG,
            "TESTING": self.TESTING,
            "LOG_LEVEL": self.LOG_LEVEL,
            "SECRET_KEY": self.SECRET_KEY,
            "SQLALCHEMY_DATABASE_URI": self.DATABASE_URL,
            "SQLALCHEMY_ENGINE_OPTIONS": self._engine_options(),
            "JWT_SECRET_KEY": self.JWT_SECRET_KEY,
            "OFFLINE_SYNC_SIGNING_SECRET": self.OFFLINE_SYNC_SIGNING_SECRET,
            "JWT_ACCESS_TOKEN_EXPIRES": self.JWT_ACCESS_TOKEN_EXPIRES,
            "JWT_REFRESH_TOKEN_EXPIRES": self.JWT_REFRESH_TOKEN_EXPIRES,
            "MFA_ISSUER_NAME": self.MFA_ISSUER_NAME,
            "WHATSAPP_WEBHOOK_URL": self.WHATSAPP_WEBHOOK_URL,
            "WHATSAPP_API_TOKEN": self.WHATSAPP_API_TOKEN,
            "PUBLIC_RECEIPT_BASE_URL": self.PUBLIC_RECEIPT_BASE_URL,
            "OFFICIAL_WEBSITE_URL": self.OFFICIAL_WEBSITE_URL,
            "SMS_WEBHOOK_URL": self.SMS_WEBHOOK_URL,
            "SMS_API_TOKEN": self.SMS_API_TOKEN,
            "EMAIL_WEBHOOK_URL": self.EMAIL_WEBHOOK_URL,
            "EMAIL_API_TOKEN": self.EMAIL_API_TOKEN,
            "EMAIL_FROM": self.EMAIL_FROM,
            "PRODUCT_IMAGE_DIR": self.PRODUCT_IMAGE_DIR,
            "REPORT_ARTIFACT_DIR": self.REPORT_ARTIFACT_DIR,
            "METRICS_AUTH_TOKEN": self.METRICS_AUTH_TOKEN,
            "SENTRY_DSN": self.SENTRY_DSN,
            "SENTRY_ENVIRONMENT": self.SENTRY_ENVIRONMENT or self.APP_ENV,
            "SENTRY_TRACES_SAMPLE_RATE": self.SENTRY_TRACES_SAMPLE_RATE,
            "FEATURE_EINVOICE_ENABLED": self.FEATURE_EINVOICE_ENABLED,
            "FEATURE_EWAY_BILL_ENABLED": self.FEATURE_EWAY_BILL_ENABLED,
            "FEATURE_REPORT_JOBS_ENABLED": self.FEATURE_REPORT_JOBS_ENABLED,
            "DEMO_MODE_ENABLED": self.DEMO_MODE_ENABLED,
            "IRP_NIC_AUTH_URL": self.IRP_NIC_AUTH_URL,
            "IRP_NIC_GENERATE_URL": self.IRP_NIC_GENERATE_URL,
            "IRP_NIC_LOOKUP_URL": self.IRP_NIC_LOOKUP_URL,
            "IRP_NIC_CANCEL_URL": self.IRP_NIC_CANCEL_URL,
            "IRP_NIC_EWAY_URL": self.IRP_NIC_EWAY_URL,
            "IRP_NIC_USERNAME": self.IRP_NIC_USERNAME,
            "IRP_NIC_PASSWORD": self.IRP_NIC_PASSWORD,
            "IRP_NIC_CLIENT_ID": self.IRP_NIC_CLIENT_ID,
            "IRP_NIC_CLIENT_SECRET": self.IRP_NIC_CLIENT_SECRET,
            "COMPLIANCE_ALERT_WEBHOOK_URL": self.COMPLIANCE_ALERT_WEBHOOK_URL,
            "COMPLIANCE_ALERT_API_TOKEN": self.COMPLIANCE_ALERT_API_TOKEN,
            "CACHE_TYPE": self.CACHE_TYPE,
            "CACHE_REDIS_URL": self.REDIS_URL,
            "CACHE_DEFAULT_TIMEOUT": self.CACHE_DEFAULT_TIMEOUT,
            "RATELIMIT_ENABLED": self.RATELIMIT_ENABLED,
            "RATELIMIT_DEFAULT": self.RATELIMIT_DEFAULT,
            "RATELIMIT_STORAGE_URI": self.REDIS_URL,
            # A Redis outage must degrade rate limiting (per-process in-memory
            # fallback), never block checkouts with 500s (P1A-1).
            "RATELIMIT_SWALLOW_ERRORS": True,
            "RATELIMIT_IN_MEMORY_FALLBACK_ENABLED": True,
            "CELERY": {
                "broker_url": self.CELERY_BROKER_URL or self.REDIS_URL,
                "result_backend": self.CELERY_RESULT_BACKEND or self.REDIS_URL,
                "task_serializer": "json",
                "result_serializer": "json",
                "accept_content": ["json"],
                "timezone": "UTC",
                "enable_utc": True,
                "broker_connection_retry_on_startup": True,
                "imports": (
                    "vglpos.tasks.receipts",
                    "vglpos.tasks.maintenance",
                    "vglpos.tasks.reports",
                    "vglpos.tasks.compliance",
                ),
                "beat_schedule": {
                    "refresh-daily-sales-summary": {
                        "task": "vglpos.refresh_daily_sales_summary",
                        "schedule": 300.0,
                    },
                    "reconcile-customer-counters-nightly": {
                        "task": "vglpos.reconcile_customer_counters",
                        "schedule": crontab(hour=2, minute=15),
                    },
                    "reconcile-e-invoices-hourly": {
                        "task": "vglpos.reconcile_einvoices",
                        "schedule": 3600.0,
                    },
                    "monitor-compliance-queue": {
                        "task": "vglpos.monitor_compliance_queue",
                        "schedule": 900.0,
                    },
                },
            },
        }


class DevelopmentConfig(BaseConfig):
    """Local development against docker-compose Postgres/Redis.

    The literals below are local-only conveniences, not deployment values:
    every one is overridable via ``.env`` and ``ProductionConfig`` refuses all
    of them outright.
    """

    APP_ENV: str = Field(default="development", validation_alias="VGLPOS_DEVELOPMENT_ENV")
    DEBUG: bool = Field(default=True, validation_alias="VGLPOS_DEVELOPMENT_DEBUG")
    TESTING: bool = Field(default=False, validation_alias="VGLPOS_DEVELOPMENT_TESTING")
    SECRET_KEY: str = "dev-only-secret-key-not-for-production"
    JWT_SECRET_KEY: str = "dev-only-jwt-key-not-for-production"
    OFFLINE_SYNC_SIGNING_SECRET: str = "dev-only-offline-sync-key-not-for-production"
    DATABASE_URL: str = "postgresql+psycopg://vglpos:vglpos@localhost:5432/vglpos_dev"


class TestingConfig(BaseConfig):
    """Hermetic test configuration.

    WHY in-memory SQLite by default: the suite must never touch a real
    database. Set ``TEST_DATABASE_URL`` (note: NOT ``DATABASE_URL``, which is
    deliberately ignored here so a developer's dev database can never leak into
    a test run) to use a disposable Postgres; ``tests/conftest.py`` refuses any
    database whose name does not end in ``_test``.
    """

    # Tell pytest this is not a test class despite the Test* name.
    __test__ = False

    # Test configuration must be hermetic.  In particular, a developer's
    # project-level .env may contain deployment-oriented values (or even values
    # that are invalid for these strongly typed fields) and must never prevent
    # the test app from being constructed.  The deliberately unusual prefix
    # keeps ordinary APP_ENV/DEBUG/etc. variables out; TEST_DATABASE_URL keeps
    # its explicit validation alias below so callers can still opt into a
    # disposable PostgreSQL database.
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="VGLPOS_TEST_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "testing"
    TESTING: bool = True
    DEBUG: bool = False
    SECRET_KEY: str = "testing-only-secret-key-not-for-production"
    JWT_SECRET_KEY: str = "testing-only-jwt-key-not-for-production"
    OFFLINE_SYNC_SIGNING_SECRET: str = "testing-only-offline-sync-key-not-for-production"
    DATABASE_URL: str = Field(
        default="sqlite+pysqlite:///:memory:", validation_alias="TEST_DATABASE_URL"
    )
    CACHE_TYPE: str = "SimpleCache"
    RATELIMIT_ENABLED: bool = False

    def _engine_options(self) -> dict[str, Any]:
        """In-memory SQLite needs one shared connection (StaticPool); the
        PostgreSQL pool sizing keywords would be rejected by its pool class."""
        if self.DATABASE_URL.startswith("sqlite"):
            return {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        return super()._engine_options()


class ProductionConfig(BaseConfig):
    """Production settings: everything security-relevant must come from the
    environment, and construction fails hard if it does not.

    WHY validate at construction: a production process that boots with a
    missing or well-known secret is a silent catastrophe; the only safe moment
    to refuse is before the first request can ever be served.
    """

    APP_ENV: str = Field(default="production", validation_alias="VGLPOS_PRODUCTION_ENV")
    DEBUG: bool = Field(default=False, validation_alias="VGLPOS_PRODUCTION_DEBUG")
    TESTING: bool = Field(default=False, validation_alias="VGLPOS_PRODUCTION_TESTING")

    @model_validator(mode="after")
    def _refuse_missing_or_default_values(self) -> ProductionConfig:
        """Reject empty, short, or known-default secrets and database URLs."""
        problems: list[str] = []
        for name in (
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "OFFLINE_SYNC_SIGNING_SECRET",
            "METRICS_AUTH_TOKEN",
        ):
            value = getattr(self, name).strip()
            lowered = value.lower()
            if lowered in _INSECURE_SECRET_VALUES or any(
                marker in lowered for marker in _INSECURE_SECRET_MARKERS
            ):
                problems.append(f"{name} is missing or a known-default value")
            elif len(value) < _MIN_SECRET_LENGTH:
                problems.append(f"{name} must be at least {_MIN_SECRET_LENGTH} characters")

        database_url = self.DATABASE_URL.strip()
        dev_default = DevelopmentConfig.model_fields["DATABASE_URL"].default
        if not database_url or database_url == dev_default:
            problems.append("DATABASE_URL is missing or the development default")
        elif not database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be PostgreSQL for server deployments")

        if problems:
            raise ValueError(
                "refusing to start with unsafe production configuration: " + "; ".join(problems)
            )
        return self


_CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env: str | None = None) -> type[BaseConfig]:
    """Map APP_ENV to a config class.

    WHY a hard error on unknown names: a typo like ``APP_ENV=prod`` silently
    falling back to development config would ship debug mode to a store.
    """
    name = (env or os.environ.get("APP_ENV", "development")).strip().lower()
    try:
        return _CONFIGS[name]
    except KeyError as exc:
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of {sorted(_CONFIGS)}") from exc
