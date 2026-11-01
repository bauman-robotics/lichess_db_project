// Связывание SAN-ходов в тексте анализа с позициями партии.
// Используется game_viewer.js и analysis.js.
(function () {
    'use strict';

    const SAN_RE = /\b(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)(?![A-Za-z0-9])/g;
    const SAN_CLEAN_RE = /[!?]+$/;

    function cleanSan(san) {
        return String(san || '').replace(SAN_CLEAN_RE, '');
    }

    function buildIndex(positions) {
        const byKey = new Map();
        const bySan = new Map();

        (positions || []).forEach(function (pos, index) {
            if (!pos || !pos.san) return;
            const san = cleanSan(pos.san);
            if (!san) return;
            const key = pos.move_number + '|' + pos.color + '|' + san;
            byKey.set(key, index);
            const variants = [san];
            const base = san.replace(/[+#]$/, '');
            if (base && base !== san) variants.push(base);
            variants.forEach(function (key) {
                if (!bySan.has(key)) bySan.set(key, []);
                if (bySan.get(key).indexOf(index) === -1) {
                    bySan.get(key).push(index);
                }
            });
        });

        return { byKey: byKey, bySan: bySan };
    }

    function resolve(index, san, moveNumber, color) {
        if (!index) return { ply: null, reason: 'none' };
        const clean = cleanSan(san);
        if (moveNumber && color) {
            const ply = index.byKey.get(moveNumber + '|' + color + '|' + clean);
            if (ply !== undefined) return { ply: ply, reason: 'exact' };
        }
        let matches = index.bySan.get(clean) || [];
        if (!matches.length) {
            matches = index.bySan.get(clean.replace(/[+#]$/, '')) || [];
        }
        if (matches.length === 1) return { ply: matches[0], reason: 'unique' };
        if (matches.length > 1) return { ply: null, reason: 'ambiguous' };
        return { ply: null, reason: 'variant' };
    }

    function skipParent(node) {
        let el = node.parentElement;
        while (el) {
            const tag = el.tagName;
            if (tag === 'CODE' || tag === 'PRE' || tag === 'A' ||
                tag === 'SCRIPT' || tag === 'STYLE') {
                return true;
            }
            if (el.classList && (el.classList.contains('analysis-move') || el.classList.contains('analysis-move-variant'))) {
                return true;
            }
            el = el.parentElement;
        }
        return false;
    }

    function makeSpan(san, info) {
        const span = document.createElement('span');
        span.textContent = san;
        if (info.ply !== null) {
            span.className = 'analysis-move';
            span.dataset.ply = String(info.ply);
            span.title = 'Перейти к этому ходу';
            span.setAttribute('role', 'button');
            span.tabIndex = 0;
        } else if (info.reason === 'ambiguous') {
            span.className = 'analysis-move-variant analysis-move-ambiguous';
            span.title = 'Ход встречается несколько раз — нужен номер';
        } else {
            span.className = 'analysis-move-variant';
            span.title = 'Вариант или ход, которого нет в этой партии';
        }
        return span;
    }

    function linkify(root, index, onMove) {
        if (!root) return;
        if (!index) return;

        const nodes = [];
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                if (!node.nodeValue || !node.nodeValue.trim()) {
                    return NodeFilter.FILTER_REJECT;
                }
                return skipParent(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            },
        });
        while (walker.nextNode()) nodes.push(walker.currentNode);

        nodes.forEach(function (node) {
            const text = node.nodeValue;
            SAN_RE.lastIndex = 0;
            let match;
            let last = 0;
            let fragment = null;

            while ((match = SAN_RE.exec(text)) !== null) {
                const san = match[0];
                const offset = match.index;

                // Номер хода и цвет — непосредственно перед SAN.
                const before = text.slice(0, offset);
                const numMatch = before.match(/(\d{1,3})\.(\.\.)?\s*$/);
                const moveNumber = numMatch ? numMatch[1] : '';
                const color = numMatch ? (numMatch[2] ? 'black' : 'white') : '';

                const info = resolve(index, san, moveNumber, color);
                if (info.reason === 'none') continue;

                if (!fragment) fragment = document.createDocumentFragment();
                if (last < offset) {
                    fragment.appendChild(document.createTextNode(text.slice(last, offset)));
                }
                fragment.appendChild(makeSpan(san, info));
                last = offset + san.length;
            }

            if (fragment) {
                if (last < text.length) {
                    fragment.appendChild(document.createTextNode(text.slice(last)));
                }
                node.parentNode.replaceChild(fragment, node);
            }
        });

        if (!root.dataset.analysisMovesBound) {
            root.dataset.analysisMovesBound = '1';
            const activate = function (target) {
                const move = target.closest ? target.closest('.analysis-move') : null;
                if (!move || !root.contains(move)) return;
                const ply = parseInt(move.dataset.ply, 10);
                if (!Number.isNaN(ply) && typeof onMove === 'function') {
                    onMove(ply);
                }
            };
            root.addEventListener('click', function (event) {
                activate(event.target);
            });
            root.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    activate(event.target);
                }
            });
        }
    }

    function setActive(root, ply) {
        if (!root) return;
        const index = parseInt(ply, 10);
        root.querySelectorAll('.analysis-move').forEach(function (el) {
            el.classList.toggle(
                'active',
                !Number.isNaN(index) && parseInt(el.dataset.ply, 10) === index
            );
        });
    }

    window.AnalysisMoves = {
        buildIndex: buildIndex,
        linkify: linkify,
        setActive: setActive,
    };
})();
