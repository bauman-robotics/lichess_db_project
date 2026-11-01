// Статус фоновой задачи импорта игр.
(function () {
    'use strict';

    const banner = document.getElementById('importTaskBanner');
    if (!banner) return;

    const taskId = banner.dataset.taskId;
    const username = banner.dataset.username;
    const text = document.getElementById('importTaskText');
    const spinner = banner.querySelector('.spinner-border');
    if (!taskId || !username || !text) return;

    const url = '/lichess-analyzer/player/' + encodeURIComponent(username)
        + '/import/status/' + encodeURIComponent(taskId);
    let reloading = false;

    function setText(value) {
        text.textContent = value;
    }

    async function poll() {
        try {
            const response = await fetch(url, { credentials: 'same-origin' });
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) {
                throw new Error(data.error || ('HTTP ' + response.status));
            }

            if (data.status === 'queued') {
                setText('Задача в очереди…');
            } else if (data.status === 'running') {
                setText('Импорт выполняется… Это может занять несколько минут.');
            } else if (data.status === 'done') {
                if (reloading) return;
                reloading = true;
                if (spinner) spinner.classList.add('d-none');
                setText('Импорт завершён: сохранено ' + (data.saved || 0)
                    + ' из ' + (data.total || 0) + '. Обновляем страницу…');

                // Убираем import_task из URL, иначе после reload баннер
                // снова увидит status=done и перезагрузит страницу по кругу.
                const cleanUrl = new URL(window.location.href);
                cleanUrl.searchParams.delete('import_task');
                window.setTimeout(function () {
                    window.location.replace(cleanUrl.toString());
                }, 1200);
                return;
            } else if (data.status === 'error') {
                if (spinner) spinner.classList.add('d-none');
                banner.classList.remove('alert-info');
                banner.classList.add('alert-danger');
                setText('Ошибка импорта: ' + (data.error || 'неизвестная ошибка'));
                return;
            }
        } catch (error) {
            setText('Не удалось получить статус задачи: ' + error.message);
        }
        window.setTimeout(poll, 2000);
    }

    poll();
})();
