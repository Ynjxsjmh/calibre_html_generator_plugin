from __future__ import annotations

import argparse
import re
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
        raise FileNotFoundError(f"Missing reader settings asset: {fs_path}") from exc


STYLE_ID = "et-reader-settings-style"
SCRIPT_ID = "et-reader-settings-script"

_ASSET_DIR = Path(__file__).resolve().parent / "resources"
_CSS_PATH = _ASSET_DIR / "css" / "et_reader_settings.css"
_JS_PATH = _ASSET_DIR / "js" / "et_reader_settings.js"

_cached_css: str | None = None
_cached_js: str | None = None


def load_reader_settings_css() -> str:
    global _cached_css
    if _cached_css is None:
        _cached_css = _read_text_asset(zip_path="resources/css/et_reader_settings.css", fs_path=_CSS_PATH)
    return _cached_css


def load_reader_settings_js() -> str:
    global _cached_js
    if _cached_js is None:
        _cached_js = _read_text_asset(zip_path="resources/js/et_reader_settings.js", fs_path=_JS_PATH)
    return _cached_js


_CLOSE_HEAD_RE = re.compile(r"</head\s*>", re.IGNORECASE)
_OPEN_BODY_RE = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
_CLOSE_BODY_RE = re.compile(r"</body\s*>", re.IGNORECASE)
_CLOSE_HTML_RE = re.compile(r"</html\s*>", re.IGNORECASE)

