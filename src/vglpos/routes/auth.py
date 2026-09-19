"""Backward-compatible import for the API v1 authentication blueprint."""

from vglpos.api.v1.auth import auth_bp

__all__ = ["auth_bp"]
