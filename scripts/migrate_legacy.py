"""Stable import location for the Flask legacy-migration command."""

from __future__ import annotations

from vglpos.cli.legacy_migration import migrate_legacy

__all__ = ["migrate_legacy"]
