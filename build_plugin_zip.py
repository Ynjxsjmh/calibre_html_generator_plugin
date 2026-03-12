"""Build the calibre *main UI (library)* plugin zip."""

from __future__ import annotations

import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    plugin_root = root / "library_plugin"
    out_path = root / "html_generator_plugin.zip"

    # (source_path, arcname_in_zip)
    files = [
        (plugin_root / "__init__.py", "__init__.py"),
        (plugin_root / "ui.py", "ui.py"),
        (
            plugin_root / "plugin-import-name-html_generator_library.txt",
            "plugin-import-name-html_generator_library.txt",
        ),
        (root / "export_single_html.py", "export_single_html.py"),
        (root / "et_pair_highlight.py", "et_pair_highlight.py"),
        (root / "et_bilingual_pair.py", "et_bilingual_pair.py"),
        (root / "et_toc_sidebar.py", "et_toc_sidebar.py"),
        (root / "resources" / "css" / "et_pair_highlight.css", "resources/css/et_pair_highlight.css"),
        (root / "resources" / "js" / "et_pair_highlight.js", "resources/js/et_pair_highlight.js"),
        (root / "resources" / "css" / "et_toc_sidebar.css", "resources/css/et_toc_sidebar.css"),
        (root / "resources" / "js" / "et_toc_sidebar.js", "resources/js/et_toc_sidebar.js"),
    ]

    missing = [str(src) for src, _ in files if not src.exists()]
    if missing:
        raise FileNotFoundError("Missing files: " + ", ".join(missing))

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arc in files:
            zf.write(src, arc.replace("\\", "/"))

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
