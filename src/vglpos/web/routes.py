"""Public, data-free Jinja shells for the authenticated browser client."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from flask import Blueprint, Response, current_app, jsonify, render_template, send_from_directory

web_bp = Blueprint("web", __name__)


def _page(template: str, **context: object) -> Response:
    """Render a shell without embedding tenant or authentication data."""
    response = Response(render_template(template, **context))
    response.headers["Cache-Control"] = "no-store"
    return response


@web_bp.get("/login")
def login() -> Response:
    """Render the credential-entry shell used before a token exists."""
    website_url = str(current_app.config.get("OFFICIAL_WEBSITE_URL", ""))
    try:
        parsed = urlsplit(website_url)
        valid_website = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        valid_website = False
    if not valid_website:
        website_url = ""
    return _page("login.html", page_name="login", shell="auth", official_website_url=website_url)


@web_bp.get("/")
def dashboard() -> Response:
    """Render the operational overview shell."""
    return _page("dashboard.html", page_name="dashboard", shell="app")


@web_bp.get("/pos")
def pos() -> Response:
    """Render the keyboard- and scanner-first billing shell."""
    return _page("pos.html", page_name="pos", shell="pos")


@web_bp.get("/products")
def products() -> Response:
    """Render catalogue management without exposing catalogue rows in HTML."""
    return _page("products.html", page_name="products", shell="app")


@web_bp.get("/customers")
def customers() -> Response:
    """Render customer management without exposing customer rows in HTML."""
    return _page("customers.html", page_name="customers", shell="app")


@web_bp.get("/sales")
def sales() -> Response:
    """Render the sales register shell."""
    return _page("sales.html", page_name="sales", shell="app")


@web_bp.get("/reports")
def reports() -> Response:
    """Render the operational and statutory reports shell."""
    return _page("reports.html", page_name="reports", shell="app")


@web_bp.get("/settings")
def settings() -> Response:
    """Render workstation and store-settings controls."""
    return _page("settings.html", page_name="settings", shell="app")


@web_bp.get("/compliance")
def compliance() -> Response:
    """Render the e-invoice queue, dead-letter, and reconciliation administration shell."""
    return _page("compliance.html", page_name="compliance", shell="app")


@web_bp.get("/receipt/<int:sale_id>")
def receipt(sale_id: int) -> Response:
    """Render a printable receipt shell populated through the protected API."""
    return _page("receipt.html", page_name="receipt", shell="receipt", sale_id=sale_id)


@web_bp.get("/receipt/offline/<uuid:offline_uuid>")
def offline_receipt(offline_uuid: UUID) -> Response:
    """Render a local provisional receipt that upgrades after synchronization."""
    return _page(
        "offline_receipt.html",
        page_name="offline-receipt",
        shell="receipt",
        offline_uuid=str(offline_uuid),
    )


@web_bp.get("/z-report/<int:shift_id>")
def z_report(shift_id: int) -> Response:
    """Render a printable shift-close report populated through the protected API."""
    return _page("z_report.html", page_name="z-report", shell="receipt", shift_id=shift_id)


@web_bp.get("/sync-queue")
def sync_queue() -> Response:
    """Render the required human review surface for queued and rejected bills."""
    return _page("sync_queue.html", page_name="sync-queue", shell="app")


def _static_root() -> Path:
    static_folder = current_app.static_folder
    if static_folder is None:
        raise RuntimeError("The Flask static folder is not configured.")
    return Path(static_folder)


@web_bp.get("/manifest.webmanifest")
def web_manifest() -> Response:
    """Serve the install manifest from the application's own trusted origin."""
    return send_from_directory(
        _static_root(), "manifest.webmanifest", mimetype="application/manifest+json"
    )


@web_bp.get("/pwa-assets.json")
def pwa_assets() -> Response:
    """List the current hashed build files for an all-or-nothing shell precache."""
    root = _static_root()
    assets = [
        "/",
        "/pos",
        "/products",
        "/customers",
        "/sales",
        "/reports",
        "/settings",
        "/compliance",
        "/sync-queue",
        "/receipt/offline/00000000-0000-0000-0000-000000000000",
        "/manifest.webmanifest",
        "/static/icons/vgl-pos.svg",
        "/static/fonts/inter-latin-400-normal.woff2",
        "/static/fonts/inter-latin-600-normal.woff2",
        "/static/fonts/noto-sans-tamil-tamil-400-normal.woff2",
        "/static/fonts/noto-sans-tamil-tamil-600-normal.woff2",
    ]
    distribution = root / "dist"
    if distribution.exists():
        assets.extend(
            f"/static/dist/{path.relative_to(distribution).as_posix()}"
            for path in distribution.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        )
    response = jsonify({"assets": sorted(set(assets))})
    response.headers["Cache-Control"] = "no-store"
    return response


@web_bp.get("/sw.js")
def service_worker() -> Response:
    """Version the worker with the exact Vite manifest so updates cannot strand old assets."""
    root = _static_root()
    source = (root / "src" / "sw.js").read_text(encoding="utf-8")
    manifest_path = root / "dist" / "manifest.json"
    manifest = manifest_path.read_bytes() if manifest_path.exists() else b"development"
    version = hashlib.sha256(manifest).hexdigest()[:16]
    source = source.replace("vglpos-phase6-v1", f"vglpos-{version}")
    response = Response(source, mimetype="text/javascript")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
