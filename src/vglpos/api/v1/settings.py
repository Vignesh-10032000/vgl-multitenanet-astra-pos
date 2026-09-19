"""Reserved API v1 settings blueprint.

The architecture endpoint map defines no settings routes in Phase 3. Keeping
the named blueprint empty makes that deliberate boundary visible without
shipping a placeholder or an unguarded endpoint.
"""

from flask import Blueprint

settings_bp = Blueprint("settings", __name__, url_prefix="/api/v1/settings")
