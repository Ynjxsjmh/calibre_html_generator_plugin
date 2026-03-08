from __future__ import annotations

from pathlib import Path

TOC_STYLE_ID = "et-toc-style"
TOC_SCRIPT_ID = "et-toc-script"

_ASSET_DIR = Path(__file__).resolve().parent / "resources"
_CSS_PATH = _ASSET_DIR / "css" / "et_toc_sidebar.css"
_JS_PATH = _ASSET_DIR / "js" / "et_toc_sidebar.js"

_cached_css: str | None = None
_cached_js: str | None = None


def load_toc_sidebar_css() -> str:
    global _cached_css
    if _cached_css is None:
        try:
            _cached_css = _CSS_PATH.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Missing TOC sidebar CSS asset: {_CSS_PATH}") from exc
    return _cached_css


def load_toc_sidebar_js() -> str:
    global _cached_js
    if _cached_js is None:
        try:
            _cached_js = _JS_PATH.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Missing TOC sidebar JS asset: {_JS_PATH}") from exc
    return _cached_js