_STYLE_BLOCK_RE = re.compile(
    rf"<style\b[^>]*\bid=\"{re.escape(STYLE_ID)}\"[^>]*>.*?</style>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_BLOCK_RE = re.compile(
    rf"<script\b[^>]*\bid=\"{re.escape(SCRIPT_ID)}\"[^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)

_PANEL_BLOCK_RE = re.compile(
    r"<!--\s*et-reader-settings:start\s*-->.*?<!--\s*et-reader-settings:end\s*-->",
    re.IGNORECASE | re.DOTALL,
)


def _insert_before_last_match(html: str, pattern: re.Pattern[str], insertion: str) -> str | None:
    last_match = None
    for match in pattern.finditer(html):
        last_match = match
    if last_match is None:
        return None
    return html[: last_match.start()] + insertion + html[last_match.start() :]


def _insert_after_first_match(html: str, pattern: re.Pattern[str], insertion: str) -> str | None:
    match = pattern.search(html)
    if match is None:
        return None
    return html[: match.end()] + insertion + html[match.end() :]


def _panel_html() -> str:
    return (
        "\n<!-- et-reader-settings:start -->\n"
        '<div id="et-reader-settings" class="et-setbox" data-et-state="expanded">\n'
        '  <div class="et-setbox-header" role="button" aria-label="阅读设置" tabindex="0">\n'
        '    <div class="et-setbox-title">阅读设置</div>\n'
        "  </div>\n"
        "  <div class=\"et-setbox-body\">\n"
        "    <div class=\"et-setting-row\">\n"
        "      <div class=\"et-bg\" aria-label=\"背景颜色\">\n"
        '        <button type="button" class="et-bg-item et-active" data-et-theme="default" title="默认白" style="background:#ffffff"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="gray" title="灰色" style="background:#ededed"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="eye" title="护眼黄" style="background:#f7efd0"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="pink" title="粉红色" style="background:#f9e6e6"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="green" title="淡绿色" style="background:#cddfcd"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="solarized-light" title="Solarized Light" style="background:#fdf6e3"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="night" title="夜间" style="background:#0f1115"></button>\n'
        '        <button type="button" class="et-bg-item" data-et-theme="solarized-night" title="Solarized Night" style="background:#002b36"></button>\n'
        "      </div>\n"
        "    </div>\n"
        "    <div class=\"et-setting-row\">\n"
        "      <div class=\"et-ctrl\" aria-label=\"字体大小\">\n"
        '        <button type="button" class="et-ctrl-btn et-font-cut">-</button>\n'
        '        <div class="et-ctrl-display"><span class="et-font-size-value">20</span>px</div>\n'
        '        <button type="button" class="et-ctrl-btn et-font-add">+</button>\n'
        "      </div>\n"
        "      <div class=\"et-ctrl\" aria-label=\"行高\">\n"
        '        <button type="button" class="et-ctrl-btn et-line-cut">-</button>\n'
        '        <div class="et-ctrl-display"><span class="et-line-height-value">1.4</span>倍</div>\n'
        '        <button type="button" class="et-ctrl-btn et-line-add">+</button>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        "</div>\n"
        "<!-- et-reader-settings:end -->\n"
    )


def inject_et_reader_settings(html: str) -> str:
    """Inject a simple reading settings panel (theme, font size, line height)."""

    updated = html

    style_tag = f"\n<style id=\"{STYLE_ID}\">\n{load_reader_settings_css()}\n</style>\n"
    script_tag = f"\n<script id=\"{SCRIPT_ID}\">\n{load_reader_settings_js()}\n</script>\n"
    panel_tag = _panel_html()

    # CSS: update or insert into <head>
    if _STYLE_BLOCK_RE.search(updated):
        updated = _STYLE_BLOCK_RE.sub(lambda _m: style_tag.strip(), updated, count=1)
    else:
        inserted = _insert_before_last_match(updated, _CLOSE_HEAD_RE, style_tag)
        if inserted is None:
            body_open = _OPEN_BODY_RE.search(updated)
            if body_open is not None:
                inserted = updated[: body_open.start()] + style_tag + updated[body_open.start() :]
            else:
                inserted = style_tag + updated
        updated = inserted

    # Panel HTML: update or insert right after <body>
    if _PANEL_BLOCK_RE.search(updated):
        updated = _PANEL_BLOCK_RE.sub(lambda _m: panel_tag.strip(), updated, count=1)
    else:
        inserted = _insert_after_first_match(updated, _OPEN_BODY_RE, panel_tag)
        if inserted is None:
            inserted = _insert_before_last_match(updated, _CLOSE_BODY_RE, panel_tag)
        if inserted is None:
            inserted = _insert_before_last_match(updated, _CLOSE_HTML_RE, panel_tag)
        if inserted is None:
            inserted = updated + panel_tag
        updated = inserted

    # JS: update or insert before </body>
    if _SCRIPT_BLOCK_RE.search(updated):
        updated = _SCRIPT_BLOCK_RE.sub(lambda _m: script_tag.strip(), updated, count=1)
    else:
        inserted = _insert_before_last_match(updated, _CLOSE_BODY_RE, script_tag)
        if inserted is None:
            inserted = _insert_before_last_match(updated, _CLOSE_HTML_RE, script_tag)
        if inserted is None:
            inserted = updated + script_tag
        updated = inserted

    return updated


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def inject_file(path: Path, *, in_place: bool, backup: bool) -> bool:
    original = _read_text(path)
    updated = inject_et_reader_settings(original)
    if updated == original:
        return False

    if in_place:
        if backup:
            backup_path = path.with_suffix(path.suffix + ".bak")
            if not backup_path.exists():
                _write_text(backup_path, original)
        _write_text(path, updated)
    else:
        out_path = path.with_name(path.stem + ".settings" + path.suffix)
        _write_text(out_path, updated)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inject a reading settings panel into HTML: background theme (including Solarized light/night), "
            "font size, and line height."
        )
    )
    parser.add_argument("paths", nargs="+", help="HTML file paths or directories")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify files in place (default).",
    )
    parser.add_argument(
        "--no-in-place",
        dest="in_place",
        action="store_false",
        help="Write `*.settings.html` next to the input instead of modifying in place.",
    )
    parser.set_defaults(in_place=True)
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="Do not create a `.bak` file when modifying in place.",
    )
    parser.set_defaults(backup=True)

    args = parser.parse_args()

    targets: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            targets.extend(sorted(p.glob("*.html")))
        else:
            targets.append(p)

    changed = 0
    for path in targets:
        if path.suffix.lower() != ".html":
            continue

        if inject_file(path, in_place=args.in_place, backup=args.backup):
            changed += 1

    print(f"Updated {changed} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
