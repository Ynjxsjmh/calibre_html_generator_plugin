/* et-toc-sidebar */
(function () {
    'use strict';

    var SIDEBAR_ID = 'et-toc-sidebar';
    var SIDEBAR_BODY_ID = 'et-toc-sidebar-body';
    var TOP_ID = 'et-toc-top';

    var DEFAULT_WIDTH = 320;
    var COLLAPSED_WIDTH = 34;
    var MIN_WIDTH = 180;

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

        function clamp(n, lo, hi) {
            if (n < lo) return lo;
            if (n > hi) return hi;
            return n;
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
        }

        function clearActive() {
            if (!sidebarBody) return;
            var prev = sidebarBody.querySelectorAll('a.et-toc-active');
            for (var i = 0; i < prev.length; i++) {
                prev[i].classList.remove('et-toc-active');
            }
        }

        function findSidebarLinkByHref(href) {
            if (!sidebarBody || !href) return null;
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

            clearActive();
            link.classList.add('et-toc-active');
            try {
                link.scrollIntoView({ block: 'nearest' });
            } catch (e) {
                // ignore
            }
        }

        function updateActiveFromScroll() {
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
            });
        }
        if (sideBtn) {
            sideBtn.addEventListener('click', function () {
                var side = sidebar.getAttribute('data-et-toc-side') || 'left';
                setSide(side === 'right' ? 'left' : 'right');
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
        addWindowListener('resize', function () { markTocDirty(); scheduleActiveUpdate(); });
        addWindowListener('load', function () { markTocDirty(); scheduleActiveUpdate(); });

        // Init
        setSide(sidebar.getAttribute('data-et-toc-side') || 'left');
        setCollapsed((sidebar.getAttribute('data-et-toc-state') || 'expanded') === 'collapsed');
        ensureSidebarToc();
        onHash();
        // Initial highlight.
        scheduleActiveUpdate();
    });
})();
