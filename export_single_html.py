from __future__ import annotations

import base64
import importlib
import os
import re
from html import escape as html_escape
from urllib.parse import urlparse


_INVALID_FILENAME_CHARS_RE = re.compile(r"[\\/:*?\"<>|]+")

_INLINE_MAX_HEIGHT_NONE_RE = re.compile(r"max-height\s*:\s*none\b", re.IGNORECASE)

_DOC_EXTS = {".xhtml", ".html", ".htm"}
_DOC_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}


def safe_filename(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = _INVALID_FILENAME_CHARS_RE.sub("_", name)
    name = name.strip(" ._")
    return name


def _import_sibling(module_name: str):
    """Import a sibling module from the current calibre plugin namespace.

    When running inside calibre with a multi-file plugin, modules live under
    `calibre_plugins.<import_name>.*`. When running this repo as plain Python,
    fall back to importing by bare module name.
    """

    if __name__.startswith("calibre_plugins."):
        parts = __name__.split(".")
        if len(parts) >= 2:
            pkg = ".".join(parts[:2])
            try:
                return importlib.import_module(f"{pkg}.{module_name}")
            except Exception:
                pass

    return importlib.import_module(module_name)


def _is_external_url(url: str) -> bool:
    if not url:
        return False
    u = url.strip()
    if u.startswith("data:"):
        return True
    if u.startswith("//"):
        return True
    p = urlparse(u)
    return bool(p.scheme) or bool(p.netloc)


def _build_name_to_prefix_map(container) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for mid, name in container.manifest_id_map.items():
            if not name or not mid:
                continue
            out[str(name)] = str(mid)
    except Exception:
        pass
    return out


def _prefix_for_name(name: str, name_to_prefix: dict[str, str]) -> str:
    prefix = name_to_prefix.get(name)
    if prefix:
        return prefix
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^A-Za-z0-9_:-]+", "_", base).strip("_")
    return base or "sec"


def _collect_text_by_media_types(container, media_types: tuple[str, ...]) -> str:
    parts: list[str] = []
    try:
        for mt in media_types:
            for name in container.manifest_type_map.get(mt, []):
                try:
                    parts.append(container.raw_data(name))
                except Exception:
                    continue
    except Exception:
        pass
    return "\n".join(p for p in parts if p)


def _is_oeb_doc_name(container, name: str) -> bool:
    mt = (container.mime_map.get(name) or "").strip().lower()
    if mt in _DOC_MEDIA_TYPES:
        return True
    return os.path.splitext(name)[1].lower() in _DOC_EXTS


def _make_toc_ul(toc_root, name_to_prefix: dict[str, str], *, level: int = 0) -> str:
    indent = "  " * level
    items: list[str] = []

    for node in toc_root:
        title = html_escape((getattr(node, "title", None) or "").strip() or "(Untitled)")
        dest = getattr(node, "dest", None)
        frag = getattr(node, "frag", None) or None

        href_target: str | None = None
        if dest:
            dest = str(dest)
            dest_prefix = _prefix_for_name(dest, name_to_prefix)
            href_target = f"{dest_prefix}_{frag}" if frag else dest_prefix

        sub = ""
        try:
            if len(node) > 0:
                sub = _make_toc_ul(node, name_to_prefix, level=level + 1)
        except Exception:
            sub = ""

        if href_target:
            items.append(
                f'{indent}<li><a id="toc_{href_target}" href="#{href_target}">{title}</a>{sub}</li>'
            )
        else:
            items.append(f"{indent}<li><span>{title}</span>{sub}</li>")

    style = ' style="text-align: left;"' if level == 0 else ""
    inner = "\n".join(items)
    return f"\n{indent}<ul{style}>\n{inner}\n{indent}</ul>\n"


def _make_spine_toc_ul(container, name_to_prefix: dict[str, str]) -> str:
    items: list[str] = []
    for name, _is_linear in container.spine_names:
        prefix = _prefix_for_name(name, name_to_prefix)
        title = html_escape(os.path.basename(name) or prefix)
        items.append(f'<li><a id="toc_{prefix}" href="#{prefix}">{title}</a></li>')
    inner = "\n".join(items)
    return f'\n<ul style="text-align: left;">\n{inner}\n</ul>\n'


