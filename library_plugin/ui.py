from __future__ import annotations

import os
import traceback

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.ebooks.oeb.polish.container import get_container

try:  # calibre >= 6
    from qt.core import QFileDialog
except ImportError:  # pragma: no cover
    from PyQt5.Qt import QFileDialog  # type: ignore

from calibre_plugins.html_generator_library.export_single_html import export_container_to_single_html, safe_filename


def _pick_best_format(formats) -> str | None:
    if not formats:
        return None
    if isinstance(formats, str):
        parts = [p.strip() for p in formats.replace(";", ",").split(",") if p.strip()]
        formats = parts
    fmt_set = {str(f).strip().upper() for f in formats if f}

    for want in ("EPUB", "AZW3"):
        if want in fmt_set:
            return want
    return None


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


class HTMLGeneratorLibraryInterfaceAction(InterfaceAction):
    name = 'HTML Generator - Library Export'

    # (text, icon, tooltip, shortcut)
    action_spec = (
        'Export single HTML',
        None,
        'Export selected books to a single self-contained HTML file',
        None,
    )

    def genesis(self):
        self.qaction.triggered.connect(self.export_selected_books)

    def export_selected_books(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return error_dialog(self.gui, 'No books selected', 'Select one or more books first.', show=True)

        ids = list(map(self.gui.library_view.model().id, rows))
        db = self.gui.current_db.new_api

        out_dir = QFileDialog.getExistingDirectory(
            self.gui,
            'Select output folder',
            os.path.expanduser('~'),
        )
        if not out_dir:
            return

        base_plugin = self.interface_action_base_plugin
        exported = 0
        skipped: list[str] = []

        for book_id in ids:
            try:
                fmts = db.formats(book_id)
                best = _pick_best_format(fmts)
                if not best:
                    skipped.append(f"{book_id}: no EPUB/AZW3")
                    continue

                mi = db.get_metadata(book_id, get_cover=False)
                title = getattr(mi, 'title', '') or f"book_{book_id}"
                out_name = safe_filename(str(title)) or f"book_{book_id}"
                out_path = _unique_path(os.path.join(out_dir, out_name + '.html'))

                # Get book file data
                ffile = db.format(book_id, best.lower(), as_file=True)
                try:
                    ffile.seek(0)
                except Exception:
                    pass
                data = ffile.read()
                try:
                    ffile.close()
                except Exception:
                    pass

                if isinstance(data, str):
                    data = data.encode('utf-8')

                # Write to a temporary file so we can open a polish container.
                tf = base_plugin.temporary_file('.' + best.lower())
                tf.write(data)
                tf.close()

                container = get_container(tf.name, tweak_mode=True)
                html_content = export_container_to_single_html(container)

                with open(out_path, 'w', encoding='utf-8-sig', newline='\n') as f:
                    f.write(html_content)

                exported += 1
            except Exception as exc:
                skipped.append(f"{book_id}: {exc}")

        if exported <= 0:
            return error_dialog(
                self.gui,
                'Export finished',
                'No books were exported. Click "Show details" for more information.',
                det_msg='\n'.join(skipped) if skipped else 'No details',
                show=True,
            )

        details = ''
        if skipped:
            details = 'Skipped/failed:\n' + '\n'.join(skipped)

        return info_dialog(
            self.gui,
            'Export complete',
            f'Exported {exported} book(s) to:\n{out_dir}',
            det_msg=details or None,
            show=True,
        )
