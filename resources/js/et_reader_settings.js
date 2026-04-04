/* et-reader-settings */
(function () {
    'use strict';

    var PANEL_ID = 'et-reader-settings';

    var KEY_THEME = 'et-reader-theme';
    var KEY_FONT = 'et-reader-font-size';
    var KEY_LINE = 'et-reader-line-height';
    var KEY_STATE = 'et-reader-settings-state';
    var OVERRIDE_ATTR = 'data-et-reader-override';

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    function clamp(n, lo, hi) {
        if (n < lo) return lo;
        if (n > hi) return hi;
        return n;
    }

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

    function setOverrideEnabled(enabled) {
        try {
            if (!document.documentElement) return;
            if (enabled) document.documentElement.setAttribute(OVERRIDE_ATTR, '1');
            else document.documentElement.removeAttribute(OVERRIDE_ATTR);
        } catch (e) {
            // ignore
        }
    }

    function findSampleTextElement() {
        // Prefer real book content.
        try {
            var p = document.querySelector('.et-epub-body p');
            if (p) return p;
        } catch (e0) {
            // ignore
        }
        try {
            var anyP = document.querySelector('p');
            if (anyP) return anyP;
        } catch (e1) {
            // ignore
        }
        return document.body || document.documentElement;
    }

    function parsePx(s) {
        if (!s) return null;
        var n = parseFloat(String(s).replace('px', ''));
        return isFinite(n) ? n : null;
    }

    function getComputedFontSizePx() {
        var el = findSampleTextElement();
        if (!el) return 16;
        try {
            var cs = window.getComputedStyle(el);
            var px = parsePx(cs.fontSize);
            if (px != null && px > 0) return px;
        } catch (e) {
            // ignore
        }
        return 16;
    }

    function getComputedLineHeightRatio() {
        var el = findSampleTextElement();
        if (!el) return 1.4;
        try {
            var cs = window.getComputedStyle(el);
            var lh = cs.lineHeight;
            // Can be "normal".
            var lhPx = parsePx(lh);
            var fsPx = parsePx(cs.fontSize) || getComputedFontSizePx();
            if (lhPx != null && fsPx > 0) {
                var r = lhPx / fsPx;
                if (isFinite(r) && r > 0.5 && r < 4) return r;
            }
        } catch (e) {
            // ignore
        }
        // Fallback: a readable default.
        return 1.4;
    }

    function setTheme(theme) {
        var t = theme || 'default';
        try {
            if (t === 'default') {
                document.documentElement.removeAttribute('data-et-theme');
            } else {
                document.documentElement.setAttribute('data-et-theme', t);
            }
        } catch (e) {
            // ignore
        }
        safeSet(KEY_THEME, t);
    }

    function setFontSize(px) {
        var v = clamp(px, 14, 40);
        setOverrideEnabled(true);
        try {
            document.documentElement.style.setProperty('--et-reader-font-size', v + 'px');
        } catch (e) {
            // ignore
        }
        safeSet(KEY_FONT, v);
        return v;
    }

    function setLineHeight(lh) {
        var v = clamp(lh, 1.1, 2.4);
        // Keep one decimal.
        v = Math.round(v * 10) / 10;
        setOverrideEnabled(true);
        try {
            document.documentElement.style.setProperty('--et-reader-line-height', String(v));
        } catch (e) {
            // ignore
        }
        safeSet(KEY_LINE, v);
        return v;
    }

    function readNumber(key) {
        var raw = safeGet(key);
        if (!raw) return null;
        var n = Number(raw);
        return isFinite(n) ? n : null;
    }

    function updateActiveThemeUI(panel, theme) {
        if (!panel) return;
        var items = panel.querySelectorAll('.et-bg-item[data-et-theme]');
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var t = it.getAttribute('data-et-theme') || 'default';
            if (t === theme) it.classList.add('et-active');
            else it.classList.remove('et-active');
        }
    }

    function setPanelState(panel, state) {
        if (!panel) return;
        panel.setAttribute('data-et-state', state === 'collapsed' ? 'collapsed' : 'expanded');
        safeSet(KEY_STATE, panel.getAttribute('data-et-state'));
    }

    onReady(function () {
        var panel = document.getElementById(PANEL_ID);
        if (!panel) return;

        // Restore settings
        var theme = safeGet(KEY_THEME) || 'default';
        var font = readNumber(KEY_FONT);
        var line = readNumber(KEY_LINE);
        var state = safeGet(KEY_STATE);

        setTheme(theme);
        updateActiveThemeUI(panel, theme);

        var sizeValue = panel.querySelector('.et-font-size-value');
        var lineValue = panel.querySelector('.et-line-height-value');

        // If the user has saved preferences, apply them and enable overrides.
        // Otherwise, keep the book's original typography and only display its current values.
        if (font != null || line != null) {
            var appliedFont = setFontSize(font != null ? font : getComputedFontSizePx());
            var appliedLine = setLineHeight(line != null ? line : getComputedLineHeightRatio());
            if (sizeValue) sizeValue.textContent = String(appliedFont);
            if (lineValue) lineValue.textContent = String(appliedLine);
        } else {
            setOverrideEnabled(false);
            var baseFont = Math.round(getComputedFontSizePx());
            var baseLine = getComputedLineHeightRatio();
            baseLine = Math.round(baseLine * 10) / 10;
            if (sizeValue) sizeValue.textContent = String(baseFont);
            if (lineValue) lineValue.textContent = String(baseLine);
        }

        if (state) setPanelState(panel, state);

        // Theme buttons
        var bg = panel.querySelector('.et-bg');
        if (bg) {
            bg.addEventListener('click', function (e) {
                var target = e.target;
                if (!target) return;
                var btn = target.closest ? target.closest('.et-bg-item') : null;
                if (!btn) return;
                var t = btn.getAttribute('data-et-theme') || 'default';
                setTheme(t);
                updateActiveThemeUI(panel, t);
            });
        }

        // Font size controls
        var fontCut = panel.querySelector('.et-font-cut');
        var fontAdd = panel.querySelector('.et-font-add');
        if (fontCut) {
            fontCut.addEventListener('click', function () {
                var current = readNumber(KEY_FONT);
                if (current == null) current = Math.round(getComputedFontSizePx());
                var next = setFontSize(current - 2);
                if (sizeValue) sizeValue.textContent = String(next);
            });
        }
        if (fontAdd) {
            fontAdd.addEventListener('click', function () {
                var current = readNumber(KEY_FONT);
                if (current == null) current = Math.round(getComputedFontSizePx());
                var next = setFontSize(current + 2);
                if (sizeValue) sizeValue.textContent = String(next);
            });
        }

        // Line height controls
        var lineCut = panel.querySelector('.et-line-cut');
        var lineAdd = panel.querySelector('.et-line-add');
        if (lineCut) {
            lineCut.addEventListener('click', function () {
                var current = readNumber(KEY_LINE);
                if (current == null) current = getComputedLineHeightRatio();
                var next = setLineHeight(current - 0.1);
                if (lineValue) lineValue.textContent = String(next);
            });
        }
        if (lineAdd) {
            lineAdd.addEventListener('click', function () {
                var current = readNumber(KEY_LINE);
                if (current == null) current = getComputedLineHeightRatio();
                var next = setLineHeight(current + 0.1);
                if (lineValue) lineValue.textContent = String(next);
            });
        }

        // Collapse/expand
        var header = panel.querySelector('.et-setbox-header');
        if (header) {
            header.addEventListener('click', function (e) {
                var collapsed = panel.getAttribute('data-et-state') === 'collapsed';
                setPanelState(panel, collapsed ? 'expanded' : 'collapsed');
            });
        }
    });
})();
