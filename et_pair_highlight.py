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

HIGHLIGHT_CSS = r"""/* et-pair-highlight */

#et-hl-layer {
    position: absolute;
    left: 0;
    top: 0;
    width: 0;
    height: 0;
    pointer-events: none;
    z-index: 2147483647;
}

.et-hl-rect {
    position: absolute;
    background: rgba(255, 238, 140, 0.65);
    border-radius: 3px;
    box-shadow: inset 0 0 0 1px rgba(180, 140, 0, 0.35);
    pointer-events: none;
}
"""

HIGHLIGHT_JS = r"""/* et-pair-highlight */
(function () {
    'use strict';

    var PAIR_PREFIX = 'et-pair-';
    var ENABLE_SENTENCE_LEVEL = true;
    var LAYER_ID = 'et-hl-layer';

    try {
        if (document.body && document.body.getAttribute('data-et-sentence-level') === '0') {
            ENABLE_SENTENCE_LEVEL = false;
        }
    } catch (e) {
        // ignore
    }

    var elementCache = new WeakMap();
    var mapCache = new WeakMap();
    var active = null; // { host, hostIdx, peer, peerIdx }

    function ensureLayer() {
        var layer = document.getElementById(LAYER_ID);
        if (layer) return layer;
        if (!document.body) return null;
        layer = document.createElement('div');
        layer.id = LAYER_ID;
        document.body.appendChild(layer);
        return layer;
    }

    function clearHighlights() {
        var layer = ensureLayer();
        if (!layer) return;
        while (layer.firstChild) layer.removeChild(layer.firstChild);
        active = null;
    }

    function addRect(left, top, width, height) {
        var layer = ensureLayer();
        if (!layer) return;
        if (width <= 0 || height <= 0) return;
        var div = document.createElement('div');
        div.className = 'et-hl-rect';
        div.style.left = left + 'px';
        div.style.top = top + 'px';
        div.style.width = width + 'px';
        div.style.height = height + 'px';
        layer.appendChild(div);
    }

    function highlightRange(range) {
        if (!range) return;
        var rects = range.getClientRects();
        for (var i = 0; i < rects.length; i++) {
            var r = rects[i];
            addRect(r.left + window.scrollX, r.top + window.scrollY, r.width, r.height);
        }
    }

    function findPairClass(el) {
        if (!el || !el.classList) return null;
        for (var i = 0; i < el.classList.length; i++) {
            var c = el.classList[i];
            if (c && c.indexOf(PAIR_PREFIX) === 0) return c;
        }
        return null;
    }

    function closestSrcOrTr(el) {
        while (el && el.nodeType === 1) {
            if (el.classList && (el.classList.contains('et-src') || el.classList.contains('et-tr'))) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    function isWS(ch) {
        return ch && /\s/.test(ch);
    }

    function isAsciiAlnum(ch) {
        return ch && /[A-Za-z0-9]/.test(ch);
    }

    function splitSentenceRanges(text) {
        // Returns [{s,e}] in raw-text indices.
        if (!text) return [];
        var out = [];
        var start = 0;
        var i = 0;

        function push(end) {
            if (end <= start) return;
            out.push({ s: start, e: end });
            start = end;
        }

        while (i < text.length) {
            var ch = text[i];

            if (ch === '。' || ch === '！' || ch === '？' || ch === '!' || ch === '?') {
                var end = i + 1;
                while (end < text.length) {
                    var c2 = text[end];
                    if (c2 === '。' || c2 === '！' || c2 === '？' || c2 === '!' || c2 === '?') end++;
                    else break;
                }
                while (end < text.length && isWS(text[end])) end++;
                push(end);
                i = end;
                continue;
            }

            if (ch === '.') {
                var j = i;
                while (j < text.length && text[j] === '.') j++;

                var prev = i > 0 ? text[i - 1] : '';
                var next = j < text.length ? text[j] : '';
                var dotCount = j - i;

                // Single dot between ASCII alnum => likely domain/email/decimal/version; do not split.
                if (dotCount === 1 && isAsciiAlnum(prev) && isAsciiAlnum(next)) {
                    i = j;
                    continue;
                }

                var end2 = j;
                while (end2 < text.length && isWS(text[end2])) end2++;
                push(end2);
                i = end2;
                continue;
            }

            i++;
        }

        if (start < text.length) out.push({ s: start, e: text.length });
        return out;
    }

    function getElementData(host) {
        var cached = elementCache.get(host);
        if (cached) return cached;

        var walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, null, false);
        var nodes = [];
        var starts = [];
        var nodeStart = new Map();
        var pos = 0;
        var rawParts = [];

        var n;
        while ((n = walker.nextNode())) {
            var t = n.nodeValue || '';
            starts.push(pos);
            nodes.push(n);
            nodeStart.set(n, pos);
            rawParts.push(t);
            pos += t.length;
        }

        var rawText = rawParts.join('');
        var ranges = splitSentenceRanges(rawText);

        cached = {
            nodes: nodes,
            starts: starts,
            nodeStart: nodeStart,
            rawText: rawText,
            ranges: ranges,
        };
        elementCache.set(host, cached);
        return cached;
    }

    function findNodeAtOffset(data, offset) {
        var nodes = data.nodes;
        var starts = data.starts;
        if (!nodes.length) return null;
        if (offset <= 0) return { node: nodes[0], offset: 0 };

        var totalLen = data.rawText.length;
        if (offset >= totalLen) {
            var last = nodes[nodes.length - 1];
            return { node: last, offset: (last.nodeValue || '').length };
        }

        // Binary search for last starts[i] <= offset
        var lo = 0;
        var hi = starts.length - 1;
        var ans = 0;
        while (lo <= hi) {
            var mid = (lo + hi) >> 1;
            if (starts[mid] <= offset) {
                ans = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }

        var node = nodes[ans];
        var inner = offset - starts[ans];
        var len = (node.nodeValue || '').length;
        if (inner < 0) inner = 0;
        if (inner > len) inner = len;
        return { node: node, offset: inner };
    }

    function makeDomRange(host, sentIdx) {
        var data = getElementData(host);
        if (!data.ranges.length) return null;
        if (sentIdx < 0) sentIdx = 0;
        if (sentIdx > data.ranges.length - 1) sentIdx = data.ranges.length - 1;

        var seg = data.ranges[sentIdx];
        var startPos = findNodeAtOffset(data, seg.s);
        var endPos = findNodeAtOffset(data, seg.e);
        if (!startPos || !endPos) return null;

        var r = document.createRange();
        r.setStart(startPos.node, startPos.offset);
        r.setEnd(endPos.node, endPos.offset);
        return r;
    }

    function findSentenceIndex(host, textNode, offsetInNode) {
        var data = getElementData(host);
        if (!data.nodes.length || !data.ranges.length) return null;
        var base = data.nodeStart.get(textNode);
        if (base === undefined || base === null) return null;
        var rawOffset = base + offsetInNode;

        // Linear scan is fine for typical paragraph sizes.
        for (var i = 0; i < data.ranges.length; i++) {
            var seg = data.ranges[i];
            if (rawOffset >= seg.s && rawOffset < seg.e) return i;
        }
        // If at the very end, attach to last.
        if (rawOffset >= data.rawText.length) return data.ranges.length - 1;
        return null;
    }

    function getCaretTextPosition(ev, host) {
        var x = ev.clientX;
        var y = ev.clientY;
        var node = null;
        var offset = 0;

        if (document.caretPositionFromPoint) {
            var pos = document.caretPositionFromPoint(x, y);
            if (pos) {
                node = pos.offsetNode;
                offset = pos.offset;
            }
        } else if (document.caretRangeFromPoint) {
            var range = document.caretRangeFromPoint(x, y);
            if (range) {
                node = range.startContainer;
                offset = range.startOffset;
            }
        }

        if (!node) return null;

        // If it's an element node, try to find a nearby text node.
        if (node.nodeType === 1) {
            var el = node;
            var child = el.childNodes && el.childNodes[offset] ? el.childNodes[offset] : null;
            if (child && child.nodeType === 3) {
                node = child;
                offset = 0;
            } else if (child && child.nodeType === 1) {
                // Find first text node inside child.
                var w = document.createTreeWalker(child, NodeFilter.SHOW_TEXT, null, false);
                var tn = w.nextNode();
                if (tn) {
                    node = tn;
                    offset = 0;
                }
            }
        }

        if (node.nodeType !== 3) return null;
        if (!host.contains(node)) return null;
        return { node: node, offset: offset };
    }

    function mapIndex(fromIndex, fromCount, toCount) {
        if (!toCount || toCount <= 0) return null;
        if (!fromCount || fromCount <= 1 || toCount <= 1) return 0;
        var mapped = Math.round(fromIndex * (toCount - 1) / (fromCount - 1));
        if (mapped < 0) mapped = 0;
        if (mapped > toCount - 1) mapped = toCount - 1;
        return mapped;
    }

    function parseMap(host) {
        var cached = mapCache.get(host);
        if (cached) return cached;
        var mapAttr = host.getAttribute('data-et-map');
        if (!mapAttr) {
            mapCache.set(host, null);
            return null;
        }
        var parts = mapAttr.split(',');
        var arr = [];
        for (var i = 0; i < parts.length; i++) {
            var v = parseInt(parts[i], 10);
            arr.push(isNaN(v) ? 0 : v);
        }
        mapCache.set(host, arr);
        return arr;
    }

    function getMappedSentenceIndex(host, hostIdx, peerCount) {
        var data = getElementData(host);
        var hostCount = data.ranges.length;

        var mapArr = parseMap(host);
        if (mapArr) {
            var expected = host.getAttribute('data-et-sent-count');
            var expectedN = expected ? parseInt(expected, 10) : null;
            if ((!expectedN || expectedN === hostCount) && mapArr.length === hostCount) {
                var mapped = mapArr[hostIdx];
                if (mapped < 0) mapped = 0;
                if (mapped > peerCount - 1) mapped = peerCount - 1;
                return mapped;
            }
        }

        return mapIndex(hostIdx, hostCount, peerCount);
    }

    function getUid(host) {
        if (!host || !host.getAttribute) return null;
        return host.getAttribute('data-et-uid');
    }

    function cssEscape(cls) {
        if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(cls);
        return cls.replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    }

    function findCounterpart(host, pairClass) {
        var want = host.classList.contains('et-src') ? 'et-tr' : 'et-src';
        var uid = getUid(host);
        if (uid) {
            return document.querySelector('.' + want + '[data-et-uid="' + uid + '"]');
        }
        if (!pairClass) return null;
        return document.querySelector('.' + want + '.' + cssEscape(pairClass));
    }

    function ensureUids() {
        var nodes = document.querySelectorAll('.et-src, .et-tr');
        var pendingSrc = Object.create(null);
        var pendingTr = Object.create(null);
        var uidCounter = 0;

        function getQueue(map, key) {
            if (!map[key]) map[key] = [];
            return map[key];
        }

        function newUid() {
            uidCounter += 1;
            return 'js_' + String(uidCounter);
        }

        function pairUp(srcEl, trEl) {
            var existing = srcEl.getAttribute('data-et-uid') || trEl.getAttribute('data-et-uid');
            if (!existing) existing = newUid();
            srcEl.setAttribute('data-et-uid', existing);
            trEl.setAttribute('data-et-uid', existing);
        }

        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var pairClass = findPairClass(el);
            if (!pairClass) continue;

            if (el.classList.contains('et-src')) {
                var trQ = pendingTr[pairClass];
                if (trQ && trQ.length) {
                    pairUp(el, trQ.shift());
                } else {
                    getQueue(pendingSrc, pairClass).push(el);
                }
            } else if (el.classList.contains('et-tr')) {
                var srcQ = pendingSrc[pairClass];
                if (srcQ && srcQ.length) {
                    pairUp(srcQ.shift(), el);
                } else {
                    getQueue(pendingTr, pairClass).push(el);
                }
            }
        }
    }

    function init() {
        if (!ENABLE_SENTENCE_LEVEL) return;
        ensureUids();
        // If the window is resized, cached client rects become stale; simplest is to clear.
        window.addEventListener('resize', function () {
            clearHighlights();
        }, false);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, false);
    } else {
        init();
    }

    document.addEventListener('click', function (ev) {
        var host = closestSrcOrTr(ev.target);
        if (!host) {
            clearHighlights();
            return;
        }

        var caret = getCaretTextPosition(ev, host);
        if (!caret) {
            clearHighlights();
            return;
        }

        var hostIdx = findSentenceIndex(host, caret.node, caret.offset);
        if (hostIdx === null) {
            clearHighlights();
            return;
        }

        var pairClass = findPairClass(host);
        var peer = findCounterpart(host, pairClass);

        clearHighlights();

        var r1 = makeDomRange(host, hostIdx);
        highlightRange(r1);

        if (peer) {
            var peerData = getElementData(peer);
            var peerIdx = getMappedSentenceIndex(host, hostIdx, peerData.ranges.length);
            if (peerIdx !== null) {
                var r2 = makeDomRange(peer, peerIdx);
                highlightRange(r2);
                active = { host: host, hostIdx: hostIdx, peer: peer, peerIdx: peerIdx };
            }
        }
    }, false);
})();
"""


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

    style_tag = f"\n<style id=\"{STYLE_ID}\">\n{HIGHLIGHT_CSS}\n</style>\n"
    script_tag = f"\n<script id=\"{SCRIPT_ID}\">\n{HIGHLIGHT_JS}\n</script>\n"

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
