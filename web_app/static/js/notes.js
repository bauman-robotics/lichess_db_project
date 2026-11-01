// Заметки к партиям: модалка, сохранение, индикаторы.
(function () {
    'use strict';

    const modalEl = document.getElementById('noteModal');
    if (!modalEl) return;

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const gameLabel = document.getElementById('noteModalGame');
    const textarea = document.getElementById('noteModalText');
    const status = document.getElementById('noteModalStatus');
    const saveBtn = document.getElementById('noteModalSave');
    const deleteBtn = document.getElementById('noteModalDelete');
    let current = null;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function apiUrl(username, gameId) {
        return '/lichess-analyzer/annotations/'
            + encodeURIComponent(username) + '/'
            + encodeURIComponent(gameId);
    }

    function setStatus(value, isError) {
        status.textContent = value || '';
        status.className = 'small mt-2 ' + (isError ? 'text-danger' : 'text-muted');
    }

    function setBusy(busy) {
        saveBtn.disabled = busy;
        deleteBtn.disabled = busy;
        textarea.disabled = busy;
    }

    function updateButtons(username, gameId, hasNote) {
        document.querySelectorAll('.btn-note').forEach(function (button) {
            if (button.dataset.username !== username || button.dataset.gameId !== gameId) {
                return;
            }
            button.dataset.hasNote = hasNote ? '1' : '0';
            button.classList.toggle('has-note', hasNote);
            button.title = hasNote ? 'Заметка есть' : 'Добавить заметку';
        });

        const badge = document.querySelector('[data-note-count]');
        if (badge && window.__noteModalHadNote !== hasNote) {
            let count = parseInt(badge.textContent, 10) || 0;
            count += hasNote ? 1 : -1;
            badge.textContent = String(Math.max(0, count));
        }
        window.__noteModalHadNote = hasNote;
    }

    async function openEditor(button) {
        current = {
            username: button.dataset.username,
            gameId: button.dataset.gameId,
            hadNote: button.dataset.hasNote === '1',
        };
        window.__noteModalHadNote = current.hadNote;
        gameLabel.textContent = 'Игрок: ' + current.username + ' · партия ' + current.gameId;
        textarea.value = '';
        setStatus('Загрузка…', false);
        setBusy(true);
        modal.show();

        try {
            const response = await fetch(apiUrl(current.username, current.gameId), {
                credentials: 'same-origin',
            });
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            textarea.value = data.note || '';
            current.hadNote = !!data.has_note;
            window.__noteModalHadNote = current.hadNote;
            deleteBtn.classList.toggle('d-none', !data.note);
            setStatus('', false);
        } catch (error) {
            setStatus('Не удалось загрузить заметку: ' + error.message, true);
        } finally {
            setBusy(false);
            textarea.focus();
        }
    }

    async function save(note) {
        if (!current) return;
        setBusy(true);
        setStatus('Сохранение…', false);
        try {
            const response = await fetch(apiUrl(current.username, current.gameId), {
                method: 'PATCH',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({ note: note }),
            });
            const data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));

            updateButtons(current.username, current.gameId, !!data.has_note);
            setStatus('', false);
            modal.hide();
        } catch (error) {
            setStatus('Ошибка сохранения: ' + error.message, true);
        } finally {
            setBusy(false);
        }
    }

    document.addEventListener('click', function (event) {
        const button = event.target.closest('.btn-note');
        if (!button) return;
        event.preventDefault();
        openEditor(button);
    });

    saveBtn.addEventListener('click', function () {
        save(textarea.value);
    });

    deleteBtn.addEventListener('click', function () {
        textarea.value = '';
        save('');
    });

    textarea.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            save(textarea.value);
        }
    });
})();
