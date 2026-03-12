from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path

try:
    from calibre.ebooks.BeautifulSoup import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:  # pragma: no cover
        BeautifulSoup = None

def _import_sibling(module_name: str):
    if __name__.startswith("calibre_plugins."):
        parts = __name__.split(".")
        if len(parts) >= 2:
            pkg = ".".join(parts[:2])
            try:
                return importlib.import_module(f"{pkg}.{module_name}")
            except Exception:
                pass
    return importlib.import_module(module_name)


try:
    auto_tag_adjacent_zh_pairs_in_soup = _import_sibling("et_bilingual_pair").auto_tag_adjacent_zh_pairs_in_soup
except Exception:  # pragma: no cover
    auto_tag_adjacent_zh_pairs_in_soup = None

STYLE_ID = "et-pair-highlight-style"
SCRIPT_ID = "et-pair-highlight-script"

_ASSET_DIR = Path(__file__).resolve().parent / "resources"
_CSS_PATH = _ASSET_DIR / "css" / "et_pair_highlight.css"
_JS_PATH = _ASSET_DIR / "js" / "et_pair_highlight.js"

HIGHLIGHT_CSS: str | None = None
HIGHLIGHT_JS: str | None = None


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
        raise FileNotFoundError(f"Missing et_pair_highlight asset: {fs_path}") from exc


def load_pair_highlight_css() -> str:
    global HIGHLIGHT_CSS
    if HIGHLIGHT_CSS is None:
        HIGHLIGHT_CSS = _read_text_asset(zip_path="resources/css/et_pair_highlight.css", fs_path=_CSS_PATH)
    return HIGHLIGHT_CSS


def load_pair_highlight_js() -> str:
    global HIGHLIGHT_JS
    if HIGHLIGHT_JS is None:
        HIGHLIGHT_JS = _read_text_asset(zip_path="resources/js/et_pair_highlight.js", fs_path=_JS_PATH)
    return HIGHLIGHT_JS


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



def _insert_before_last_match(html: str, pattern: re.Pattern[str], insertion: str) -> str | None:
    last_match = None
    for match in pattern.finditer(html):
        last_match = match
    if last_match is None:
        return None
    return html[: last_match.start()] + insertion + html[last_match.start() :]


def inject_et_pair_highlight(html: str) -> str:
    """Injects CSS+JS that highlights `.et-src/.et-tr` pairs by shared `et-pair-xxx` class."""

    updated = html

    css_text = load_pair_highlight_css()
    js_text = load_pair_highlight_js()
    style_tag = f"\n<style id=\"{STYLE_ID}\">\n{css_text}\n</style>\n"
    script_tag = f"\n<script id=\"{SCRIPT_ID}\">\n{js_text}\n</script>\n"

    # Update existing injected blocks if present; otherwise insert.
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

    # Optional: auto-tag adjacent (src, zh) sibling blocks as `.et-src/.et-tr` pairs.
    # This preserves the original DOM structure (lists, links) and avoids the common
    # pitfall of pairing whole <ol>/<ul> containers.
    if getattr(inject_file, "auto_tag_zh", False):
        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup (bs4) is required for --auto-tag-zh")
        if auto_tag_adjacent_zh_pairs_in_soup is None:
            raise RuntimeError("Missing helper: et_bilingual_pair.auto_tag_adjacent_zh_pairs_in_soup")
        soup = BeautifulSoup(original, "html.parser")
        tagged = auto_tag_adjacent_zh_pairs_in_soup(soup)
        # Keep a tiny hint for users debugging.
        if tagged:
            try:
                if soup.body is not None and not soup.body.get("data-et-auto-tagged"):
                    soup.body["data-et-auto-tagged"] = "1"
            except Exception:
                pass
        original = str(soup)

    updated = inject_et_pair_highlight(original)
    if updated == original:
        return False

    if in_place:
        if backup:
            backup_path = path.with_suffix(path.suffix + ".bak")
            if not backup_path.exists():
                _write_text(backup_path, original)
        _write_text(path, updated)
    else:
        out_path = path.with_name(path.stem + ".pair" + path.suffix)
        _write_text(out_path, updated)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inject click-to-highlight behavior for bilingual HTML where source/translation share an `et-pair-xxx` class. "
            "The injected script can also split paired paragraphs into sentences at runtime for sentence-level highlighting."
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
        help="Write `*.pair.html` next to the input instead of modifying in place.",
    )
    parser.set_defaults(in_place=True)
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="Do not create a `.bak` file when modifying in place.",
    )
    parser.set_defaults(backup=True)

    parser.add_argument(
        "--auto-tag-zh",
        action="store_true",
        help=(
            "Auto-tag adjacent bilingual blocks (non-zh followed by lang=zh*) as `.et-src/.et-tr` with an `et-pair-xxx` class. "
            "Useful for raw EPUB-export HTML where translations are already placed under the source."
        ),
    )

    args = parser.parse_args()

    # Thread the flag into inject_file without changing its public signature.
    setattr(inject_file, "auto_tag_zh", bool(args.auto_tag_zh))

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
