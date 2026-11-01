// График преимущества и запуск Stockfish на странице просмотра.
(function () {
    'use strict';

    const ctx = window.ENGINE_CONTEXT || {};
    const panel = document.getElementById('engineEvalPanel');
    if (!panel || !ctx.username || !ctx.gameId) return;

    const canvas = document.getElementById('engineEvalChart');
    const empty = document.getElementById('engineEvalEmpty');
    const emptyText = document.getElementById('engineEvalEmptyText');
    const analyzeBtn = document.getElementById('engineAnalyzeBtn');
    const taskStatus = document.getElementById('engineTaskStatus');
    const toggle = document.getElementById('engineGraphToggle');
    const sourceLabel = document.getElementById('engineEvalSource');
    const body = document.getElementById('engineEvalBody');

    let chart = null;
    let positions = [];
    let taskTimer = null;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function fmtEval(cp, mate) {
        if (mate !== null && mate !== undefined) return '#' + mate;
        if (cp === null || cp === undefined) return '—';
        return (cp / 100).toFixed(2);
    }

    function valueOf(pos) {
        if (pos.mate !== null && pos.mate !== undefined) {
            return pos.mate > 0 ? 10 : -10;
        }
        if (pos.eval_cp !== null && pos.eval_cp !== undefined) {
            return Math.max(-10, Math.min(10, pos.eval_cp / 100));
        }
        return null;
    }

    function buildLabels() {
        return positions.map(function (pos) {
            if (!pos.move_number) return 'начало';
            return pos.move_number + (pos.color === 'black' ? '…' : '.');
        });
    }

    function hasAnyEval() {
        return positions.some(function (p) {
            return (p.eval_cp !== null && p.eval_cp !== undefined) ||
                (p.mate !== null && p.mate !== undefined);
        });
    }

    function sourceText() {
        const sources = new Set();
        positions.forEach(function (p) {
            if (p.eval_source) sources.add(p.eval_source);
        });
        if (sources.has('lichess') && sources.has('engine')) return 'Lichess + Stockfish';
        if (sources.has('lichess')) return 'Lichess';
        if (sources.has('engine')) return 'Stockfish';
        return 'нет оценок';
    }

    function drawChart() {
        if (!hasAnyEval()) {
            if (chart) { chart.destroy(); chart = null; }
            canvas.classList.add('d-none');
            empty.classList.remove('d-none');
            analyzeBtn.classList.remove('d-none');
            sourceLabel.textContent = 'нет оценок · depth ' + ctx.depth;
            return;
        }

        canvas.classList.remove('d-none');
        empty.classList.add('d-none');
        sourceLabel.textContent = sourceText() + ' · depth ' + ctx.depth;

        const values = positions.map(valueOf);
        const labels = buildLabels();

        if (chart) chart.destroy();
        chart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Оценка (белые +)',
                    data: values,
                    borderColor: 'rgba(54, 162, 235, 0.9)',
                    backgroundColor: 'rgba(54, 162, 235, 0.12)',
                    borderWidth: 1.5,
                    tension: 0.1,
                    fill: true,
                    spanGaps: false,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    pointHitRadius: 10,
                    pointBackgroundColor: values.map(function (v, i) {
                        if (positions[i] && positions[i].result === 'Loss') return 'rgb(220, 53, 69)';
                        if (positions[i] && positions[i].result === 'Win') return 'rgb(40, 167, 69)';
                        return 'rgb(255, 193, 7)';
                    }),
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                onClick: function (event, elements) {
                    if (!elements.length) return;
                    const index = elements[0].index;
                    if (window.GameViewer) window.GameViewer.showPosition(index);
                },
                onHover: function (event, elements) {
                    if (event.native && event.native.target) {
                        event.native.target.style.cursor = elements.length ? 'pointer' : 'default';
                    }
                },
                scales: {
                    x: {
                        ticks: { maxTicksLimit: 14, autoSkip: true, maxRotation: 0 },
                        grid: { color: 'rgba(255,255,255,0.04)' }
                    },
                    y: {
                        suggestedMin: -10,
                        suggestedMax: 10,
                        ticks: { maxTicksLimit: 7 },
                        grid: { color: 'rgba(255,255,255,0.06)' }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: function (items) {
                                const i = items[0].dataIndex;
                                const p = positions[i];
                                if (!p) return '';
                                return p.move_number
                                    ? `${p.move_number}${p.color === 'black' ? '...' : '.'} ${p.san || ''}`
                                    : 'Начальная позиция';
                            },
                            label: function (item) {
                                const p = positions[item.dataIndex] || {};
                                return 'Оценка: ' + fmtEval(p.eval_cp, p.mate);
                            }
                        }
                    }
                }
            }
        });
    }

    async function loadPositions() {
        try {
            const response = await fetch(
                `/lichess-analyzer/player/${encodeURIComponent(ctx.username)}`
                + `/game/${encodeURIComponent(ctx.gameId)}/positions`,
                { credentials: 'same-origin' }
            );
            if (!response.ok) throw new Error('HTTP ' + response.status);
            const data = await response.json();
            positions = data.positions || [];
            drawChart();
            applyToggle();
        } catch (error) {
            emptyText.textContent = 'Не удалось загрузить оценки: ' + error.message;
        }
    }

    function applyToggle() {
        let open = localStorage.getItem('la_engine_graph');
        if (open === null) open = '1';
        const isOpen = open === '1';
        body.classList.toggle('d-none', !isOpen);
        toggle.textContent = isOpen ? 'Скрыть график' : 'Показать график';
    }

    toggle.addEventListener('click', function () {
        const isOpen = body.classList.contains('d-none');
        body.classList.toggle('d-none', !isOpen);
        toggle.textContent = isOpen ? 'Скрыть график' : 'Показать график';
        try { localStorage.setItem('la_engine_graph', isOpen ? '1' : '0'); } catch (e) {}
        // Пересчитать размер доски под изменившуюся высоту layout.
        window.dispatchEvent(new Event('resize'));
    });

    async function pollTask(taskId) {
        const url = `/lichess-analyzer/player/${encodeURIComponent(ctx.username)}`
            + `/game/${encodeURIComponent(ctx.gameId)}/engine/status/${encodeURIComponent(taskId)}`;
        try {
            const response = await fetch(url, { credentials: 'same-origin' });
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));

            if (data.status === 'queued') {
                taskStatus.textContent = 'В очереди…';
            } else if (data.status === 'running') {
                taskStatus.textContent = `Анализ: ${data.progress || 0} / ${data.total || '?'}`;
            } else if (data.status === 'done') {
                taskStatus.textContent = 'Готово. График обновлён.';
                await loadPositions();
                return;
            } else if (data.status === 'error') {
                taskStatus.textContent = 'Ошибка: ' + (data.error || 'неизвестная');
                analyzeBtn.disabled = false;
                return;
            }
        } catch (error) {
            taskStatus.textContent = 'Не удалось получить статус: ' + error.message;
        }
        taskTimer = setTimeout(function () { pollTask(taskId); }, 1000);
    }

    analyzeBtn.addEventListener('click', async function () {
        analyzeBtn.disabled = true;
        taskStatus.textContent = 'Запуск…';
        try {
            const response = await fetch(
                `/lichess-analyzer/player/${encodeURIComponent(ctx.username)}`
                + `/game/${encodeURIComponent(ctx.gameId)}/engine`,
                {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken(),
                    },
                    body: '{}',
                }
            );
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.error || ('HTTP ' + response.status));
            }
            pollTask(data.task_id);
        } catch (error) {
            analyzeBtn.disabled = false;
            taskStatus.textContent = 'Ошибка запуска: ' + error.message;
        }
    });

    window.addEventListener('gameviewer:position', function (event) {
        if (!chart || !event.detail) return;
        const index = event.detail.index;
        if (index === undefined || index === null) return;
        try {
            chart.setActiveElements([{ datasetIndex: 0, index: index }]);
            chart.update('none');
        } catch (e) {}
    });

    applyToggle();
    loadPositions();
})();