def _rewrite_doc_to_body_html(
    container,
    raw: str,
    *,
    base_name: str,
    base_prefix: str,
    name_to_prefix: dict[str, str],
    img_uri_cache: dict[str, str],
) -> str:
    from lxml import html as lhtml

    try:
        doc = lhtml.document_fromstring(raw)
    except Exception:
        doc = lhtml.document_fromstring(f"<html><body>{raw}</body></html>")

    for el in doc.xpath('//*[@id]'):
        old = el.get("id")
        if old:
            el.set("id", f"{base_prefix}_{old}")

    for a in doc.xpath('//a[@name]'):
        old = a.get("name")
        if not old:
            continue
        new = f"{base_prefix}_{old}"
        a.set("name", new)
        if not a.get("id"):
            a.set("id", new)

    for a in doc.xpath('//a[@href] | //area[@href]'):
        href = a.get("href")
        if not href:
            continue

        if href.startswith("#"):
            frag = href[1:]
            if frag:
                a.set("href", f"#{base_prefix}_{frag}")
            continue

        if _is_external_url(href):
            continue

        p = urlparse(href)
        path = p.path or ""
        frag = p.fragment or ""

        try:
            dest_name = base_name if not path else container.href_to_name(path, base=base_name)
        except Exception:
            continue

        if not dest_name or not _is_oeb_doc_name(container, dest_name):
            continue

        dest_prefix = _prefix_for_name(str(dest_name), name_to_prefix)
        a.set("href", f"#{dest_prefix}_{frag}" if frag else f"#{dest_prefix}")

    for img in doc.xpath('//img[@src]'):
        src = img.get("src")
        if not src or _is_external_url(src):
            continue
        if src.strip().lower().startswith("data:"):
            continue

        p = urlparse(src)
        path = p.path or ""
        if not path:
            continue
        try:
            img_name = container.href_to_name(path, base=base_name)
        except Exception:
            continue

        mt = container.mime_map.get(img_name) or ""
        if not mt.startswith("image/"):
            continue

        data_uri = img_uri_cache.get(img_name)
        if not data_uri:
            try:
                blob = container.raw_data(img_name, decode=False)
            except Exception:
                continue
            if isinstance(blob, str):
                blob = blob.encode("utf-8")
            b64 = base64.b64encode(blob).decode("ascii")
            data_uri = f"data:{mt};base64,{b64}"
            img_uri_cache[img_name] = data_uri
        img.set("src", data_uri)

        # Keep behavior consistent with the legacy BeautifulSoup exporter:
        # - If <img> has class: clear inline style
        # - If <img> has class and parent has class: also relax parent's max-height
        # - Else: apply responsive defaults
        img_has_class = img.get("class") is not None
        if img_has_class:
            img.set("style", "")
            parent = img.getparent()
            if parent is not None and parent.get("class") is not None:
                parent_style = (parent.get("style") or "").strip()
                if not _INLINE_MAX_HEIGHT_NONE_RE.search(parent_style):
                    if parent_style and not parent_style.endswith(";"):
                        parent_style += ";"
                    parent.set("style", (parent_style + " max-height: none;").strip())
        else:
            img.set("style", "width: auto; max-width: 100%; height: auto;")

    XLINK = "{http://www.w3.org/1999/xlink}href"
    for im in doc.xpath('//*[local-name()="image"]'):
        href = im.get("href") or im.get(XLINK)
        if not href or _is_external_url(href):
            continue
        p = urlparse(href)
        path = p.path or ""
        if not path:
            continue
        try:
            img_name = container.href_to_name(path, base=base_name)
        except Exception:
            continue

        mt = container.mime_map.get(img_name) or ""
        if not mt.startswith("image/"):
            continue

        data_uri = img_uri_cache.get(img_name)
        if not data_uri:
            try:
                blob = container.raw_data(img_name, decode=False)
            except Exception:
                continue
            if isinstance(blob, str):
                blob = blob.encode("utf-8")
            b64 = base64.b64encode(blob).decode("ascii")
            data_uri = f"data:{mt};base64,{b64}"
            img_uri_cache[img_name] = data_uri

        if im.get("href"):
            im.set("href", data_uri)
        if im.get(XLINK):
            im.set(XLINK, data_uri)

    body = doc.find("body")
    if body is None:
        return raw

    body_html = lhtml.tostring(body, encoding="unicode", method="html")
    body_html = re.sub(r"^<body\b[^>]*>", "", body_html, flags=re.IGNORECASE)
    body_html = re.sub(r"</body>\s*$", "", body_html, flags=re.IGNORECASE)
    return body_html


