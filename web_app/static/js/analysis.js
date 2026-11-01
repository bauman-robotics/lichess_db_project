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
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const CSRF_TOKEN = csrfEl ? csrfEl.value : (csrfMeta ? csrfMeta.content : '');

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
        const elStatusText = document.getElementById('analysis-status-text');
        const elError      = document.getElementById('analysis-error');
        const elContent    = document.getElementById('analysis-content');
        const elPromptButtons = Array.from(
            document.querySelectorAll('.analysis-prompt-btn')
        );
        const elRerunBtn = document.getElementById('analysisRerunBtn');

        // ---------- Состояние ----------
        let currentGame = null;  // { username, gameId }
        let analysisMoveIndex = null;
        let selectedPrompt = '';

        function selectPrompt(key) {
            selectedPrompt = key || '';
            elPromptButtons.forEach(function (button) {
                button.classList.toggle('active', button.dataset.promptKey === selectedPrompt);
            });
            try {
                if (selectedPrompt) {
                    localStorage.setItem('analysis_prompt', selectedPrompt);
                }
            } catch (e) { /* localStorage может быть недоступен */ }
        }

        if (elPromptButtons.length) {
            const container = document.getElementById('analysisPromptButtons');
            const defaultPrompt = container ? container.dataset.defaultPrompt : '';
            const hasDefault = elPromptButtons.some(function (b) {
                return b.dataset.promptKey === defaultPrompt;
            });
            // По умолчанию подсвечиваем промпт из конфига, а не первый в списке.
            selectPrompt(hasDefault ? defaultPrompt : elPromptButtons[0].dataset.promptKey);
            elPromptButtons.forEach(function (button) {
                button.addEventListener('click', function () {
                    selectPrompt(button.dataset.promptKey);
                });
            });
        }

        // ---------- Утилиты ----------

        function setButtonState(btn, state) {
            if (!btn) return;
            btn.dataset.state = state;
            btn.classList.remove(
                'btn-analysis-none',
                'btn-analysis-running',
                'btn-analysis-done',
                'btn-analysis-error',
                'btn-analysis-engine'
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
                // Не затираем индикаторы оценок, если у кнопки нет icon-обёртки.
                const dots = Array.from(btn.querySelectorAll('.analysis-eval-dot'));
                btn.textContent = icon;
                dots.forEach(function (dot) { btn.appendChild(dot); });
            }
        }

        function setButtonStage(btn, stage, progress, total) {
            if (!btn) return;
            const iconEl = btn.querySelector('.btn-analysis-icon');
            if (stage === 'engine') {
                btn.classList.add('btn-analysis-engine');
                btn.title = `Stockfish: ${progress || 0} / ${total || '?'}`;
                if (iconEl) iconEl.textContent = '📈';
                if (elStatusText) {
                    elStatusText.textContent =
                        `Stockfish: ${progress || 0} / ${total || '?'}`;
                }
            } else {
                btn.classList.remove('btn-analysis-engine');
                btn.title = 'Анализ партии через DeepSeek';
                if (iconEl) iconEl.textContent = '⏳';
                if (elStatusText) elStatusText.textContent = 'DeepSeek думает…';
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
                if (window.AnalysisMoves && analysisMoveIndex) {
                    window.AnalysisMoves.linkify(
                        elContent,
                        analysisMoveIndex,
                        function (ply) { navigateToPly(currentGame, ply); }
                    );
                }
            } catch (e) {
                console.error('Markdown error:', e);
                elContent.textContent = text;
            }
        }

        function navigateToPly(game, ply) {
            if (!game) return;
            const url = `/lichess-analyzer/player/${encodeURIComponent(game.username)}`
                + `/game/${encodeURIComponent(game.gameId)}/view?ply=${ply}`;
            if (typeof window.openGameViewer === 'function'
                && document.getElementById('viewGameModal')) {
                modal.hide();
                window.openGameViewer(game.username, game.gameId, { startPly: ply });
            } else {
                window.location.href = url;
            }
        }

        async function loadAnalysisPositions(username, gameId) {
            analysisMoveIndex = null;
            try {
                const response = await fetch(
                    `/lichess-analyzer/player/${encodeURIComponent(username)}`
                    + `/game/${encodeURIComponent(gameId)}/positions`,
                    { credentials: 'same-origin' }
                );
                if (!response.ok) return;
                const data = await response.json();
                if (window.AnalysisMoves && data.positions) {
                    analysisMoveIndex = window.AnalysisMoves.buildIndex(data.positions);
                }
            } catch (e) {
                analysisMoveIndex = null;
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
            // console.log('[analysis] openModalWithResult ВЫЗВАНА');
            // console.log('[analysis]   username:', username);
            // console.log('[analysis]   gameId:', gameId);
            currentGame = { username, gameId };

            // Обновить ссылку «Смотреть партию» под текущую партию
            const viewLink = document.getElementById('viewFromAnalysisLink');
            if (viewLink) {
                viewLink.href = `/lichess-analyzer/player/${username}/game/${gameId}/view`;
            }            

            resetModal();
            elGameId.textContent = gameId;
            modal.show();
            loadPgn(username, gameId);
            await loadAnalysisPositions(username, gameId);

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

        async function startAnalysis(username, gameId, button, options) {
            setButtonState(button, 'running');
            if (elRerunBtn) elRerunBtn.disabled = true;

            try {
                const r = await fetch(
                    `/lichess-analyzer/player/${username}/game/${gameId}/analyze`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CSRF_TOKEN,
                        },
                        credentials: 'same-origin',
                        body: JSON.stringify(options || {}),
                    }
                );
                const data = await r.json();

                if (data.status === 'done') {
                    setButtonState(button, 'done');
                    if (elRerunBtn) elRerunBtn.disabled = false;
                    openModalWithResult(username, gameId);
                    return;
                }
                if (data.status === 'started') {
                    pollStatus(username, gameId, data.task_id, button);
                    return;
                }
                if (data.status === 'busy') {
                    setButtonState(button, 'none');
                    if (elRerunBtn) elRerunBtn.disabled = false;
                    alert(data.message || 'Дождитесь окончания текущего анализа');
                    return;
                }
                setButtonState(button, 'error');
                alert(data.message || 'Ошибка анализа');
                if (elRerunBtn) elRerunBtn.disabled = false;
            } catch (e) {
                setButtonState(button, 'error');
                alert('Ошибка сети: ' + e.message);
                if (elRerunBtn) elRerunBtn.disabled = false;
            }
        }

        // ---------- Polling статуса ----------

        async function pollStatus(username, gameId, taskId, button) {
            const url = `/lichess-analyzer/player/${username}/game/${gameId}/analyze/status/${taskId}`;
            let attempts = 0;
            const maxAttempts = 180;

            const tick = async () => {
                attempts++;
                try {
                    const r = await fetch(url, { credentials: 'same-origin' });
                    const data = await r.json();

                    if (data.status === 'running') {
                        setButtonStage(button, data.stage || 'deepseek',
                            data.progress, data.total);
                    }
                    if (data.status === 'done') {
                        setButtonState(button, 'done');
                        if (elRerunBtn) elRerunBtn.disabled = false;
                        openModalWithResult(username, gameId);
                        return;
                    }
                    if (data.status === 'error') {
                        setButtonState(button, 'error');
                        if (elStatusText) elStatusText.textContent = 'Ошибка анализа';
                        if (elRerunBtn) elRerunBtn.disabled = false;
                        alert(data.message || 'Ошибка анализа');
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        setButtonState(button, 'error');
                        if (elRerunBtn) elRerunBtn.disabled = false;
                        alert('Превышено время ожидания');
                        return;
                    }
                    setTimeout(tick, 2000);
                } catch (e) {
                    setButtonState(button, 'error');
                    if (elRerunBtn) elRerunBtn.disabled = false;
                    alert('Ошибка сети: ' + e.message);
                }
            };

            setTimeout(tick, 2000);
        }

        if (elRerunBtn) {
            elRerunBtn.addEventListener('click', function () {
                if (!currentGame) return;
                elContent.textContent = '';
                elError.classList.add('d-none');
                elStatus.classList.remove('d-none');
                startAnalysis(
                    currentGame.username,
                    currentGame.gameId,
                    null,
                    { force: true, prompt_key: selectedPrompt }
                );
            });
        }

        // ---------- Обработка кликов по кнопкам анализа ----------

        document.querySelectorAll('.btn-analysis').forEach(btn => {
            setButtonState(btn, btn.dataset.state || 'none');

            btn.addEventListener('click', () => {
                const state = btn.dataset.state;
                const username = btn.dataset.username;
                const gameId = btn.dataset.gameId;

                // console.log('[analysis] КЛИК по .btn-analysis');
                // console.log('[analysis]   state:', state);
                // console.log('[analysis]   username:', username);
                // console.log('[analysis]   gameId:', gameId);

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