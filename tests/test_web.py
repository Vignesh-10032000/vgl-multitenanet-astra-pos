"""Security and rendering contracts for the Phase 5 Jinja shell."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from flask import Flask

from vglpos.app import create_app
from vglpos.config import TestingConfig

TEMPLATE_ROOT = Path("src/vglpos/web/templates")
STATIC_SOURCE_ROOT = Path("src/vglpos/web/static/src")


@pytest.fixture(scope="module")
def web_app() -> Flask:
    """Create a data-free shell app; no browser route may require a database."""
    return create_app(TestingConfig)


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/",
        "/pos",
        "/products",
        "/customers",
        "/sales",
        "/reports",
        "/settings",
        "/receipt/1",
    ],
)
def test_browser_shells_are_public_data_free_and_hardened(web_app: Flask, path: str) -> None:
    response = web_app.test_client().get(path)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp


def test_templates_have_no_executable_inline_script_or_event_attributes() -> None:
    for template in TEMPLATE_ROOT.glob("*.html"):
        source = template.read_text(encoding="utf-8")
        script_tags = re.findall(r"<script\b[^>]*>", source, flags=re.IGNORECASE)
        assert all(re.search(r"\bsrc\s*=", tag, flags=re.IGNORECASE) for tag in script_tags), (
            template
        )
        assert re.search(r"\son[a-z]+\s*=", source, flags=re.IGNORECASE) is None, template


def test_frontend_never_uses_native_prompt_or_confirm() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in STATIC_SOURCE_ROOT.rglob("*.js")
    )
    assert "window.prompt(" not in source
    assert "window.confirm(" not in source


def test_login_page_uses_vgl_branding_and_demo_entry(web_app: Flask) -> None:
    response = web_app.test_client().get("/login")
    source = response.get_data(as_text=True)

    assert 'src="/static/icons/vgl-logo.png"' in source
    assert 'id="demo-login"' in source
    assert "Vignesh Growth Lab" in source
    assert 'href="mailto:vigneshgrowthlab@gmail.com"' in source
    assert 'href="https://wa.me/918220034139"' in source
    assert 'href="tel:+918220034139"' in source


@pytest.mark.parametrize(
    ("url", "visible"),
    [
        ("https://example.com/", True),
        ("", False),
        ("javascript:alert(1)", False),
        ("https://[invalid", False),
    ],
)
def test_login_official_website_requires_a_valid_https_url(
    web_app: Flask, url: str, visible: bool
) -> None:
    """Only a configured HTTPS site can appear as the public website link."""
    original = web_app.config["OFFICIAL_WEBSITE_URL"]
    try:
        web_app.config["OFFICIAL_WEBSITE_URL"] = url
        source = web_app.test_client().get("/login").get_data(as_text=True)
        assert ('href="https://example.com/"' in source) is visible
    finally:
        web_app.config["OFFICIAL_WEBSITE_URL"] = original


def test_locale_catalogues_have_matching_keys() -> None:
    locale_root = Path("src/vglpos/web/static/i18n")
    english = json.loads((locale_root / "en.json").read_text(encoding="utf-8"))
    tamil = json.loads((locale_root / "ta.json").read_text(encoding="utf-8"))

    assert english
    assert english.keys() == tamil.keys()
