/* et-toc-sidebar */
(function () {
    'use strict';

    var SIDEBAR_ID = 'et-toc-sidebar';
    var SIDEBAR_BODY_ID = 'et-toc-sidebar-body';
    var TOP_ID = 'et-toc-top';

    var DEFAULT_WIDTH = 320;
    var COLLAPSED_WIDTH = 34;
    var MIN_WIDTH = 180;

    // Persisted UI state (localStorage)
    var KEY_TOC_WIDTH = 'et-toc-width';
    var KEY_TOC_SIDE = 'et-toc-side';
    var KEY_TOC_STATE = 'et-toc-state';
    var KEY_PAIR_HIGHLIGHT = 'et-pair-highlight-enabled';

    function safeGet(key) {
        try {
            return window.localStorage ? window.localStorage.getItem(key) : null;
        } catch (e) {
            return null;
        }
    }

    function safeSet(key, value) {
        try {
            if (window.localStorage) window.localStorage.setItem(key, String(value));
        } catch (e) {
            // ignore
        }
    }

    function readNumber(key) {
        var raw = safeGet(key);
        if (!raw) return null;
        var n = Number(raw);
        return isFinite(n) ? n : null;
    }

    function readBool(key) {
        var raw = safeGet(key);
        if (raw === null || raw === undefined) return null;
        var s = String(raw).toLowerCase();
        if (s === '1' || s === 'true' || s === 'yes' || s === 'on') return true;
        if (s === '0' || s === 'false' || s === 'no' || s === 'off') return false;
        return null;
    }

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    function normalizeText(s) {
        return (s || '').replace(/\s+/g, ' ').trim();
    }

    function closestAnchor(el) {
        if (!el) return null;
        if (el.closest) return el.closest('a');
        while (el && el.nodeType === 1) {
            if (el.tagName === 'A') return el;
            el = el.parentElement;
        }
        return null;
    }

    onReady(function () {
        var sidebar = document.getElementById(SIDEBAR_ID);
        if (!sidebar) return;

        var sidebarBody = document.getElementById(SIDEBAR_BODY_ID);
        var collapseBtn = document.getElementById('et-toc-collapse-btn');
        var sideBtn = document.getElementById('et-toc-side-btn');
        var highlightBtn = document.getElementById('et-toc-highlight-btn');
        var resizer = document.getElementById('et-toc-resizer');

        if (!resizer) {
            try {
                resizer = document.createElement('div');
                resizer.id = 'et-toc-resizer';
                resizer.className = 'et-toc-resizer';
                resizer.setAttribute('aria-hidden', 'true');
                sidebar.appendChild(resizer);
            } catch (e0) {
                // ignore
            }
        }

        // Reserve space for the fixed TOC sidebar using *padding* (not margins).
        // Using body margins here can create horizontal overflow/clipping when the reader column is centered.
        // Keep the original inline paddings so overlay mode can restore the ebook's defaults.
        var bodyInlinePL = '';
        var bodyInlinePR = '';
        try {
            if (document.body) {
                bodyInlinePL = document.body.style.paddingLeft || '';
                bodyInlinePR = document.body.style.paddingRight || '';
            }
        } catch (eInlinePad) {
            // ignore
        }

        var basePL = '0px';
        var basePR = '0px';
        var basePaddingDirty = true;

        function refreshBaseBodyPadding() {
            if (!document.body) return;
            basePaddingDirty = false;

            var oldPL = '';
            var oldPR = '';
            try {
                oldPL = document.body.style.paddingLeft || '';
                oldPR = document.body.style.paddingRight || '';
                // Temporarily reset to the ebook's original inline styles so computed values reflect the base CSS.
                document.body.style.paddingLeft = bodyInlinePL;
                document.body.style.paddingRight = bodyInlinePR;
            } catch (eResetPad) {
                // ignore
            }

            try {
                var cs0 = window.getComputedStyle(document.body);
                basePL = cs0.paddingLeft || '0px';
                basePR = cs0.paddingRight || '0px';
            } catch (ePad) {
                basePL = '0px';
                basePR = '0px';
            }

            try {
                document.body.style.paddingLeft = oldPL;
                document.body.style.paddingRight = oldPR;
            } catch (eRestorePad) {
                // ignore
            }
        }

        // Overlay mode should only apply to phone-like (narrow) *touch* screens.
        // Do NOT apply it to narrow desktop windows, otherwise the sidebar will overlap content.
        function isTouchLikeDevice() {
            try {
                if (window.matchMedia) {
                    if (window.matchMedia('(pointer: coarse)').matches) return true;
                    if (window.matchMedia('(hover: none)').matches) return true;
                }
            } catch (e0) {
                // ignore
            }
            try {
                if (navigator && typeof navigator.maxTouchPoints === 'number') {
                    return navigator.maxTouchPoints > 0;
                }
            } catch (e1) {
                // ignore
            }
            try {
                return ('ontouchstart' in window);
            } catch (e2) {
                return false;
            }
        }

        function isOverlayMode() {
            var w = 0;
            try {
                w = (window.innerWidth || 0);
            } catch (eW) {
                w = 0;
            }
            return w <= 768 && isTouchLikeDevice();
        }

        var tocIndex = null; // [{ tocId, href, top }]
        var tocIdToHref = null; // { tocId: href }
        var tocDirty = true;
        var activeTocId = null;
        var activeSidebarLink = null;
        var sidebarHrefMap = null; // { href: <a> }
        var rafPending = false;
        var lastReadingAnchor = null;
        var readingAnchorRafPending = false;
        var readingAnchorTimer = 0;
        var restoreRafPending = false;
        var pendingRestoreAnchor = null;
        var restoreGuardTimer = 0;
        var isRestoringViewport = false;
        var activeDragAnchor = null;
        var resizeSessionAnchor = null;
        var resizeSettleTimer = 0;
        var overlaySessionAnchor = null;
        var overlaySessionDirty = false;

        // Restore persisted state (do not write back during init).
        var savedSide = safeGet(KEY_TOC_SIDE);
        if (savedSide !== 'left' && savedSide !== 'right') savedSide = null;

        var savedState = safeGet(KEY_TOC_STATE);
        if (savedState !== 'collapsed' && savedState !== 'expanded') savedState = null;

        var savedWidth = readNumber(KEY_TOC_WIDTH);

        var savedHighlight = readBool(KEY_PAIR_HIGHLIGHT);
        if (savedHighlight !== null) {
            window.etHighlightEnabled = savedHighlight;
        }

        function setCollapseButtonLabel(collapsed) {
            if (!collapseBtn) return;
            // Match the html_generator implementation: keep the label intact and
            // let the narrow collapsed width naturally wrap CJK text (e.g. "目录" -> "目/录").
            collapseBtn.textContent = collapsed ? '目录' : '收起';
        }

        function isHighlightEnabled() {
            if (!highlightBtn) return true;
            return highlightBtn.getAttribute('data-et-highlight-enabled') !== 'false';
        }

        function setHighlightButtonLabel() {
            if (!highlightBtn) return;
            var enabled = isHighlightEnabled();
            var label = enabled ? '禁用' : '启用';
            // Same as collapse button: rely on wrapping instead of injecting '\n'.
            highlightBtn.textContent = label;
        }

        function clamp(n, lo, hi) {
            if (n < lo) return lo;
            if (n > hi) return hi;
            return n;
        }

        function raf(cb) {
            var fn = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };
            return fn(cb);
        }

        function clearTimer(timerId) {
            if (!timerId) return 0;
            try {
                window.clearTimeout(timerId);
            } catch (eT) {
                // ignore
            }
            return 0;
        }

        function getScrollX() {
            return window.scrollX || window.pageXOffset || 0;
        }

        function getScrollY() {
            return window.scrollY || window.pageYOffset || 0;
        }

        function parsePx(v) {
            var n = parseFloat(v || '0');
            return isFinite(n) ? n : 0;
        }

        function isNodeConnected(node) {
            if (!node) return false;
            try {
                if (node.isConnected) return true;
            } catch (eNC0) {
                // ignore
            }
            try {
                return !!(document.documentElement && document.documentElement.contains(node));
            } catch (eNC1) {
                return false;
            }
        }

        function isIgnoredAnchorElement(el) {
            if (!el) return true;
            try {
                if (sidebar && sidebar.contains(el)) return true;
            } catch (eIA0) {
                // ignore
            }
            try {
                var pos = window.getComputedStyle(el).position || '';
                if (pos === 'fixed') return true;
            } catch (eIA1) {
                // ignore
            }
            return false;
        }

        function isIgnoredAnchorNode(node) {
            if (!node) return true;
            if (node.nodeType === 1) return isIgnoredAnchorElement(node);
            return isIgnoredAnchorElement(node.parentElement || null);
        }

        function firstTextDescendant(root) {
            if (!root || root.nodeType !== 1) return null;
            try {
                var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
                return walker.nextNode();
            } catch (eTW) {
                return null;
            }
        }

        function firstMeaningfulOffset(text) {
            var s = text || '';
            for (var i = 0; i < s.length; i++) {
                if (!/\s/.test(s.charAt(i))) return i;
            }
            return 0;
        }

        function findTextNodeNearOffset(el, startIndex) {
            if (!el || el.nodeType !== 1 || !el.childNodes) return null;
            var total = el.childNodes.length;
            if (!total) return null;

            var idx = clamp(typeof startIndex === 'number' ? startIndex : 0, 0, total);
            for (var dist = 0; dist <= total; dist++) {
                var left = idx - dist;
                if (left >= 0 && left < total) {
                    var leftNode = el.childNodes[left];
                    if (leftNode) {
                        if (leftNode.nodeType === 3) return leftNode;
                        var leftText = firstTextDescendant(leftNode);
                        if (leftText) return leftText;
                    }
                }

                var right = idx + dist;
                if (dist && right >= 0 && right < total) {
                    var rightNode = el.childNodes[right];
                    if (rightNode) {
                        if (rightNode.nodeType === 3) return rightNode;
                        var rightText = firstTextDescendant(rightNode);
                        if (rightText) return rightText;
                    }
                }
            }

            return firstTextDescendant(el);
        }

        function resolveTextPosition(node, offset) {
            if (!node) return null;

            if (node.nodeType === 3) {
                var textLen = (node.nodeValue || '').length;
                var nextOffset = typeof offset === 'number' ? offset : 0;
                if (nextOffset < 0) nextOffset = 0;
                if (nextOffset > textLen) nextOffset = textLen;
                return { node: node, offset: nextOffset };
            }

            if (node.nodeType !== 1) return null;

            var textNode = findTextNodeNearOffset(node, offset);
            if (!textNode) return null;
            return {
                node: textNode,
                offset: firstMeaningfulOffset(textNode.nodeValue || '')
            };
        }

        function getCaretTextPositionAtPoint(x, y) {
            var node = null;
            var offset = 0;

            try {
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
            } catch (eCP) {
                node = null;
            }

            var resolved = resolveTextPosition(node, offset);
            if (!resolved) return null;
            if (isIgnoredAnchorNode(resolved.node)) return null;
            return resolved;
        }

        function getReadingSampleXs() {
            var width = Math.max(
                window.innerWidth || 0,
                document.documentElement ? (document.documentElement.clientWidth || 0) : 0
            );
            if (!width) return [24];

            var minX = 12;
            var maxX = Math.max(12, width - 12);

            if (isOverlayMode() && !isCollapsed()) {
                var overlaySide = sidebar.getAttribute('data-et-toc-side') || 'left';
                var overlayWidth = getSidebarWidthPx();
                var visibleLeft = minX;
                var visibleRight = maxX;

                if (overlaySide === 'right') {
                    visibleRight = clamp(Math.round(width - overlayWidth - 12), minX, maxX);
                } else {
                    visibleLeft = clamp(Math.round(overlayWidth + 12), minX, maxX);
                }

                if (visibleRight - visibleLeft < 24) return [];

                var overlayXs = [];
                function pushOverlayX(val) {
                    for (var oi = 0; oi < overlayXs.length; oi++) {
                        if (Math.abs(overlayXs[oi] - val) < 2) return;
                    }
                    overlayXs.push(val);
                }

                pushOverlayX(clamp(Math.round(visibleLeft + 12), visibleLeft, visibleRight));
                pushOverlayX(clamp(Math.round(visibleLeft + 56), visibleLeft, visibleRight));
                pushOverlayX(clamp(Math.round((visibleLeft + visibleRight) / 2), visibleLeft, visibleRight));
                pushOverlayX(clamp(Math.round(visibleRight - 20), visibleLeft, visibleRight));
                return overlayXs;
            }

            var bodyPL = 0;
            var bodyPR = 0;
            try {
                var bodyCS = window.getComputedStyle(document.body);
                bodyPL = parsePx(bodyCS.paddingLeft);
                bodyPR = parsePx(bodyCS.paddingRight);
            } catch (eGX) {
                bodyPL = 0;
                bodyPR = 0;
            }

            var left = clamp(Math.round(bodyPL + 24), minX, maxX);
            var leftWide = clamp(Math.round(bodyPL + 88), minX, maxX);
            var right = clamp(Math.round(width - bodyPR - 24), minX, maxX);
            var center = clamp(Math.round((left + right) / 2), minX, maxX);

            var xs = [];
            function pushX(val) {
                for (var i = 0; i < xs.length; i++) {
                    if (Math.abs(xs[i] - val) < 2) return;
                }
                xs.push(val);
            }

            pushX(left);
            pushX(leftWide);
            pushX(center);
            pushX(right);
            return xs;
        }

        function getReadingSampleYs() {
            var viewportH = Math.max(
                window.innerHeight || 0,
                document.documentElement ? (document.documentElement.clientHeight || 0) : 0
            );
            var ys = [8, 14, 22, 32, 44, 60, 78, 98];
            var out = [];
            for (var i = 0; i < ys.length; i++) {
                if (viewportH && ys[i] > viewportH - 8) continue;
                out.push(ys[i]);
            }
            return out.length ? out : [8];
        }

        function buildScrollFallbackAnchor(viewportY) {
            return {
                node: null,
                offset: 0,
                element: null,
                viewportY: typeof viewportY === 'number' ? viewportY : 0,
                scrollX: getScrollX(),
                scrollY: getScrollY(),
                isScrollFallback: true
            };
        }

        function buildReadingAnchor(node, offset, element, viewportY) {
            if (!node && !element) return null;
            var anchorElement = element || (node ? (node.nodeType === 1 ? node : node.parentElement) : null);
            if (anchorElement && isIgnoredAnchorElement(anchorElement)) return null;
            return {
                node: node || null,
                offset: typeof offset === 'number' ? offset : 0,
                element: anchorElement || null,
                viewportY: viewportY,
                scrollX: getScrollX(),
                scrollY: getScrollY(),
                isScrollFallback: false
            };
        }

        function captureVisibleHashTargetAnchor() {
            var h = location.hash || '';
            if (!h || h.charAt(0) !== '#') return null;
            if (h.indexOf('#toc_') === 0) return null;

            var target = document.getElementById(h.slice(1));
            if (!target || isIgnoredAnchorElement(target)) return null;

            var rect = null;
            try {
                rect = target.getBoundingClientRect();
            } catch (eHT0) {
                rect = null;
            }
            if (!rect) return null;

            var viewportH = Math.max(
                window.innerHeight || 0,
                document.documentElement ? (document.documentElement.clientHeight || 0) : 0
            );
            if (rect.bottom < -4) return null;
            if (viewportH && rect.top > viewportH * 0.65) return null;

            var viewportY = rect.top;
            if (!isFinite(viewportY)) viewportY = 0;
            if (viewportY < 0) viewportY = 0;
            if (viewportH && viewportY > viewportH - 8) viewportY = Math.max(0, viewportH - 8);

            return buildReadingAnchor(null, 0, target, viewportY);
        }

        function captureReadingAnchor() {
            if (!document.body) return null;

            var xs = getReadingSampleXs();
            var ys = getReadingSampleYs();
            if (!xs.length) return buildScrollFallbackAnchor(ys.length ? ys[0] : 0);

            for (var i = 0; i < ys.length; i++) {
                for (var j = 0; j < xs.length; j++) {
                    var x = xs[j];
                    var y = ys[i];
                    var pos = getCaretTextPositionAtPoint(x, y);
                    if (pos) {
                        return buildReadingAnchor(pos.node, pos.offset, pos.node.parentElement || null, y);
                    }

                    var el = null;
                    try {
                        el = document.elementFromPoint(x, y);
                    } catch (eEF) {
                        el = null;
                    }
                    if (!el || isIgnoredAnchorElement(el)) continue;
                    if (el === document.documentElement || el === document.body) continue;

                    var textNode = firstTextDescendant(el);
                    if (textNode) {
                        return buildReadingAnchor(
                            textNode,
                            firstMeaningfulOffset(textNode.nodeValue || ''),
                            el,
                            y
                        );
                    }
                    return buildReadingAnchor(null, 0, el, y);
                }
            }

            return buildScrollFallbackAnchor(ys.length ? ys[0] : 0);
        }

        function createTextRange(anchor) {
            if (!anchor || !anchor.node || !isNodeConnected(anchor.node)) return null;

            var text = anchor.node.nodeValue || '';
            var len = text.length;
            var start = typeof anchor.offset === 'number' ? anchor.offset : 0;
            if (start < 0) start = 0;
            if (start > len) start = len;

            var range = document.createRange();
            if (!len) {
                range.setStart(anchor.node, 0);
                range.setEnd(anchor.node, 0);
                return range;
            }

            if (start >= len) {
                range.setStart(anchor.node, len - 1);
                range.setEnd(anchor.node, len);
                return range;
            }

            range.setStart(anchor.node, start);
            range.setEnd(anchor.node, Math.min(start + 1, len));
            return range;
        }

        function getRectFromRange(range) {
            if (!range) return null;
            try {
                var rects = range.getClientRects();
                if (rects && rects.length) return rects[0];
            } catch (eGR0) {
                // ignore
            }
            try {
                var rect = range.getBoundingClientRect();
                if (rect && (rect.height || rect.width || rect.top || rect.bottom)) return rect;
            } catch (eGR1) {
                // ignore
            }
            return null;
        }

        function getAnchorRect(anchor) {
            if (!anchor) return null;

            var rect = null;
            try {
                rect = getRectFromRange(createTextRange(anchor));
            } catch (eAR0) {
                rect = null;
            }
            if (rect) return rect;

            var el = anchor.element;
            if ((!el || !isNodeConnected(el)) && anchor.node) {
                el = anchor.node.parentElement || null;
            }
            if (!el || !isNodeConnected(el) || isIgnoredAnchorElement(el)) return null;
            try {
                return el.getBoundingClientRect();
            } catch (eAR1) {
                return null;
            }
        }

        function beginRestoreGuard() {
            isRestoringViewport = true;
            readingAnchorTimer = clearTimer(readingAnchorTimer);
            restoreGuardTimer = clearTimer(restoreGuardTimer);
            try {
                restoreGuardTimer = window.setTimeout(function () {
                    isRestoringViewport = false;
                    restoreGuardTimer = 0;
                }, 120);
            } catch (eRG) {
                isRestoringViewport = false;
            }
        }

        function restoreReadingAnchor(anchor) {
            if (!anchor) return false;

            var rect = getAnchorRect(anchor);
            if (!rect) {
                var fallbackX = isFinite(anchor.scrollX) ? anchor.scrollX : getScrollX();
                var fallbackY = isFinite(anchor.scrollY) ? anchor.scrollY : getScrollY();
                if (fallbackY < 0) fallbackY = 0;

                beginRestoreGuard();
                try {
                    window.scrollTo({ left: fallbackX, top: fallbackY, behavior: 'auto' });
                    return true;
                } catch (eRF0) {
                    try {
                        window.scrollTo(fallbackX, fallbackY);
                        return true;
                    } catch (eRF1) {
                        return false;
                    }
                }
            }

            var top = rect.top;
            var targetY = typeof anchor.viewportY === 'number' ? anchor.viewportY : 0;
            if (!isFinite(top) || !isFinite(targetY)) return false;

            var delta = top - targetY;
            if (!isFinite(delta) || Math.abs(delta) < 1) return true;

            var nextY = getScrollY() + delta;
            if (nextY < 0) nextY = 0;

            beginRestoreGuard();
            try {
                window.scrollTo({ left: getScrollX(), top: nextY, behavior: 'auto' });
                return true;
            } catch (eRS0) {
                try {
                    window.scrollTo(getScrollX(), nextY);
                    return true;
                } catch (eRS1) {
                    return false;
                }
            }
        }

        function scheduleBaselineAnchorCapture() {
            if (readingAnchorRafPending || isRestoringViewport) return;
            readingAnchorRafPending = true;
            raf(function () {
                readingAnchorRafPending = false;
                if (isRestoringViewport) return;
                var anchor = captureReadingAnchor();
                if (anchor) lastReadingAnchor = anchor;
            });
        }

        function scheduleDelayedBaselineAnchorCapture(delay) {
            readingAnchorTimer = clearTimer(readingAnchorTimer);
            try {
                readingAnchorTimer = window.setTimeout(function () {
                    readingAnchorTimer = 0;
                    scheduleBaselineAnchorCapture();
                }, delay || 0);
            } catch (eRC) {
                scheduleBaselineAnchorCapture();
            }
        }

        function scheduleReadingAnchorRestore(anchor) {
            if (!anchor) return;
            pendingRestoreAnchor = anchor;
            if (restoreRafPending) return;
            restoreRafPending = true;
            raf(function () {
                restoreRafPending = false;
                var nextAnchor = pendingRestoreAnchor;
                pendingRestoreAnchor = null;
                if (!nextAnchor) return;
                if (restoreReadingAnchor(nextAnchor)) {
                    scheduleDelayedBaselineAnchorCapture(140);
                }
            });
        }

        function startOverlaySession(anchor) {
            overlaySessionAnchor = anchor || null;
            overlaySessionDirty = false;
        }

        function markOverlaySessionDirty() {
            if (!overlaySessionAnchor) return;
            overlaySessionDirty = true;
        }

        function clearOverlaySession() {
            overlaySessionAnchor = null;
            overlaySessionDirty = false;
        }

        function runWithPreservedReadingPosition(action, preferredAnchor) {
            if (typeof action !== 'function') return;

            var anchor = preferredAnchor || null;
            if (!anchor && isOverlayMode() && !isCollapsed()) {
                anchor = captureVisibleHashTargetAnchor();
            }
            if (!anchor) anchor = captureReadingAnchor() || lastReadingAnchor;
            action();

            if (anchor) {
                scheduleReadingAnchorRestore(anchor);
            } else {
                scheduleDelayedBaselineAnchorCapture(0);
            }
        }

        function markTocDirty() {
            tocDirty = true;
        }

        function rebuildTocIndex() {
            tocDirty = false;
            tocIndex = [];
            tocIdToHref = Object.create(null);

            var top = document.getElementById(TOP_ID);
            if (!top) return;

            var links = top.querySelectorAll('a[id^="toc_"][href^="#"]');
            for (var i = 0; i < links.length; i++) {
                var a = links[i];
                var tocId = a.getAttribute('id');
                var href = a.getAttribute('href') || '';
                if (!tocId || href.charAt(0) !== '#') continue;
                var targetId = href.slice(1);
                if (!targetId) continue;
                var target = document.getElementById(targetId);
                if (!target) continue;
                var topPx = 0;
                try {
                    topPx = target.getBoundingClientRect().top + window.scrollY;
                } catch (e2) {
                    topPx = 0;
                }
                tocIdToHref[tocId] = href;
                tocIndex.push({ tocId: tocId, href: href, top: topPx });
            }

            tocIndex.sort(function (x, y) { return x.top - y.top; });
        }

        function ensureTocIndex() {
            if (!tocIndex || tocDirty) rebuildTocIndex();
        }

        function scheduleActiveUpdate() {
            // If the sidebar TOC is hidden (collapsed), there is nothing visible to sync.
            // Skipping work here avoids scroll-jank on mobile.
            try {
                if (sidebar.getAttribute('data-et-toc-state') === 'collapsed') return;
            } catch (e0) {
                // ignore
            }

            if (rafPending) return;
            rafPending = true;
            raf(function () {
                rafPending = false;
                updateActiveFromScroll();
            });
        }

        function getSidebarWidthPx() {
            try {
                var w = sidebar.getBoundingClientRect().width;
                if (w && w > 0) return Math.round(w);
            } catch (eW) {
                // ignore
            }
            var collapsed = sidebar.getAttribute('data-et-toc-state') === 'collapsed';
            return collapsed ? COLLAPSED_WIDTH : DEFAULT_WIDTH;
        }

        function setSidebarWidthPx(px) {
            try {
                sidebar.style.setProperty('--et-toc-width', px + 'px');
            } catch (eS) {
                // ignore
            }
        }

        function applyBodyOffset() {
            if (!document.body) return;

            if (basePaddingDirty) refreshBaseBodyPadding();

            // On mobile devices, let the TOC overlay.
            // When *collapsed* in overlay mode, reserve a tiny gutter so the header buttons
            // don't cover the first characters of the text.
            if (isOverlayMode()) {
                try {
                    sidebar.setAttribute('data-et-toc-overlay', '1');
                } catch (eOA) {
                    // ignore
                }

                var oSide = sidebar.getAttribute('data-et-toc-side') || 'left';
                var oCollapsed = sidebar.getAttribute('data-et-toc-state') === 'collapsed';

                try {
                    if (oCollapsed) {
                        if (oSide === 'right') {
                            document.body.style.setProperty(
                                'padding-right',
                                'calc(' + basePR + ' + ' + COLLAPSED_WIDTH + 'px)',
                                'important'
                            );
                            document.body.style.setProperty('padding-left', bodyInlinePL, '');
                        } else {
                            document.body.style.setProperty(
                                'padding-left',
                                'calc(' + basePL + ' + ' + COLLAPSED_WIDTH + 'px)',
                                'important'
                            );
                            document.body.style.setProperty('padding-right', bodyInlinePR, '');
                        }
                    } else {
                        document.body.style.setProperty('padding-left', bodyInlinePL, '');
                        document.body.style.setProperty('padding-right', bodyInlinePR, '');
                    }
                } catch (ePad0) {
                    // ignore
                }
                return;
            }

            try {
                sidebar.removeAttribute('data-et-toc-overlay');
            } catch (eOR) {
                // ignore
            }

            var side = sidebar.getAttribute('data-et-toc-side') || 'left';
            var w = getSidebarWidthPx();
            try {
                if (side === 'right') {
                    document.body.style.setProperty('padding-right', 'calc(' + basePR + ' + ' + w + 'px)', 'important');
                    document.body.style.setProperty('padding-left', basePL, 'important');
                } else {
                    document.body.style.setProperty('padding-left', 'calc(' + basePL + ' + ' + w + 'px)', 'important');
                    document.body.style.setProperty('padding-right', basePR, 'important');
                }
            } catch (ePad1) {
                // ignore
            }
        }

        function setCollapsed(collapsed) {
            sidebar.setAttribute('data-et-toc-state', collapsed ? 'collapsed' : 'expanded');
            setCollapseButtonLabel(collapsed);
            setHighlightButtonLabel();
            // Hide the side-switch button in collapsed state (compact rail).
            // Use inline style to win over any ebook CSS.
            if (sideBtn) sideBtn.style.display = collapsed ? 'none' : '';
            applyBodyOffset();
            if (!collapsed) ensureSidebarToc();
            markTocDirty();
            scheduleActiveUpdate();
        }

        function setSide(side) {
            sidebar.setAttribute('data-et-toc-side', side === 'right' ? 'right' : 'left');
            if (sideBtn) sideBtn.textContent = (side === 'right') ? '左侧' : '右侧';
            applyBodyOffset();
            // Width typically unchanged, but keep the index fresh for safety.
            markTocDirty();
            scheduleActiveUpdate();
        }

        // Resizable width (mouse drag)
        if (resizer) {
            resizer.addEventListener('mousedown', function (e) {
                try {
                    if (e && typeof e.button === 'number' && e.button !== 0) return;
                } catch (ignoreBtn) {
                    // ignore
                }

                if (sidebar.getAttribute('data-et-toc-state') === 'collapsed') return;

                var startX = e.clientX;
                var startWidth = getSidebarWidthPx();
                var side = sidebar.getAttribute('data-et-toc-side') || 'left';
                activeDragAnchor = captureReadingAnchor() || lastReadingAnchor;

                var prevUserSelect = '';
                var prevCursor = '';
                try {
                    if (document.body) {
                        prevUserSelect = document.body.style.userSelect || '';
                        document.body.style.userSelect = 'none';
                    }
                    prevCursor = document.documentElement.style.cursor || '';
                    document.documentElement.style.cursor = 'ew-resize';
                } catch (eStyle) {
                    // ignore
                }

                function onMove(ev) {
                    var dx = ev.clientX - startX;
                    var next = startWidth + (side === 'right' ? -dx : dx);

                    var maxW = Math.floor(window.innerWidth * 0.75);
                    if (!maxW || maxW < MIN_WIDTH) maxW = MIN_WIDTH;
                    next = clamp(next, MIN_WIDTH, maxW);

                    setSidebarWidthPx(next);
                    applyBodyOffset();
                    if (activeDragAnchor) scheduleReadingAnchorRestore(activeDragAnchor);
                }

                function onUp() {
                    try {
                        window.removeEventListener('mousemove', onMove);
                        window.removeEventListener('mouseup', onUp);
                    } catch (eOff) {
                        // ignore
                    }
                    try {
                        if (document.body) document.body.style.userSelect = prevUserSelect;
                        document.documentElement.style.cursor = prevCursor;
                    } catch (eRestore) {
                        // ignore
                    }

                    if (activeDragAnchor) scheduleReadingAnchorRestore(activeDragAnchor);
                    activeDragAnchor = null;

                    // Resizing can cause reflow (line wrap) so rebuild index once after drag.
                    markTocDirty();
                    scheduleActiveUpdate();
                    scheduleDelayedBaselineAnchorCapture(0);

                    // Persist width after the user finishes dragging.
                    safeSet(KEY_TOC_WIDTH, getSidebarWidthPx());
                }

                try {
                    e.preventDefault();
                    window.addEventListener('mousemove', onMove);
                    window.addEventListener('mouseup', onUp);
                } catch (eBind) {
                    // ignore
                }
            });
        }

        function ensureSidebarToc() {
            if (!sidebarBody) return;
            if (sidebarBody.getAttribute('data-et-built') === '1') return;
            sidebarBody.setAttribute('data-et-built', '1');

            sidebarHrefMap = Object.create(null);
            activeSidebarLink = null;

            var top = document.getElementById(TOP_ID);
            var sourceList = top ? top.querySelector('ul') : null;
            if (!sourceList) {
                var first = document.querySelector('a[id^="toc_"]');
                if (first && first.closest) sourceList = first.closest('ul');
            }
            if (!sourceList) return;

            var clone = sourceList.cloneNode(true);

            // Remove IDs from the cloned TOC to keep IDs unique, and add hover tooltips.
            var links = clone.querySelectorAll('a');
            for (var i = 0; i < links.length; i++) {
                var a = links[i];
                var id = a.getAttribute('id');
                if (id && id.indexOf('toc_') === 0) {
                    a.removeAttribute('id');
                }
                var txt = normalizeText(a.textContent);
                if (txt) a.setAttribute('title', txt);

                var href = a.getAttribute('href') || '';
                if (href) sidebarHrefMap[href] = a;
            }

            // Strip inline styles on the cloned tree to avoid odd layout in the sidebar.
            try {
                clone.removeAttribute('style');
                var uls = clone.querySelectorAll('ul');
                for (var j = 0; j < uls.length; j++) {
                    uls[j].removeAttribute('style');
                }
            } catch (e2) {
                // ignore
            }

            sidebarBody.appendChild(clone);
        }

        function clearActive() {
            if (activeSidebarLink) {
                try {
                    activeSidebarLink.classList.remove('et-toc-active');
                } catch (eR) {
                    // ignore
                }
            }
            activeSidebarLink = null;
        }

        function findSidebarLinkByHref(href) {
            if (!sidebarBody || !href) return null;
            if (sidebarHrefMap && sidebarHrefMap[href]) return sidebarHrefMap[href];
            var links = sidebarBody.querySelectorAll('a[href]');
            for (var i = 0; i < links.length; i++) {
                if (links[i].getAttribute('href') === href) return links[i];
            }
            return null;
        }

        function isCollapsed() {
            try {
                return sidebar.getAttribute('data-et-toc-state') === 'collapsed';
            } catch (eC) {
                return false;
            }
        }

        function focusByHref(href) {
            ensureSidebarToc();
            if (!href) return;

            var link = findSidebarLinkByHref(href);
            if (!link) return;

            if (activeSidebarLink && activeSidebarLink !== link) {
                try { activeSidebarLink.classList.remove('et-toc-active'); } catch (eA0) { /* ignore */ }
            }

            try { link.classList.add('et-toc-active'); } catch (eA1) { /* ignore */ }
            activeSidebarLink = link;

            if (isCollapsed()) return;
            try {
                link.scrollIntoView({ block: 'nearest' });
            } catch (e) {
                // ignore
            }
        }

        function focusByTocId(tocId) {
            if (!tocId) return;

            // Always track the latest active TOC id even when collapsed.
            activeTocId = tocId;

            var href = null;
            try {
                if (tocIdToHref && tocIdToHref[tocId]) href = tocIdToHref[tocId];
            } catch (eH0) {
                href = null;
            }

            if (!href) {
                var topLink = document.getElementById(tocId);
                href = topLink ? (topLink.getAttribute('href') || null) : null;
            }

            if (!href) return;
            if (isCollapsed()) return;
            focusByHref(href);
        }

        function updateActiveFromScroll() {
            if (isCollapsed()) return;
            ensureTocIndex();
            if (!tocIndex || !tocIndex.length) return;

            // Pick the last TOC target whose top is above the viewport top (with a small offset).
            var y = (window.scrollY || 0) + 24;
            var lo = 0;
            var hi = tocIndex.length - 1;
            var idx = 0;
            while (lo <= hi) {
                var mid = (lo + hi) >> 1;
                if (tocIndex[mid].top <= y) {
                    idx = mid;
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }

            var tocId = tocIndex[idx].tocId;
            if (!tocId || tocId === activeTocId) return;
            activeTocId = tocId;
            focusByHref(tocIndex[idx].href);
        }

        // Button wiring
        if (collapseBtn) {
            collapseBtn.addEventListener('click', function () {
                var collapsed = sidebar.getAttribute('data-et-toc-state') === 'collapsed';
                var overlayMode = isOverlayMode();
                var anchor = null;

                if (overlayMode) {
                    if (collapsed) {
                        anchor = captureReadingAnchor() || lastReadingAnchor;
                        startOverlaySession(buildScrollFallbackAnchor(0));
                    } else {
                        anchor = (!overlaySessionDirty && overlaySessionAnchor)
                            ? overlaySessionAnchor
                            : (captureVisibleHashTargetAnchor() || captureReadingAnchor() || lastReadingAnchor);
                    }
                }

                runWithPreservedReadingPosition(function () {
                    setCollapsed(!collapsed);
                    safeSet(KEY_TOC_STATE, sidebar.getAttribute('data-et-toc-state') || (!collapsed ? 'collapsed' : 'expanded'));
                }, anchor);

                if (overlayMode && !collapsed) {
                    clearOverlaySession();
                }
            });
        }
        if (sideBtn) {
            sideBtn.addEventListener('click', function () {
                var side = sidebar.getAttribute('data-et-toc-side') || 'left';
                if (isOverlayMode() && !isCollapsed()) markOverlaySessionDirty();
                runWithPreservedReadingPosition(function () {
                    setSide(side === 'right' ? 'left' : 'right');
                    safeSet(KEY_TOC_SIDE, sidebar.getAttribute('data-et-toc-side') || (side === 'right' ? 'left' : 'right'));
                });
            });
        }
        if (highlightBtn) {
            highlightBtn.addEventListener('click', function () {
                var enabled = highlightBtn.getAttribute('data-et-highlight-enabled') !== 'false';
                enabled = !enabled;
                highlightBtn.setAttribute('data-et-highlight-enabled', enabled ? 'true' : 'false');
                setHighlightButtonLabel();
                // Set global flag for highlight functionality
                window.etHighlightEnabled = enabled;
                safeSet(KEY_PAIR_HIGHLIGHT, enabled ? 'true' : 'false');
            });
        }

        // Note: do NOT intercept clicks of `#toc_...` anchors.
        // `↩` uses `href="#toc_xxx"` to jump back to the top TOC. We keep that default behavior.

        function onHash() {
            var h = (location.hash || '');
            if (h.indexOf('#toc_') === 0) {
                // Sync sidebar highlight without changing layout (avoid reflow that may interfere with anchor jumps).
                focusByTocId(h.slice(1));
            }
            if (!isRestoringViewport && isOverlayMode() && !isCollapsed()) markOverlaySessionDirty();
            scheduleDelayedBaselineAnchorCapture(60);
        }
        window.addEventListener('hashchange', onHash);

        function addWindowListener(name, handler) {
            try {
                window.addEventListener(name, handler, { passive: true });
            } catch (e3) {
                window.addEventListener(name, handler);
            }
        }

        // Keep the active TOC item in sync with reading position.
        addWindowListener('scroll', function () {
            if (!isRestoringViewport && isOverlayMode() && !isCollapsed()) markOverlaySessionDirty();
            scheduleActiveUpdate();
            scheduleBaselineAnchorCapture();
        });
        addWindowListener('resize', function () {
            if (!isRestoringViewport && isOverlayMode() && !isCollapsed()) markOverlaySessionDirty();
            basePaddingDirty = true;
            markTocDirty();
            if (!resizeSessionAnchor) {
                resizeSessionAnchor = lastReadingAnchor || captureReadingAnchor();
            }
            applyBodyOffset();
            if (resizeSessionAnchor) scheduleReadingAnchorRestore(resizeSessionAnchor);
            scheduleActiveUpdate();
            resizeSettleTimer = clearTimer(resizeSettleTimer);
            try {
                resizeSettleTimer = window.setTimeout(function () {
                    resizeSessionAnchor = null;
                    resizeSettleTimer = 0;
                    scheduleDelayedBaselineAnchorCapture(0);
                }, 140);
            } catch (eRZ) {
                resizeSessionAnchor = null;
                scheduleBaselineAnchorCapture();
            }
        });
        addWindowListener('load', function () {
            basePaddingDirty = true;
            markTocDirty();
            applyBodyOffset();
            scheduleActiveUpdate();
            scheduleDelayedBaselineAnchorCapture(0);
        });

        // Init
        if (savedWidth != null && isFinite(savedWidth)) {
            var maxW0 = Math.floor((window.innerWidth || 0) * 0.75);
            if (!maxW0 || maxW0 < MIN_WIDTH) maxW0 = MIN_WIDTH;
            var w0 = clamp(savedWidth, MIN_WIDTH, maxW0);
            setSidebarWidthPx(w0);
        }

        setSide(savedSide || sidebar.getAttribute('data-et-toc-side') || 'left');

        var initialState = savedState || sidebar.getAttribute('data-et-toc-state') || 'expanded';
        var initialCollapsed = (initialState === 'collapsed');
        if (!savedState && !initialCollapsed && isOverlayMode()) initialCollapsed = true;
        setCollapsed(initialCollapsed);

        if (highlightBtn) {
            var initialEnabled = (savedHighlight !== null) ? savedHighlight : (window.etHighlightEnabled !== false);
            window.etHighlightEnabled = initialEnabled;
            highlightBtn.setAttribute('data-et-highlight-enabled', initialEnabled ? 'true' : 'false');
            setHighlightButtonLabel();
        }

        if (!isCollapsed()) ensureSidebarToc();
        onHash();
        // Initial highlight.
        scheduleActiveUpdate();
        scheduleDelayedBaselineAnchorCapture(0);
    });
})();
