"""Flask CLI command registry."""

from __future__ import annotations

from flask import Flask

from vglpos.cli.feature_flags import feature_flag
from vglpos.cli.legacy_migration import migrate_legacy
from vglpos.cli.maintenance import reconcile_customer_counters
from vglpos.cli.seed_reference import seed_reference


def register_cli(app: Flask) -> None:
    """Register maintenance commands without performing work at import time."""
    app.cli.add_command(migrate_legacy)
    app.cli.add_command(reconcile_customer_counters)
    app.cli.add_command(seed_reference)
    app.cli.add_command(feature_flag)
