"""Vite manifest integration for content-hashed web assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from flask import current_app


class ViteEntry(TypedDict):
    """Asset URLs required to render one Vite entry point."""

    script: str
    styles: list[str]


def vite_entry(source: str) -> ViteEntry:
    """Resolve one source entry through Vite's manifest.

    A readable development fallback keeps Flask route tests independent from
    Node. Real browsers use ``npm run build`` so bare package imports and CSS
    are always bundled before the application is served.
    """
    static_folder = current_app.static_folder
    if static_folder is None:
        raise RuntimeError("The Flask static folder is not configured.")
    manifest_path = Path(static_folder) / "dist" / "manifest.json"
    if not manifest_path.exists():
        return {"script": f"/static/src/{source}", "styles": []}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_entry = manifest.get(source)
    if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get("file"), str):
        raise RuntimeError(f"Vite manifest has no entry for {source!r}.")
    css = raw_entry.get("css", [])
    if not isinstance(css, list) or not all(isinstance(item, str) for item in css):
        raise RuntimeError(f"Vite manifest CSS list is invalid for {source!r}.")
    global_style = manifest.get("style.css")
    if (
        isinstance(global_style, dict)
        and isinstance(global_style.get("file"), str)
        and global_style["file"] not in css
    ):
        css.append(global_style["file"])
    return {
        "script": f"/static/dist/{raw_entry['file']}",
        "styles": [f"/static/dist/{item}" for item in css],
    }
