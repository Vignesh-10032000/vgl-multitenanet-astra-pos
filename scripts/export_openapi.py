"""Emit the generated OpenAPI 3.1 contract for release documentation tooling."""

# Importing the app factory first completes blueprint initialization before the OpenAPI
# registry is loaded; alphabetizing these imports reintroduces a circular import.
# ruff: noqa: I001

from __future__ import annotations

import json
import sys

from vglpos.app import create_app
from vglpos.api.v1.openapi import build_openapi
from vglpos.config import TestingConfig


def main() -> None:
    app = create_app(TestingConfig)
    with app.app_context():
        sys.stdout.write(json.dumps(build_openapi(), indent=2, sort_keys=True))
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
