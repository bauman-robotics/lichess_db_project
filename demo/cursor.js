(function () {
    if (window.__demoCursorInjected) return;
    window.__demoCursorInjected = true;

    const css = document.createElement('style');
    css.textContent = `
        html, body, * { cursor: none !important; }
        #demo-cursor {
            position: fixed; left: 0; top: 0; z-index: 2147483647;
            width: 26px; height: 26px; pointer-events: none;
            transform: translate(-4px, -2px);
            transition: transform 70ms linear;
            filter: drop-shadow(0 2px 3px rgba(0,0,0,.65));
        }
        .demo-click-ripple {
            position: fixed; z-index: 2147483646; width: 14px; height: 14px;
            margin-left: -7px; margin-top: -7px; border-radius: 50%;
            border: 2px solid #ffd700; pointer-events: none;
            animation: demo-ripple .45s ease-out forwards;
        }
        @keyframes demo-ripple {
            from { opacity: 1; transform: scale(.5); }
            to   { opacity: 0; transform: scale(3.2); }
        }
        .demo-highlight {
            outline: 3px solid #ffd700 !important;
            outline-offset: 3px !important;
            box-shadow: 0 0 0 6px rgba(255, 215, 0, .18) !important;
            transition: outline-color .2s ease, box-shadow .2s ease;
        }
        #demo-tooltip {
            position: fixed; z-index: 2147483647; display: none;
            max-width: 420px; padding: 8px 11px; border-radius: 7px;
            background: #fff; color: #111; font: 500 14px/1.35 system-ui, sans-serif;
            box-shadow: 0 5px 18px rgba(0,0,0,.35); pointer-events: none;
        }
        #demo-notepad {
            position: fixed; z-index: 2147483646; right: 32px; bottom: 92px;
            width: 560px; max-width: 60vw; max-height: 420px; overflow: auto;
            padding: 16px 18px; border: 1px solid #ffd700; border-radius: 9px;
            background: rgba(15, 15, 20, .96); color: #f4f4f4;
            font: 15px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            white-space: pre-wrap; box-shadow: 0 10px 35px rgba(0,0,0,.5);
        }
        #demo-notepad .demo-notepad-title {
            display: block; margin-bottom: 8px; color: #ffd700;
            font: 700 13px/1.2 system-ui, sans-serif; letter-spacing: .04em;
            text-transform: uppercase;
        }
        @media (max-width: 500px) {
            #demo-caption {
                bottom: 108px; max-width: 88vw; padding: 8px 12px;
                font-size: 16px; line-height: 1.35;
            }
            #demo-tooltip { max-width: 82vw; font-size: 12px; }
            #demo-notepad { right: 10px; bottom: 120px; width: calc(100vw - 20px); max-width: none; }
        }
        #demo-caption {
            position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%);
            z-index: 2147483645; max-width: 80vw; padding: 10px 18px;
            border-radius: 9px; background: rgba(12, 12, 16, .86);
            border: 1px solid rgba(255,255,255,.18); color: #fff;
            font: 600 20px/1.3 system-ui, -apple-system, sans-serif;
            text-align: center; pointer-events: none;
            box-shadow: 0 6px 24px rgba(0,0,0,.35);
        }
    `;
    let cssMounted = false;

    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = `
        <svg width="26" height="26" viewBox="0 0 26 26" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 2 L22 13 L13.8 15.2 L10.9 23.5 L3 2 Z"
                  fill="#ffffff" stroke="#111111" stroke-width="1.6" stroke-linejoin="round"/>
        </svg>`;

    let tooltip = null;
    let notepad = null;

    function ensureTooltip() {
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'demo-tooltip';
            document.body.appendChild(tooltip);
        }
        return tooltip;
    }

    function placeTooltip(event) {
        if (!tooltip) return;
        const x = Math.min(event.clientX + 18, window.innerWidth - tooltip.offsetWidth - 12);
        const y = Math.min(event.clientY + 18, window.innerHeight - tooltip.offsetHeight - 12);
        tooltip.style.left = Math.max(8, x) + 'px';
        tooltip.style.top = Math.max(8, y) + 'px';
    }

    function place(x, y) {
        cursor.style.transform = `translate(${x - 4}px, ${y - 2}px)`;
    }

    function mount() {
        if (!document.documentElement || !document.body) return;
        if (!cssMounted) {
            css.textContent += `
        @media (max-width: 500px) {
            #demo-caption {
                bottom: 108px !important; max-width: 88vw !important;
                padding: 8px 12px !important; font-size: 16px !important;
                line-height: 1.35 !important;
            }
        }
    `;
    document.documentElement.appendChild(css);
            cssMounted = true;
        }
        if (!cursor.parentNode) document.body.appendChild(cursor);
    }

    document.addEventListener('mousemove', function (event) {
        mount();
        place(event.clientX, event.clientY);
    }, true);

    document.addEventListener('mouseover', function (event) {
        const target = event.target.closest && event.target.closest(
            '.analysis-eval-dot, .btn-analysis'
        );
        if (!target) return;
        const text = target.getAttribute('title') || '';
        if (!text) return;
        const el = ensureTooltip();
        el.textContent = text;
        el.style.display = 'block';
        placeTooltip(event);
    }, true);

    document.addEventListener('mousemove', function (event) {
        if (tooltip && tooltip.style.display === 'block') placeTooltip(event);
    }, true);

    document.addEventListener('mouseout', function (event) {
        const target = event.target.closest && event.target.closest(
            '.analysis-eval-dot, .btn-analysis'
        );
        if (target && tooltip) tooltip.style.display = 'none';
    }, true);

    document.addEventListener('mousedown', function (event) {
        mount();
        place(event.clientX, event.clientY);
        const ripple = document.createElement('div');
        ripple.className = 'demo-click-ripple';
        ripple.style.left = event.clientX + 'px';
        ripple.style.top = event.clientY + 'px';
        document.body.appendChild(ripple);
        setTimeout(function () { ripple.remove(); }, 500);
    }, true);

    window.__demoNotepad = function (text, title) {
        if (!document.body) return;
        if (!notepad) {
            notepad = document.createElement('div');
            notepad.id = 'demo-notepad';
            document.body.appendChild(notepad);
        }
        notepad.textContent = '';
        const heading = document.createElement('span');
        heading.className = 'demo-notepad-title';
        heading.textContent = title || 'Текстовый блокнот';
        notepad.appendChild(heading);
        notepad.appendChild(document.createTextNode(text || ''));
        notepad.style.display = 'block';
    };

    window.__demoHideNotepad = function () {
        if (notepad) notepad.style.display = 'none';
    };

    window.__demoSetCaption = function (text) {
        let el = document.getElementById('demo-caption');
        if (!text) {
            if (el) el.remove();
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.id = 'demo-caption';
            document.body.appendChild(el);
        }
        el.textContent = text;
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
    place(window.innerWidth / 2, window.innerHeight / 2);
})();
