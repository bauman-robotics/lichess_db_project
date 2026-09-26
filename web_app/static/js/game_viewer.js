// ============================================
// ПРОСМОТР ПАРТИИ С ДОСКОЙ
// ============================================
// Использует:
//   - ChessBoard    (chessboard/board.js)
//   - BoardRenderer (chessboard/renderer.js)
//   - PIECES_SVG    (chessboard/pieces.js)
//
// Требует на странице:
//   - модалку #viewGameModal
//   - кнопки .btn-view-game с data-username и data-game-id
//   - window.VIEWER_CONFIG (опционально)
// ============================================

(function () {
    'use strict';

    // Дефолтные значения (если VIEWER_CONFIG не задан)
    const DEFAULT_CFG = {
        boardSizeDesktop: 500,
        boardSizeMobile: 320,
        playIntervalMs: 800,
    };

    // Возвращает актуальный конфиг при каждом вызове.
    // Нужно потому, что window.VIEWER_CONFIG может быть установлен
    // ПОСЛЕ загрузки game_viewer.js (в {% block scripts %}).
    function getCfg() {
        return Object.assign({}, DEFAULT_CFG, window.VIEWER_CONFIG || {});
    }

    document.addEventListener('DOMContentLoaded', function () {

        const modalEl = document.getElementById('viewGameModal');
        if (!modalEl) {
            // На этой странице нет модалки просмотра — выходим
            return;
        }

        const modal = new bootstrap.Modal(modalEl);

        // Пересчитываем размер доски после отрисовки модалки
        modalEl.addEventListener('shown.bs.modal', () => {
            applyBoardSize();
        });

        // ---------- Элементы ----------
        const elGameId      = document.getElementById('view-game-id');
        const elBoard       = document.getElementById('viewBoard');
        const elMoveCounter = document.getElementById('viewMoveCounter');
        const elMoveTotal   = document.getElementById('viewMoveTotal');
        const elMovesList   = document.getElementById('viewMovesList');
        const elOpenLichess = document.getElementById('viewOpenLichess');

        // ---------- Состояние ----------
        let board = null;
        let renderer = null;
        let positions = [];
        let currentIndex = 0;
        let playing = false;
        let timer = null;

        // ---------- Инициализация доски ----------
        function initBoard() {
            if (board) return;

            board = new ChessBoard();
            renderer = new BoardRenderer(board, null);

            // renderer ищет элемент с id="chessBoard"
            elBoard.id = 'chessBoard';

            board.init();
            renderer.render();
            applyBoardSize();
        }

        function applyBoardSize() {
            const isMobile = window.innerWidth < 768;
            const cfg = getCfg();

            if (isMobile) {
                const container = elBoard.parentElement;
                const w = container.clientWidth;
                elBoard.style.width  = w + 'px';
                elBoard.style.height = w + 'px';
            } else {
                elBoard.style.width  = cfg.boardSizeDesktop + 'px';
                elBoard.style.height = cfg.boardSizeDesktop + 'px';
            }

            // На десктопе — список ходов и комментарии высотой с доску
            if (!isMobile) {
                const boardHeight = elBoard.offsetHeight;   // реальная высота доски в px

                const comments = document.querySelector('.viewer-comments');
                const moves = document.querySelector('.viewer-moves');

                if (comments) comments.style.maxHeight = boardHeight + 'px';
                if (moves)    moves.style.maxHeight    = boardHeight + 'px';
            } else {
                // На мобильных — сбрасываем inline max-height
                const comments = document.querySelector('.viewer-comments');
                const moves = document.querySelector('.viewer-moves');
                if (comments) comments.style.maxHeight = '';
                if (moves)    moves.style.maxHeight    = '';
            }
        }
        window.addEventListener('resize', applyBoardSize);

        // ---------- Показ позиции ----------
        function showPosition(index) {
            if (!positions.length) return;

            currentIndex = Math.max(0, Math.min(index, positions.length - 1));
            const pos = positions[currentIndex];

            board.loadFromFEN(pos.fen);
            board.setLastMoveFromAlgebraic(pos.from, pos.to);
            renderer.render();
            highlightMoveInList(currentIndex);
            elMoveCounter.textContent = currentIndex;
        }

        // ---------- Список ходов ----------
        function buildMovesList() {
            elMovesList.innerHTML = '';
            let i = 1; // пропускаем начальную позицию (index 0)

            while (i < positions.length) {
                const white = positions[i];
                const black = positions[i + 1];

                const row = document.createElement('div');
                row.className = 'move-row';

                const num = document.createElement('span');
                num.className = 'move-number';
                num.textContent = `${white.move_number}.`;
                row.appendChild(num);

                const sanW = document.createElement('span');
                sanW.className = 'move-san white';
                sanW.textContent = white.san;
                sanW.dataset.index = i;
                sanW.style.cursor = 'pointer';
                sanW.onclick = function () {
                    showPosition(parseInt(this.dataset.index, 10));
                };
                row.appendChild(sanW);

                if (black) {
                    const sanB = document.createElement('span');
                    sanB.className = 'move-san black';
                    sanB.textContent = black.san;
                    sanB.dataset.index = i + 1;
                    sanB.style.cursor = 'pointer';
                    sanB.style.marginLeft = '8px';
                    sanB.onclick = function () {
                        showPosition(parseInt(this.dataset.index, 10));
                    };
                    row.appendChild(sanB);
                }

                elMovesList.appendChild(row);
                i += 2;
            }

            elMoveTotal.textContent = positions.length - 1;
        }

        function highlightMoveInList(index) {
            // Снимаем активность со всех ходов
            elMovesList.querySelectorAll('.move-san').forEach(s => s.classList.remove('active'));

            const san = elMovesList.querySelector(`.move-san[data-index="${index}"]`);
            if (!san) return;

            san.classList.add('active');

            // Прокручиваем ТОЛЬКО контейнер ходов, не трогая страницу
            const container = elMovesList.parentElement;   // .viewer-moves
            if (!container) return;

            const containerRect = container.getBoundingClientRect();
            const sanRect = san.getBoundingClientRect();

            if (sanRect.top < containerRect.top) {
                container.scrollTop -= (containerRect.top - sanRect.top);
            } else if (sanRect.bottom > containerRect.bottom) {
                container.scrollTop += (sanRect.bottom - containerRect.bottom);
            }
        }

        // ---------- Кнопки навигации ----------
        document.getElementById('viewFirst').onclick = () => showPosition(0);
        document.getElementById('viewPrev').onclick  = () => showPosition(currentIndex - 1);
        document.getElementById('viewNext').onclick  = () => showPosition(currentIndex + 1);
        document.getElementById('viewLast').onclick  = () => showPosition(positions.length - 1);

        document.getElementById('viewFlip').onclick = () => {
            if (!board) return;
            board.flipped = !board.flipped;
            renderer.render();
        };

        document.getElementById('viewPlay').onclick = function () {
            if (playing) {
                clearInterval(timer);
                playing = false;
                this.textContent = '⏯';
                return;
            }

            if (currentIndex >= positions.length - 1) {
                currentIndex = 0;
            }

            const cfg = getCfg();

            playing = true;
            this.textContent = '⏸';

            timer = setInterval(() => {
                if (currentIndex >= positions.length - 1) {
                    clearInterval(timer);
                    playing = false;
                    document.getElementById('viewPlay').textContent = '⏯';
                    return;
                }
                showPosition(currentIndex + 1);
            }, cfg.playIntervalMs);
        };

        // Убираем фокус с кнопок навигации после клика —
        // чтобы браузер не «прыгал» к кнопке и не сдвигал модалку
        ['viewFirst', 'viewPrev', 'viewPlay', 'viewNext', 'viewLast', 'viewFlip'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.addEventListener('click', () => btn.blur());
            }
        });

        // ---------- Клавиатура ----------
        document.addEventListener('keydown', (e) => {
            if (!modalEl.classList.contains('show')) return;

            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                showPosition(currentIndex - 1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                showPosition(currentIndex + 1);
            } else if (e.key === ' ') {
                e.preventDefault();
                document.getElementById('viewPlay').click();
            } else if (e.key === 'Home') {
                e.preventDefault();
                showPosition(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                showPosition(positions.length - 1);
            }
        });

        // ---------- Отображение анализа в левой колонке ----------
        function renderAnalysis(text) {
            const elComments = document.getElementById('viewComments');
            if (!elComments) return;

            if (!text || !text.trim()) {
                elComments.innerHTML = '<p class="text-muted">Анализ для этой партии пока не сделан.</p>';
                return;
            }

            // Markdown → HTML (marked + DOMPurify)
            try {
                let html = marked.parse(text);
                if (typeof DOMPurify !== 'undefined') {
                    html = DOMPurify.sanitize(html);
                }
                elComments.innerHTML = html;
            } catch (e) {
                console.error('Markdown error:', e);
                elComments.textContent = text;
            }
        }

        // ---------- Открытие модалки ----------
        async function openViewer(username, gameId) {
            initBoard();

            elGameId.textContent = gameId;
            elMovesList.innerHTML = '<div class="text-muted">Загрузка…</div>';

            if (elOpenLichess) {
                elOpenLichess.href = `https://lichess.org/${gameId}`;
            }

            modal.show();

            // Пересчитываем размер доски ПОСЛЕ отрисовки модалки
            setTimeout(applyBoardSize, 100);

            try {
                const r = await fetch(
                    `/lichess-analyzer/player/${username}/game/${gameId}/positions`,
                    { credentials: 'same-origin' }
                );
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const data = await r.json();

                if (!data.positions || !data.positions.length) {
                    elMovesList.innerHTML = '<div class="text-muted">Не удалось разобрать партию</div>';
                    return;
                }

                if (data.meta && data.meta.color === 'black') {
                    board.flipped = true;
                } else {
                    board.flipped = false;
                }

                // Выводим анализ в левую колонку
                renderAnalysis(data.analysis || '');

                positions = data.positions;
                buildMovesList();
                showPosition(0);

                // Ещё раз — на случай, если размер контейнера изменился
                applyBoardSize();

            } catch (e) {
                elMovesList.innerHTML = `<div class="text-danger">Ошибка: ${e.message}</div>`;
            }
        }

        // ---------- Обработка кликов по кнопкам .btn-view-game ----------
        document.querySelectorAll('.btn-view-game').forEach(btn => {
            btn.addEventListener('click', () => {
                openViewer(btn.dataset.username, btn.dataset.gameId);
            });
        });

        // Экспортируем функцию наружу — для кнопки «Смотреть» в модалке анализа
        window.openGameViewer = openViewer;

    });

})();