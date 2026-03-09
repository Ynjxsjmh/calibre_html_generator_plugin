from __future__ import annotations

from pathlib import Path


def _read_text_asset(*, zip_path: str, fs_path: Path) -> str:
    """Read a text asset either from the plugin ZIP (preferred) or filesystem.

    In calibre plugin code, `get_resources()` is injected as a builtin that can
    read files from the plugin ZIP. When running this project outside calibre,
    it may be unavailable, in which case we fall back to reading from disk.
    """

    # Try plugin ZIP first.
    try:
        data = get_resources(zip_path)  # type: ignore[name-defined]
    except Exception:
        data = None

    if isinstance(data, (bytes, bytearray)):
        return bytes(data).decode("utf-8")

    # Fallback to filesystem for local dev.
    try:
        return fs_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing TOC sidebar asset: {fs_path}") from exc

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
        _cached_css = _read_text_asset(zip_path="resources/css/et_toc_sidebar.css", fs_path=_CSS_PATH)
    return _cached_css


def load_toc_sidebar_js() -> str:
    global _cached_js
    if _cached_js is None:
        _cached_js = _read_text_asset(zip_path="resources/js/et_toc_sidebar.js", fs_path=_JS_PATH)
    return _cached_js
