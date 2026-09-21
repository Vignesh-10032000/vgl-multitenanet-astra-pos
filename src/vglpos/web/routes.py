"""Public, data-free Jinja shells for the authenticated browser client."""

from __future__ import annotations

from flask import Blueprint, Response, render_template

web_bp = Blueprint("web", __name__)


def _page(template: str, **context: object) -> Response:
    """Render a shell without embedding tenant or authentication data."""
    response = Response(render_template(template, **context))
    response.headers["Cache-Control"] = "no-store"
    return response


@web_bp.get("/login")
def login() -> Response:
    """Render the credential-entry shell used before a token exists."""
    return _page("login.html", page_name="login", shell="auth")


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


@web_bp.get("/receipt/<int:sale_id>")
def receipt(sale_id: int) -> Response:
    """Render a printable receipt shell populated through the protected API."""
    return _page("receipt.html", page_name="receipt", shell="receipt", sale_id=sale_id)
