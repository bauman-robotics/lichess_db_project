// ============================================
// ПРОСМОТР ПАРТИИ С ДОСКОЙ
// ============================================
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const modalEl = document.getElementById('viewGameModal');
        if (!modalEl) return;

        const modal = new bootstrap.Modal(modalEl);

        const elGameId = document.getElementById('view-game-id');
        const elBoard = document.getElementById('viewBoard');
        const elMoveCounter = document.getElementById('viewMoveCounter');
        const elMoveTotal = document.getElementById('viewMoveTotal');
        const elMovesList = document.getElementById('viewMovesList');

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

            // Подменяем getElementById в renderer — он ищет 'chessBoard'
            // Временно присваиваем id нашему контейнеру
            elBoard.id = 'chessBoard';

            board.init();
            renderer.render();
        }

        // ---------- Показ позиции ----------
        function showPosition(index) {
            if (!positions.length) return;

            currentIndex = Math.max(0, Math.min(index, positions.length - 1));
            const pos = positions[currentIndex];

            board.loadFromFEN(pos.fen);

            // Подсветка последнего хода
            if (currentIndex > 0) {
                // Восстанавливаем lastMove по предыдущему ходу
                // (FEN не содержит, откуда пришёл ход — можно вычислить,
                //  но для простоты пока пропустим)
            }

            renderer.render();
            highlightMoveInList(currentIndex);
            elMoveCounter.textContent = currentIndex;
        }

        // ---------- Список ходов ----------
        function buildMovesList() {
            elMovesList.innerHTML = '';

            // Группируем по номерам: 1. d4 d5, 2. c4 e6, ...
            let i = 1; // пропускаем начальную позицию (index 0)
            while (i < positions.length) {
                const white = positions[i];
                const black = positions[i + 1];

                const row = document.createElement('div');
                row.className = 'move-row';
                row.dataset.index = i;

                const num = document.createElement('span');
                num.className = 'move-number';
                num.textContent = `${white.move_number}.`;
                row.appendChild(num);

                const sanW = document.createElement('span');
                sanW.className = 'move-san white';
                sanW.textContent = white.san;
                sanW.dataset.index = i;
                sanW.style.cursor = 'pointer';
                sanW.onclick = () => showPosition(i);
                row.appendChild(sanW);

                if (black) {
                    const sanB = document.createElement('span');
                    sanB.className = 'move-san black';
                    sanB.textContent = black.san;
                    sanB.dataset.index = i + 1;
                    sanB.style.cursor = 'pointer';
                    sanB.style.marginLeft = '8px';
                    sanB.onclick = () => showPosition(i + 1);
                    row.appendChild(sanB);
                }

                elMovesList.appendChild(row);
                i += 2;
            }

            elMoveTotal.textContent = positions.length - 1;
        }

        function highlightMoveInList(index) {
            elMovesList.querySelectorAll('.move-row').forEach(r => r.classList.remove('active'));
            elMovesList.querySelectorAll('.move-san').forEach(s => s.classList.remove('active'));

            const san = elMovesList.querySelector(`.move-san[data-index="${index}"]`);
            if (san) {
                san.classList.add('active');
                san.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }

        // ---------- Кнопки навигации ----------
        document.getElementById('viewFirst').onclick = () => showPosition(0);
        document.getElementById('viewPrev').onclick = () => showPosition(currentIndex - 1);
        document.getElementById('viewNext').onclick = () => showPosition(currentIndex + 1);
        document.getElementById('viewLast').onclick = () => showPosition(positions.length - 1);

        document.getElementById('viewPlay').onclick = function () {
            if (playing) {
                clearInterval(timer);
                playing = false;
                this.textContent = '▶';
                return;
            }

            if (currentIndex >= positions.length - 1) {
                currentIndex = 0;
            }

            playing = true;
            this.textContent = '⏸';

            timer = setInterval(() => {
                if (currentIndex >= positions.length - 1) {
                    clearInterval(timer);
                    playing = false;
                    document.getElementById('viewPlay').textContent = '▶';
                    return;
                }
                showPosition(currentIndex + 1);
            }, 800);
        };

        // ---------- Открытие модалки ----------
        async function openViewer(username, gameId) {
            initBoard();

            elGameId.textContent = gameId;
            elMovesList.innerHTML = '<div class="text-muted">Загрузка…</div>';

            modal.show();

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

                positions = data.positions;
                buildMovesList();
                showPosition(0);
            } catch (e) {
                elMovesList.innerHTML = `<div class="text-danger">Ошибка: ${e.message}</div>`;
            }
        }

        // ---------- Обработка кликов по кнопкам ----------
        document.querySelectorAll('.btn-view-game').forEach(btn => {
            btn.addEventListener('click', () => {
                openViewer(btn.dataset.username, btn.dataset.gameId);
            });
        });
    });
})();