def export_container_to_single_html(container) -> str:
    name_to_prefix = _build_name_to_prefix_map(container)

    pair_highlight = _import_sibling("et_pair_highlight")
    inject_et_pair_highlight = getattr(pair_highlight, "inject_et_pair_highlight")

    reader_settings_mod = _import_sibling("et_reader_settings")
    inject_et_reader_settings = getattr(reader_settings_mod, "inject_et_reader_settings")

    toc_sidebar_mod = _import_sibling("et_toc_sidebar")
    TOC_STYLE_ID = getattr(toc_sidebar_mod, "TOC_STYLE_ID")
    TOC_SCRIPT_ID = getattr(toc_sidebar_mod, "TOC_SCRIPT_ID")
    load_toc_sidebar_css = getattr(toc_sidebar_mod, "load_toc_sidebar_css")
    load_toc_sidebar_js = getattr(toc_sidebar_mod, "load_toc_sidebar_js")

    title = ""
    try:
        title = str(getattr(container.mi, "title", "") or "")
    except Exception:
        title = ""

    css_text = _collect_text_by_media_types(container, ("text/css",))
    js_text = _collect_text_by_media_types(container, ("application/javascript", "text/javascript"))

    css_block = f"\n<style>\n{css_text}\n</style>\n" if css_text else ""
    js_block = f"\n<script>\n{js_text}\n</script>\n" if js_text else ""

    toc_root = None
    try:
        from calibre.ebooks.oeb.polish.toc import from_files, get_toc

        toc_root = get_toc(container, verify_destinations=False)
        if toc_root is None or len(toc_root) == 0:
            toc_root = from_files(container)
    except Exception:
        toc_root = None

    toc_ul = (
        _make_toc_ul(toc_root, name_to_prefix)
        if toc_root is not None
        else _make_spine_toc_ul(container, name_to_prefix)
    )

    toc_sidebar_css = load_toc_sidebar_css()
    toc_sidebar_js = load_toc_sidebar_js()
    toc_style = f'\n<style id="{TOC_STYLE_ID}">\n{toc_sidebar_css}\n</style>\n'
    toc_script = f'\n<script id="{TOC_SCRIPT_ID}">\n{toc_sidebar_js}\n</script>\n'

    toc_sidebar = (
        "\n"
        '<aside id="et-toc-sidebar" data-et-toc-side="left" data-et-toc-state="expanded">\n'
        '  <div class="et-toc-header">\n'
        '    <button type="button" id="et-toc-collapse-btn" class="et-toc-btn et-toc-collapse-btn">收起</button>\n'
        '    <button type="button" id="et-toc-side-btn" class="et-toc-btn et-toc-side-btn">右侧</button>\n'
        '    <button type="button" id="et-toc-highlight-btn" class="et-toc-btn et-toc-highlight-btn">禁用</button>\n'
        "  </div>\n"
        '  <nav class="et-toc-body" id="et-toc-sidebar-body" aria-label="Table of contents"></nav>\n'
        '  <div class="et-toc-resizer" id="et-toc-resizer" aria-hidden="true"></div>\n'
        "</aside>\n"
    )
    toc_top = f'\n<div id="et-toc-top">\n{toc_ul}\n</div>\n'

    img_uri_cache: dict[str, str] = {}
    book_parts: list[str] = []
    for name, _is_linear in container.spine_names:
        prefix = _prefix_for_name(name, name_to_prefix)
        raw = container.raw_data(name)
        inner = _rewrite_doc_to_body_html(
            container,
            raw,
            base_name=name,
            base_prefix=prefix,
            name_to_prefix=name_to_prefix,
            img_uri_cache=img_uri_cache,
        )
        book_parts.append(f'\n<a id="{prefix}"></a>\n{inner}\n')

    book_content = "\n".join(book_parts)

    safe_title = html_escape(title or "")
    html_content = (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        f"  <title>{safe_title}</title>\n"
        f"{css_block}"
        f"{toc_style}"
        "</head>\n"
        "<body style=\"text-align: left;\">\n"
        f"{toc_sidebar}"
        "<main id=\"et-reader\">\n"
        f"{toc_top}"
        f"{book_content}"
        "</main>\n"
        f"{js_block}"
        f"{toc_script}"
        "</body>\n"
        "</html>\n"
    )

    # Optional: auto-tag adjacent bilingual blocks if possible.
    try:
        from calibre.ebooks.BeautifulSoup import BeautifulSoup  # type: ignore

        bilingual_pair_mod = _import_sibling("et_bilingual_pair")
        auto_tag_adjacent_zh_pairs_in_soup = getattr(bilingual_pair_mod, "auto_tag_adjacent_zh_pairs_in_soup")

        soup = BeautifulSoup(html_content, "html.parser")
        tagged = auto_tag_adjacent_zh_pairs_in_soup(soup)
        if tagged:
            try:
                if soup.body is not None and not soup.body.get("data-et-auto-tagged"):
                    soup.body["data-et-auto-tagged"] = "1"
            except Exception:
                pass
        html_content = str(soup)
    except Exception:
        pass

    html_content = inject_et_pair_highlight(html_content)
    html_content = inject_et_reader_settings(html_content)
    return html_content
