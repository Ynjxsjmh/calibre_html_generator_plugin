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

        // Overlay mode should happen on *mobile devices* (touch-first), not just when a desktop window is narrow.
        // Otherwise desktop users can't resize and will see sidebar/content overlap.
        var overlayMql = null;
        try {
            if (window.matchMedia) overlayMql = window.matchMedia('(hover: none) and (pointer: coarse)');
        } catch (eMql) {
            overlayMql = null;
        }

        var uaIsMobile = false;
        try {
            var ua = (navigator && navigator.userAgent) ? String(navigator.userAgent) : '';
            uaIsMobile = /\b(Mobi|Android|iPhone|iPad|iPod)\b/i.test(ua);
        } catch (eUA) {
            uaIsMobile = false;
        }

        function isOverlayMode() {
            if (uaIsMobile) return true;
            try {
                if (overlayMql) return !!overlayMql.matches;
            } catch (eOM) {
                // ignore
            }
            return false;
        }

        var tocIndex = null; // [{ tocId, href, top }]
        var tocIdToHref = null; // { tocId: href }
        var tocDirty = true;
        var activeTocId = null;
        var activeSidebarLink = null;
        var sidebarHrefMap = null; // { href: <a> }
        var rafPending = false;

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
                setCollapsed(!collapsed);
            });
        }
        if (sideBtn) {
            sideBtn.addEventListener('click', function () {
                var side = sidebar.getAttribute('data-et-toc-side') || 'left';
                setSide(side === 'right' ? 'left' : 'right');
            });
        }
        if (highlightBtn) {
            highlightBtn.addEventListener('click', function () {
                var enabled = highlightBtn.getAttribute('data-et-highlight-enabled') !== 'false';
                enabled = !enabled;
                highlightBtn.setAttribute('data-et-highlight-enabled', enabled ? 'true' : 'false');
                setHighlightButtonLabel();
                // Set global flag for highlight functionality
                if (window.etHighlightEnabled !== undefined) {
                    window.etHighlightEnabled = enabled;
                }
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
        addWindowListener('resize', function () { basePaddingDirty = true; markTocDirty(); applyBodyOffset(); scheduleActiveUpdate(); });
        addWindowListener('load', function () { basePaddingDirty = true; markTocDirty(); applyBodyOffset(); scheduleActiveUpdate(); });

        // Init
        setSide(sidebar.getAttribute('data-et-toc-side') || 'left');
        var initialCollapsed = (sidebar.getAttribute('data-et-toc-state') || 'expanded') === 'collapsed';
        if (isOverlayMode()) initialCollapsed = true;
        setCollapsed(initialCollapsed);
        if (highlightBtn) {
            var initialEnabled = window.etHighlightEnabled !== false;
            highlightBtn.setAttribute('data-et-highlight-enabled', initialEnabled ? 'true' : 'false');
            setHighlightButtonLabel();
        }
        if (!isCollapsed()) ensureSidebarToc();
        onHash();
        // Initial highlight.
        scheduleActiveUpdate();
    });
})();
