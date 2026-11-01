// ============================================
// ИЗБРАННЫЕ ПАРТИИ
// ============================================
// Кнопки .btn-favorite есть в таблицах, карточках и на странице партии.
// Заметки редактируются на странице /favorites.

(function () {
    'use strict';

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function showToast(message) {
        var toast = document.createElement('div');
        toast.className = 'app-toast';
        toast.textContent = message;
        document.body.appendChild(toast);
        window.setTimeout(function () {
            toast.classList.add('app-toast-hide');
        }, 2400);
        window.setTimeout(function () {
            toast.remove();
        }, 3000);
    }

    function updateCount(count) {
        document.querySelectorAll('[data-favorite-count]').forEach(function (el) {
            el.textContent = String(count);
        });
    }

    function updateButtons(username, gameId, favorited) {
        document.querySelectorAll('.btn-favorite').forEach(function (button) {
            if (button.dataset.username !== username || button.dataset.gameId !== gameId) {
                return;
            }
            button.dataset.favorited = favorited ? 'true' : 'false';
            button.classList.toggle('is-favorite', favorited);
            button.setAttribute('aria-pressed', favorited ? 'true' : 'false');
            button.title = favorited ? 'Убрать из избранного' : 'В избранное';
            var icon = button.querySelector('.favorite-icon');
            if (icon) icon.textContent = favorited ? '★' : '☆';
            var label = button.querySelector('.favorite-label');
            if (label) label.textContent = favorited ? 'В избранном' : 'В избранное';
        });
    }

    async function toggleFavorite(button) {
        var username = button.dataset.username;
        var gameId = button.dataset.gameId;
        if (!username || !gameId) return;

        var favorited = button.dataset.favorited === 'true';
        button.disabled = true;

        try {
            var response = await fetch(
                favorited
                    ? '/lichess-analyzer/favorites/' + encodeURIComponent(username)
                        + '/' + encodeURIComponent(gameId)
                    : '/lichess-analyzer/favorites',
                {
                    method: favorited ? 'DELETE' : 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken()
                    },
                    body: favorited ? null : JSON.stringify({
                        player_username: username,
                        game_id: gameId
                    })
                }
            );

            var data = {};
            try { data = await response.json(); } catch (e) { /* ignore */ }

            if (!response.ok) {
                throw new Error(data.error || ('HTTP ' + response.status));
            }

            updateButtons(username, gameId, data.favorited);
            updateCount(data.count);
            showToast(data.favorited ? 'Добавлено в избранное' : 'Удалено из избранного');

            if (!data.favorited) {
                var card = button.closest('[data-favorite-card]');
                if (card) {
                    card.remove();
                    var list = document.querySelector('[data-favorites-list]');
                    if (list && !list.querySelector('[data-favorite-card]')) {
                        var empty = document.getElementById('favoritesEmpty');
                        if (empty) empty.classList.remove('d-none');
                    }
                }
            }
        } catch (error) {
            showToast('Не удалось обновить избранное: ' + error.message);
        } finally {
            button.disabled = false;
        }
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest('.btn-favorite');
        if (button) {
            event.preventDefault();
            toggleFavorite(button);
            return;
        }

        var editButton = event.target.closest('.btn-note-edit');
        if (editButton) {
            event.preventDefault();
            var card = editButton.closest('[data-favorite-card]');
            if (!card) return;
            var editor = card.querySelector('.favorite-note-editor');
            var view = card.querySelector('.favorite-note-view');
            if (editor) {
                editor.classList.remove('d-none');
                if (view) view.classList.add('d-none');
                var textarea = editor.querySelector('textarea');
                if (textarea) textarea.focus();
            }
            return;
        }

        var cancelButton = event.target.closest('.btn-note-cancel');
        if (cancelButton) {
            event.preventDefault();
            var card2 = cancelButton.closest('[data-favorite-card]');
            if (!card2) return;
            var editor2 = card2.querySelector('.favorite-note-editor');
            var view2 = card2.querySelector('.favorite-note-view');
            if (editor2) editor2.classList.add('d-none');
            if (view2) view2.classList.remove('d-none');
            return;
        }

        var saveButton = event.target.closest('.btn-note-save');
        if (saveButton) {
            event.preventDefault();
            saveNote(saveButton);
        }
    });

    async function saveNote(button) {
        var card = button.closest('[data-favorite-card]');
        if (!card) return;
        var username = card.dataset.player;
        var gameId = card.dataset.game;
        var textarea = card.querySelector('.favorite-note-editor textarea');
        if (!textarea) return;

        button.disabled = true;
        try {
            var response = await fetch(
                '/lichess-analyzer/favorites/' + encodeURIComponent(username)
                    + '/' + encodeURIComponent(gameId),
                {
                    method: 'PATCH',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken()
                    },
                    body: JSON.stringify({ note: textarea.value })
                }
            );
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok) {
                throw new Error(data.error || ('HTTP ' + response.status));
            }

            var view = card.querySelector('.favorite-note-view');
            if (view) {
                view.textContent = textarea.value || 'Без заметки';
                view.classList.toggle('favorite-note-empty', !textarea.value);
            }
            var editor = card.querySelector('.favorite-note-editor');
            if (editor) editor.classList.add('d-none');
            if (view) view.classList.remove('d-none');
            showToast('Заметка сохранена');
        } catch (error) {
            showToast('Не удалось сохранить заметку: ' + error.message);
        } finally {
            button.disabled = false;
        }
    }
})();
