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

    function place(x, y) {
        cursor.style.transform = `translate(${x - 4}px, ${y - 2}px)`;
    }

    function mount() {
        if (!document.documentElement || !document.body) return;
        if (!cssMounted) {
            document.documentElement.appendChild(css);
            cssMounted = true;
        }
        if (!cursor.parentNode) document.body.appendChild(cursor);
    }

    document.addEventListener('mousemove', function (event) {
        mount();
        place(event.clientX, event.clientY);
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
