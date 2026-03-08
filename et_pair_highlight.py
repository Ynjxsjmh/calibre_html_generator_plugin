from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

from et_bilingual_pair import auto_tag_adjacent_zh_pairs_in_soup

STYLE_ID = "et-pair-highlight-style"
SCRIPT_ID = "et-pair-highlight-script"

HIGHLIGHT_CSS = r"""/* et-pair-highlight */

.et-sent {
    cursor: pointer;
}

.et-pair-active {
    background: rgba(255, 238, 140, 0.65);
    border-radius: 3px;
    box-shadow: inset 0 0 0 1px rgba(180, 140, 0, 0.35);
}
"""

HIGHLIGHT_JS = r"""/* et-pair-highlight */
(function () {
    'use strict';

    var ACTIVE_CLASS = 'et-pair-active';
    var PAIR_PREFIX = 'et-pair-';
    var ENABLE_SENTENCE_LEVEL = true;

    try {
        if (document.body && document.body.getAttribute('data-et-sentence-level') === '0') {
            ENABLE_SENTENCE_LEVEL = false;
        }
    } catch (e) {
        // ignore
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

    function closestSentence(el) {
        while (el && el.nodeType === 1) {
            if (el.classList && el.classList.contains('et-sent')) return el;
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

    function normalizeTextWithMap(raw) {
        // Normalize whitespace (\s+ -> single space) and trim, while keeping a mapping
        // from normalized character index -> raw character index.
        // This allows us to split sentences on the normalized text but wrap ranges
        // in the original DOM without destroying markup.
        raw = raw || '';

        var norm = '';
        var map = []; // map[normIndex] = rawIndex

        var i = 0;
        while (i < raw.length && isWS(raw[i])) i++;

        var inWs = false;
        for (; i < raw.length; i++) {
            var ch = raw[i];
            if (isWS(ch)) {
                if (!inWs) {
                    norm += ' ';
                    map.push(i);
                    inWs = true;
                }
            } else {
                norm += ch;
                map.push(i);
                inWs = false;
            }
        }

        // Trim trailing single space introduced by normalization.
        if (norm.length && norm[norm.length - 1] === ' ') {
            norm = norm.slice(0, -1);
            map.pop();
        }

        return { norm: norm, map: map };
    }

    function splitSentenceRanges(text) {
        // Returns [{s: start, e: end}, ...] in the provided (already-normalized) text.
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

        if (start < text.length) push(text.length);
        return out;
    }

    function locateTextPosition(root, index) {
        // Find the {node, offset} for a character index within root.textContent.
        // Includes text inside nested inline elements.
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
        var remaining = index;
        var last = null;
        while (walker.nextNode()) {
            var n = walker.currentNode;
            last = n;
            var v = n.nodeValue || '';
            var len = v.length;
            if (remaining <= len) {
                return { node: n, offset: remaining };
            }
            remaining -= len;
        }
        if (last) {
            return { node: last, offset: (last.nodeValue || '').length };
        }
        return null;
    }

    function wrapRawRangeWithSpan(root, rawStart, rawEnd, sentIndex) {
        if (!root) return false;
        if (rawEnd <= rawStart) return false;

        var startPos = locateTextPosition(root, rawStart);
        var endPos = locateTextPosition(root, rawEnd);
        if (!startPos || !endPos) return false;

        try {
            var range = document.createRange();
            range.setStart(startPos.node, startPos.offset);
            range.setEnd(endPos.node, endPos.offset);
            if (range.collapsed) return false;

            var frag = range.extractContents();
            var span = document.createElement('span');
            span.className = 'et-sent';
            span.setAttribute('data-et-sent', String(sentIndex));
            span.appendChild(frag);
            range.insertNode(span);
            return true;
        } catch (e) {
            return false;
        }
    }

    function sentenceizeBlockPreserveMarkup(blockEl, startIndex) {
        // Wrap sentences inside a leaf block element (e.g. <p>) without losing inline markup (<a>, <i>, <sup>...).
        // Returns the next global sentence index.
        if (!blockEl) return startIndex;
        if (blockEl.querySelector && blockEl.querySelector('.et-sent')) return startIndex;

        var raw = blockEl.textContent || '';
        var normInfo = normalizeTextWithMap(raw);
        var norm = normInfo.norm;
        if (!norm) return startIndex;

        var ranges = splitSentenceRanges(norm);
        if (!ranges.length) return startIndex;

        // Convert normalized ranges to raw ranges.
        var rawRanges = [];
        for (var i = 0; i < ranges.length; i++) {
            var r = ranges[i];
            if (r.e <= r.s) continue;
            var rawStart = normInfo.map[r.s];
            var lastRaw = normInfo.map[r.e - 1];
            if (rawStart === undefined || lastRaw === undefined) continue;
            // Do NOT extend to trailing whitespace.
            // Extending can cross element boundaries (e.g., <a> followed by indentation text nodes)
            // and may leave behind empty elements after Range.extractContents().
            var rawEnd = lastRaw + 1;
            rawRanges.push({ s: rawStart, e: rawEnd });
        }

        if (!rawRanges.length) {
            // Fallback: wrap whole block.
            var wholeWrapped = wrapRawRangeWithSpan(blockEl, 0, raw.length, startIndex);
            return wholeWrapped ? (startIndex + 1) : startIndex;
        }

        // Wrap from end to start so earlier indices remain stable.
        var ok = true;
        for (var j = rawRanges.length - 1; j >= 0; j--) {
            var rr = rawRanges[j];
            var wrapped = wrapRawRangeWithSpan(blockEl, rr.s, rr.e, startIndex + j);
            if (!wrapped) ok = false;
        }

        if (!ok) {
            // If we partially failed, don't leave the block half-wrapped; best-effort fallback
            // is to just wrap the whole block as a single sentence.
            // (We avoid attempting a complex rollback here.)
        }

        return startIndex + rawRanges.length;
    }

    function getSentenceTargets(host) {
        // Strategy:
        // - If host itself is a leaf block (no nested block descendants), sentenceize host.
        // - Otherwise, sentenceize leaf block descendants (typically <p> inside <li>/<ol>).
        // This prevents invalid HTML like putting <span> directly under <ol> and avoids
        // wrapping ranges across block boundaries.
        var BLOCK_SELECTOR = 'p,li,dt,dd,blockquote,pre,th,td,h1,h2,h3,h4,h5,h6,div';
        var targets = [];

        if (!host || !host.querySelector) return targets;

        if (host.matches && host.matches(BLOCK_SELECTOR) && !host.querySelector(BLOCK_SELECTOR)) {
            targets.push(host);
            return targets;
        }

        var nodes = host.querySelectorAll(BLOCK_SELECTOR);
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el || !el.querySelector) continue;
            if (el.querySelector(BLOCK_SELECTOR)) continue; // not a leaf block
            targets.push(el);
        }

        if (!targets.length) targets.push(host);
        return targets;
    }

    function sentenceizeHost(host) {
        if (!host) return;
        if (host.querySelector && host.querySelector('.et-sent')) return;

        var targets = getSentenceTargets(host);
        var idx = 0;
        for (var i = 0; i < targets.length; i++) {
            idx = sentenceizeBlockPreserveMarkup(targets[i], idx);
        }

        if (!host.getAttribute('data-et-sent-count')) {
            host.setAttribute('data-et-sent-count', String(idx));
        }
    }

    function ensureUidsAndSentenceize() {
        var nodes = document.querySelectorAll('.et-src, .et-tr');
        var pendingSrc = Object.create(null);
        var pendingTr = Object.create(null);
        var uidCounter = 0;

        function getQueue(map, key) {
            if (!map[key]) map[key] = [];
            return map[key];
        }

        function pairUp(srcEl, trEl) {
            var existing = srcEl.getAttribute('data-et-uid') || trEl.getAttribute('data-et-uid');
            if (!existing) {
                uidCounter += 1;
                existing = String(uidCounter);
            }
            srcEl.setAttribute('data-et-uid', existing);
            trEl.setAttribute('data-et-uid', existing);

            sentenceizeHost(srcEl);
            sentenceizeHost(trEl);
        }

        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var pairClass = findPairClass(el);
            if (!pairClass) continue;

            // Always sentence-split (without losing markup), even if pairing fails.
            sentenceizeHost(el);

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
        if (ENABLE_SENTENCE_LEVEL) ensureUidsAndSentenceize();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, false);
    } else {
        init();
    }

    function clearActive() {
        var active = document.querySelectorAll('.' + ACTIVE_CLASS);
        for (var i = 0; i < active.length; i++) {
            active[i].classList.remove(ACTIVE_CLASS);
        }
    }

    function cssEscape(cls) {
        if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(cls);
        return cls.replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    }

    function mapIndex(fromIndex, fromCount, toCount) {
        if (!toCount || toCount <= 0) return null;
        if (!fromCount || fromCount <= 1 || toCount <= 1) return 0;
        var mapped = Math.round(fromIndex * (toCount - 1) / (fromCount - 1));
        if (mapped < 0) mapped = 0;
        if (mapped > toCount - 1) mapped = toCount - 1;
        return mapped;
    }

    function getUid(host) {
        if (!host || !host.getAttribute) return null;
        return host.getAttribute('data-et-uid');
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

    function highlightParagraph(host, pairClass) {
        var uid = getUid(host);
        clearActive();

        if (uid) {
            var byUid = document.querySelectorAll('[data-et-uid="' + uid + '"]');
            for (var i = 0; i < byUid.length; i++) byUid[i].classList.add(ACTIVE_CLASS);
            return;
        }

        if (!pairClass) return;
        var selector = '.' + cssEscape(pairClass);
        var pairNodes = document.querySelectorAll(selector);
        for (var j = 0; j < pairNodes.length; j++) pairNodes[j].classList.add(ACTIVE_CLASS);
    }

    function highlightSentence(sentenceEl, host, pairClass) {
        var idx = parseInt(sentenceEl.getAttribute('data-et-sent'), 10);
        if (isNaN(idx)) return;

        var peer = findCounterpart(host, pairClass);
        clearActive();
        sentenceEl.classList.add(ACTIVE_CLASS);

        if (!peer) return;

        // If explicit per-sentence mapping exists, use it.
        // 1) Legacy per-span mapping: data-et-to="3,4"
        var toAttr = sentenceEl.getAttribute('data-et-to');
        if (toAttr) {
            var parts = toAttr.split(',');
            for (var k = 0; k < parts.length; k++) {
                var t = parseInt(parts[k], 10);
                if (isNaN(t)) continue;
                var otherMapped = peer.querySelector('.et-sent[data-et-sent="' + t + '"]');
                if (otherMapped) otherMapped.classList.add(ACTIVE_CLASS);
            }
            return;
        }

        // 2) Host-level mapping produced by `et_sentence_align.py`: data-et-map="0,0,1,2,..."
        // Use it only if sentence counts match.
        var mapAttr = host.getAttribute('data-et-map');
        if (mapAttr) {
            var fromCount2 = host.querySelectorAll('.et-sent').length;
            var toCount2 = peer.querySelectorAll('.et-sent').length;
            var sentCountAttr = host.getAttribute('data-et-sent-count');
            var expectedFrom = sentCountAttr ? parseInt(sentCountAttr, 10) : null;
            var parts2 = mapAttr.split(',');
            if ((!expectedFrom || expectedFrom === fromCount2) && parts2.length === fromCount2) {
                var mapped2 = parseInt(parts2[idx], 10);
                if (!isNaN(mapped2)) {
                    if (mapped2 < 0) mapped2 = 0;
                    if (mapped2 > toCount2 - 1) mapped2 = toCount2 - 1;
                    var other2 = peer.querySelector('.et-sent[data-et-sent="' + mapped2 + '"]');
                    if (other2) other2.classList.add(ACTIVE_CLASS);
                    return;
                }
            }
        }

        // Fallback: relative-position mapping.
        var fromCount = host.querySelectorAll('.et-sent').length;
        var toCount = peer.querySelectorAll('.et-sent').length;
        var mapped = mapIndex(idx, fromCount, toCount);
        if (mapped === null) return;

        var other = peer.querySelector('.et-sent[data-et-sent="' + mapped + '"]');
        if (other) other.classList.add(ACTIVE_CLASS);
    }

    document.addEventListener('click', function (ev) {
        var sentenceEl = closestSentence(ev.target);
        if (sentenceEl) {
            var host = closestSrcOrTr(sentenceEl);
            if (!host) return;
            var pairClass = findPairClass(host);
            highlightSentence(sentenceEl, host, pairClass);
            return;
        }

        var host2 = closestSrcOrTr(ev.target);
        // Paragraph click highlighting is intentionally disabled.
        // Click outside sentences (or anywhere else) clears highlight.
        clearActive();
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
