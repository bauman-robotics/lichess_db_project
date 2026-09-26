// ============================================
// ОБЩИЙ JS ДЛЯ АНАЛИЗА ПАРТИЙ ЧЕРЕЗ DEEPSEEK
// ============================================
// Работает на страницах:
//   - player_stats.html (таблица «Последние игры»)
//   - player_openings.html (таблица + карточки)
//
// Требует:
//   - модалку с id="analysisModal" на странице
//   - кнопки с классом .btn-analysis
//   - библиотеки marked.js и DOMPurify в base.html
//   - опционально: game_viewer.js для кнопки «Смотреть партию»
// ============================================

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {

        const modalEl = document.getElementById('analysisModal');
        if (!modalEl) {
            return;
        }

        // ---------- CSRF-токен ----------
        const csrfEl = document.querySelector('[name=csrf_token]');
        const CSRF_TOKEN = csrfEl ? csrfEl.value : '';

        // ---------- Модалка Bootstrap ----------
        const modal = new bootstrap.Modal(modalEl);

        // ---------- Элементы модалки ----------
        const elGameId     = document.getElementById('analysis-game-id');
        const elMetaDate   = document.getElementById('meta-date');
        const elMetaResult = document.getElementById('meta-result');
        const elMetaOpp    = document.getElementById('meta-opponent');
        const elMetaOpen   = document.getElementById('meta-opening');
        const elPgn        = document.getElementById('analysis-pgn');
        const elStatus     = document.getElementById('analysis-status');
        const elError      = document.getElementById('analysis-error');
        const elContent    = document.getElementById('analysis-content');

        // ---------- Состояние ----------
        let currentGame = null;  // { username, gameId }

        // ---------- Утилиты ----------

        function setButtonState(btn, state) {
            btn.dataset.state = state;
            btn.classList.remove(
                'btn-analysis-none',
                'btn-analysis-running',
                'btn-analysis-done',
                'btn-analysis-error'
            );
            btn.classList.add('btn-analysis-' + state);

            let icon = '🤖';
            if (state === 'running')      icon = '⏳';
            else if (state === 'done')    icon = '✅';
            else if (state === 'error')   icon = '❌';

            const iconEl = btn.querySelector('.btn-analysis-icon');
            if (iconEl) {
                iconEl.textContent = icon;
            } else {
                btn.textContent = icon;
            }
        }

        function resetModal() {
            elGameId.textContent = '';
            elMetaDate.textContent = '—';
            elMetaResult.textContent = '—';
            elMetaOpp.textContent = '—';
            elMetaOpen.textContent = '—';
            elPgn.textContent = '—';
            elContent.textContent = '';
            elError.classList.add('d-none');
            elStatus.classList.add('d-none');
        }

        function renderMarkdown(text) {
            if (!text) {
                elContent.textContent = '';
                return;
            }
            try {
                let html = marked.parse(text);
                if (typeof DOMPurify !== 'undefined') {
                    html = DOMPurify.sanitize(html);
                }
                elContent.innerHTML = html;
            } catch (e) {
                console.error('Markdown error:', e);
                elContent.textContent = text;
            }
        }

        function showError(msg) {
            elError.textContent = '❌ ' + msg;
            elError.classList.remove('d-none');
            elStatus.classList.add('d-none');
        }

        async function loadPgn(username, gameId) {
            elPgn.textContent = 'Загрузка…';
            try {
                const r = await fetch(
                    `/lichess-analyzer/player/${username}/game/${gameId}/pgn`,
                    { credentials: 'same-origin' }
                );
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const data = await r.json();
                elPgn.textContent = data.pgn || '—';
            } catch (e) {
                elPgn.textContent = 'Ошибка загрузки нотации';
            }
        }

        // ---------- Открытие модалки с готовым результатом ----------

        async function openModalWithResult(username, gameId) {
            currentGame = { username, gameId };

            resetModal();
            elGameId.textContent = gameId;
            modal.show();
            loadPgn(username, gameId);

            try {
                const r = await fetch(
                    `/lichess-analyzer/player/${username}/game/${gameId}/analyze`,
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': CSRF_TOKEN },
                        credentials: 'same-origin',
                    }
                );
                const data = await r.json();

                if (data.meta) {
                    elMetaDate.textContent = data.meta.date || '—';
                    elMetaResult.textContent = data.meta.result || '—';
                    elMetaOpp.textContent = data.meta.opponent
                        ? data.meta.opponent + (data.meta.opponent_rating ? ' (' + data.meta.opponent_rating + ')' : '')
                        : '—';
                    elMetaOpen.textContent = data.meta.opening || '—';
                }

                if (data.status === 'done' && data.analysis) {
                    renderMarkdown(data.analysis);
                } else {
                    showError(data.message || 'Не удалось загрузить анализ');
                }
            } catch (e) {
                showError('Ошибка: ' + e.message);
            }
        }

        // ---------- Запуск анализа (без открытия модалки) ----------

        async function startAnalysis(username, gameId, button) {
            setButtonState(button, 'running');

            try {
                const r = await fetch(
                    `/lichess-analyzer/player/${username}/game/${gameId}/analyze`,
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': CSRF_TOKEN },
                        credentials: 'same-origin',
                    }
                );
                const data = await r.json();

                if (data.status === 'done') {
                    setButtonState(button, 'done');
                    openModalWithResult(username, gameId);
                    return;
                }
                if (data.status === 'started') {
                    pollStatus(username, gameId, data.task_id, button);
                    return;
                }
                if (data.status === 'busy') {
                    setButtonState(button, 'none');
                    alert(data.message || 'Дождитесь окончания текущего анализа');
                    return;
                }
                setButtonState(button, 'error');
                alert(data.message || 'Ошибка анализа');
            } catch (e) {
                setButtonState(button, 'error');
                alert('Ошибка сети: ' + e.message);
            }
        }

        // ---------- Polling статуса ----------

        async function pollStatus(username, gameId, taskId, button) {
            const url = `/lichess-analyzer/player/${username}/game/${gameId}/analyze/status/${taskId}`;
            let attempts = 0;
            const maxAttempts = 60;

            const tick = async () => {
                attempts++;
                try {
                    const r = await fetch(url, { credentials: 'same-origin' });
                    const data = await r.json();

                    if (data.status === 'done') {
                        setButtonState(button, 'done');
                        openModalWithResult(username, gameId);
                        return;
                    }
                    if (data.status === 'error') {
                        setButtonState(button, 'error');
                        alert(data.message || 'Ошибка анализа');
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        setButtonState(button, 'error');
                        alert('Превышено время ожидания');
                        return;
                    }
                    setTimeout(tick, 2000);
                } catch (e) {
                    setButtonState(button, 'error');
                    alert('Ошибка сети: ' + e.message);
                }
            };

            setTimeout(tick, 2000);
        }

        // ---------- Кнопка «Смотреть партию» в модалке анализа ----------
        document.getElementById('viewFromAnalysisBtn')?.addEventListener('click', () => {
            if (!currentGame) return;

            const { username, gameId } = currentGame;

            // Закрываем модалку анализа
            modal.hide();

            // Открываем модалку просмотра
            if (typeof window.openGameViewer === 'function') {
                window.openGameViewer(username, gameId);
            } else {
                console.warn('openGameViewer недоступен — game_viewer.js не загружен');
                window.open(`https://lichess.org/${gameId}`, '_blank');
            }
        });

        // ---------- Обработка кликов по кнопкам анализа ----------

        document.querySelectorAll('.btn-analysis').forEach(btn => {
            setButtonState(btn, btn.dataset.state || 'none');

            btn.addEventListener('click', () => {
                const state = btn.dataset.state;
                const username = btn.dataset.username;
                const gameId = btn.dataset.gameId;

                if (state === 'done') {
                    openModalWithResult(username, gameId);
                    return;
                }
                if (state === 'running') {
                    alert('Анализ уже выполняется. Дождитесь ответа.');
                    return;
                }
                startAnalysis(username, gameId, btn);
            });
        });

    });

})();