"""Operator commands for shared runtime feature flags."""

from __future__ import annotations

import click

from vglpos.services.feature_flags import FEATURES, clear_feature, feature_enabled, set_feature


@click.command("feature-flag")
@click.argument("name", type=click.Choice(sorted(FEATURES)))
@click.argument("action", type=click.Choice(("enable", "disable", "default", "status")))
def feature_flag(name: str, action: str) -> None:
    """Change a feature immediately across application processes."""
    if action == "enable":
        set_feature(name, True)
    elif action == "disable":
        set_feature(name, False)
    elif action == "default":
        clear_feature(name)
    click.echo(f"{name}={'enabled' if feature_enabled(name) else 'disabled'}")
