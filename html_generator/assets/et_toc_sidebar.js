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

        // Capture base margins so we can offset without destroying the ebook CSS spacing.
        var baseML = '0px';
        var baseMR = '0px';
        try {
            if (document.body) {
                var cs = window.getComputedStyle(document.body);
                baseML = cs.marginLeft || '0px';
                baseMR = cs.marginRight || '0px';
            }
        } catch (e) {
            // ignore
        }

        var tocIndex = null; // [{ tocId, top }]
        var tocDirty = true;
        var activeTocId = null;
        var rafPending = false;

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

        // Performance: index sidebar links by href to avoid scanning the DOM on every scroll.
        var sidebarHrefIndex = null; // { '#chapter001': <a>, ... }
        var activeSidebarLink = null;

        function clamp(n, lo, hi) {
            if (n < lo) return lo;
            if (n > hi) return hi;
            return n;
        }

        function isTouchLikeDevice() {
            try {
                if (window.matchMedia) {
                    if (window.matchMedia('(pointer: coarse)').matches) return true;
                    if (window.matchMedia('(hover: none)').matches) return true;
                }
            } catch (e) {
                // ignore
            }
            try {
                if (navigator && typeof navigator.maxTouchPoints === 'number') {
                    return navigator.maxTouchPoints > 0;
                }
            } catch (e2) {
                // ignore
            }
            try {
                return ('ontouchstart' in window);
            } catch (e3) {
                return false;
            }
        }

        // Mobile overlay mode should only apply to phone-like (narrow) *touch* screens.
        // Do NOT apply it to narrow desktop windows, otherwise the sidebar will overlap content.
        function isMobileOverlayMode() {
            var w = 0;
            try {
                w = (window.innerWidth || 0);
            } catch (e) {
                w = 0;
            }
            return w <= 768 && isTouchLikeDevice();
        }

        function raf(cb) {
            var fn = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };
            return fn(cb);
        }

        function markTocDirty() {
            tocDirty = true;
        }

        function rebuildTocIndex() {
            tocDirty = false;
            tocIndex = [];

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
                tocIndex.push({ tocId: tocId, top: topPx });
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

            // Mobile/narrow screens: keep content full-width.
            // The sidebar stays `position: fixed` and overlays when expanded.
            if (isMobileOverlayMode()) {
                var collapsed = sidebar.getAttribute('data-et-toc-state') === 'collapsed';
                if (collapsed) {
                    var sideN = sidebar.getAttribute('data-et-toc-side') || 'left';
                    var wN = getSidebarWidthPx();
                    // Add 1px safety to avoid the sidebar border sitting on top of the first glyph.
                    var padN = wN + 1;
                    if (sideN === 'right') {
                        document.body.style.marginRight = 'calc(' + baseMR + ' + ' + padN + 'px)';
                        document.body.style.marginLeft = baseML;
                    } else {
                        document.body.style.marginLeft = 'calc(' + baseML + ' + ' + padN + 'px)';
                        document.body.style.marginRight = baseMR;
                    }
                    return;
                }

                document.body.style.marginLeft = baseML;
                document.body.style.marginRight = baseMR;
                return;
            }

            var side = sidebar.getAttribute('data-et-toc-side') || 'left';
            var w = getSidebarWidthPx();
            if (side === 'right') {
                document.body.style.marginRight = 'calc(' + baseMR + ' + ' + w + 'px)';
                document.body.style.marginLeft = baseML;
            } else {
                document.body.style.marginLeft = 'calc(' + baseML + ' + ' + w + 'px)';
                document.body.style.marginRight = baseMR;
            }
        }

        function setCollapsed(collapsed) {
            sidebar.setAttribute('data-et-toc-state', collapsed ? 'collapsed' : 'expanded');
            if (collapseBtn) collapseBtn.textContent = collapsed ? '目录' : '收起';
            applyBodyOffset();
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

                    // Resizing can cause reflow (line wrap) so rebuild index once after drag.
                    markTocDirty();
                    scheduleActiveUpdate();

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

            // Build href index for fast lookups while scrolling.
            try {
                sidebarHrefIndex = Object.create(null);
                var idxLinks = clone.querySelectorAll('a[href]');
                for (var k = 0; k < idxLinks.length; k++) {
                    var href = idxLinks[k].getAttribute('href');
                    if (href && !sidebarHrefIndex[href]) sidebarHrefIndex[href] = idxLinks[k];
                }
            } catch (eIdx) {
                sidebarHrefIndex = null;
            }
        }

        function clearActive() {
            if (activeSidebarLink) {
                try {
                    activeSidebarLink.classList.remove('et-toc-active');
                } catch (e0) {
                    // ignore
                }
                activeSidebarLink = null;
                return;
            }

            if (!sidebarBody) return;
            var prev = sidebarBody.querySelectorAll('a.et-toc-active');
            for (var i = 0; i < prev.length; i++) {
                prev[i].classList.remove('et-toc-active');
            }
        }

        function findSidebarLinkByHref(href) {
            if (!sidebarBody || !href) return null;
            if (sidebarHrefIndex && sidebarHrefIndex[href]) return sidebarHrefIndex[href];
            var links = sidebarBody.querySelectorAll('a[href]');
            for (var i = 0; i < links.length; i++) {
                if (links[i].getAttribute('href') === href) return links[i];
            }
            return null;
        }

        function focusByTocId(tocId) {
            ensureSidebarToc();
            if (!tocId) return;

            var topLink = document.getElementById(tocId);
            var href = topLink ? topLink.getAttribute('href') : null;
            if (!href) return;

            var link = findSidebarLinkByHref(href);
            if (!link) return;

            if (activeSidebarLink && activeSidebarLink !== link) {
                clearActive();
            }
            activeSidebarLink = link;
            try {
                link.classList.add('et-toc-active');
            } catch (eAdd) {
                // ignore
            }
            try {
                link.scrollIntoView({ block: 'nearest' });
            } catch (e) {
                // ignore
            }
        }

        function updateActiveFromScroll() {
            // Avoid doing work while the sidebar is collapsed (typical on mobile).
            // We'll resync when the user expands the sidebar.
            try {
                if (sidebar.getAttribute('data-et-toc-state') === 'collapsed') return;
            } catch (eCollapsed) {
                // ignore
            }

            ensureSidebarToc();
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
            focusByTocId(tocId);
        }

        // Button wiring
        if (collapseBtn) {
            collapseBtn.addEventListener('click', function () {
                var collapsed = sidebar.getAttribute('data-et-toc-state') === 'collapsed';
                setCollapsed(!collapsed);
                safeSet(KEY_TOC_STATE, sidebar.getAttribute('data-et-toc-state') || (!collapsed ? 'collapsed' : 'expanded'));
            });
        }
        if (sideBtn) {
            sideBtn.addEventListener('click', function () {
                var side = sidebar.getAttribute('data-et-toc-side') || 'left';
                setSide(side === 'right' ? 'left' : 'right');
                safeSet(KEY_TOC_SIDE, sidebar.getAttribute('data-et-toc-side') || (side === 'right' ? 'left' : 'right'));
            });
        }
        if (highlightBtn) {
            highlightBtn.addEventListener('click', function () {
                var enabled = highlightBtn.getAttribute('data-et-highlight-enabled') !== 'false';
                enabled = !enabled;
                highlightBtn.setAttribute('data-et-highlight-enabled', enabled ? 'true' : 'false');
                highlightBtn.textContent = enabled ? '禁用' : '启用';
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
        addWindowListener('scroll', scheduleActiveUpdate);
        addWindowListener('resize', function () { applyBodyOffset(); markTocDirty(); scheduleActiveUpdate(); });
        addWindowListener('load', function () { markTocDirty(); scheduleActiveUpdate(); });

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
        // Default to collapsed on narrow/mobile screens to avoid a squeezed reading area.
        // Only apply this heuristic when there is no persisted user preference.
        if (!savedState && !initialCollapsed && isMobileOverlayMode()) {
            initialCollapsed = true;
        }
        setCollapsed(initialCollapsed);
        if (highlightBtn) {
            var initialEnabled = (savedHighlight !== null) ? savedHighlight : (window.etHighlightEnabled !== false);
            window.etHighlightEnabled = initialEnabled;
            highlightBtn.setAttribute('data-et-highlight-enabled', initialEnabled ? 'true' : 'false');
            highlightBtn.textContent = initialEnabled ? '禁用' : '启用';
        }
        ensureSidebarToc();
        onHash();
        // Initial highlight.
        scheduleActiveUpdate();
    });
})();
