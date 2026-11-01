#!/usr/bin/env bash
#
# Обновление приложения на сервере.
#
# Обычно вызывается локальным scripts/deploy/update_remote.py,
# но может запускаться и вручную из любой точки репозитория:
#
#   bash scripts/deploy/server_update.sh
#   cd scripts/deploy && ./server_update.sh
#
# Переменные:
#   PROJECT_PATH    — путь к проекту; по умолчанию вычисляется от расположения скрипта
#   BRANCH          — ветка; пусто = текущая ветка сервера
#   SERVICE         — имя systemd-сервиса (по умолчанию lichess-analyzer)
#   RUN_MIGRATIONS  — 1/0, запускать setup_db.py --action create
#   SKIP_RESTART    — 1/0, не перезапускать сервис
#   USE_SUDO        — 1/0; по умолчанию 0 для root, иначе 1
#   PYTHON_BIN      — путь к python; по умолчанию venv/bin/python или python3
#   HEALTHCHECK_URL — URL для проверки после рестарта (опционально)
#   HEALTHCHECK_RETRIES — сколько секунд ждать ответа (по умолчанию 30)
#   DRY_RUN         — 1/0, только показать команды
#
set -euo pipefail

# Если PROJECT_PATH не задан, определяем корень репозитория по пути скрипта.
if [ -z "${PROJECT_PATH:-}" ]; then
    SCRIPT_SOURCE="${BASH_SOURCE[0]}"
    if [ -f "$SCRIPT_SOURCE" ]; then
        SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_SOURCE")" && pwd)"
        PROJECT_PATH="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
    fi
fi

BRANCH="${BRANCH:-}"
SERVICE="${SERVICE:-lichess-analyzer}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
if [ -z "${USE_SUDO:-}" ]; then
    if [ "$(id -u)" -eq 0 ]; then
        USE_SUDO=0
    else
        USE_SUDO=1
    fi
fi
PYTHON_BIN="${PYTHON_BIN:-}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
HEALTHCHECK_RETRIES="${HEALTHCHECK_RETRIES:-30}"
DRY_RUN="${DRY_RUN:-0}"

export GIT_TERMINAL_PROMPT=0

log()  { printf '\n[deploy] %s\n' "$*"; }
warn() { printf '[deploy] WARN: %s\n' "$*" >&2; }
die()  { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

trap 'printf "[deploy] FAILED at line %s\n" "$LINENO" >&2' ERR

run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf '+ '
        printf '%q ' "$@"
        printf '\n'
    else
        "$@"
    fi
}

[ -n "$PROJECT_PATH" ] || die "PROJECT_PATH не задан. Запустите скрипт из репозитория или укажите PROJECT_PATH=/path/to/project"
[ -d "$PROJECT_PATH" ] || die "каталог проекта не найден: $PROJECT_PATH"
[ -d "$PROJECT_PATH/.git" ] || die "это не git-репозиторий: $PROJECT_PATH"
[ -n "$SERVICE" ] || die "SERVICE не задан"

cd "$PROJECT_PATH"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no >&2 || true
    die "рабочее дерево содержит изменения в отслеживаемых файлах. Закоммитьте/уберите их на сервере."
fi

if [ -n "$(git status --porcelain --untracked-files=normal | grep '^??' || true)" ]; then
    warn "есть неотслеживаемые файлы — они не блокируют обновление"
fi

BEFORE_COMMIT="$(git rev-parse --short HEAD)"
BEFORE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
log "До обновления: $BEFORE_BRANCH @ $BEFORE_COMMIT"

if [ -n "$BRANCH" ]; then
    run git fetch --prune origin
    if [ "$BEFORE_BRANCH" != "$BRANCH" ]; then
        log "Переключение на ветку $BRANCH"
        run git checkout "$BRANCH"
    fi
    run git pull --ff-only origin "$BRANCH"
else
    run git pull --ff-only
fi

AFTER_COMMIT="$(git rev-parse --short HEAD)"
AFTER_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
log "После обновления: $AFTER_BRANCH @ $AFTER_COMMIT"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    if [ -z "$PYTHON_BIN" ]; then
        if [ -x "$PROJECT_PATH/venv/bin/python" ]; then
            PYTHON_BIN="$PROJECT_PATH/venv/bin/python"
        else
            PYTHON_BIN="python3"
        fi
    fi
    log "Миграции: $PYTHON_BIN scripts/setup_db.py --action create"
    run "$PYTHON_BIN" scripts/setup_db.py --action create
else
    log "Миграции пропущены"
fi

if [ "$SKIP_RESTART" = "1" ]; then
    log "Перезапуск сервиса пропущен"
else
    if [ "$USE_SUDO" = "1" ]; then
        SUDO=(sudo -n)
    else
        SUDO=()
    fi

    log "Перезапуск сервиса: $SERVICE"
    if [ "$DRY_RUN" = "1" ]; then
        printf '+ '
        printf '%q ' "${SUDO[@]}" systemctl restart "$SERVICE"
        printf '\n'
    else
        if ! "${SUDO[@]}" systemctl restart "$SERVICE"; then
            systemctl status "$SERVICE" --no-pager -l || true
            die "не удалось перезапустить $SERVICE"
        fi
        if ! "${SUDO[@]}" systemctl is-active "$SERVICE" >/dev/null; then
            systemctl status "$SERVICE" --no-pager -l || true
            die "сервис $SERVICE не активен после перезапуска"
        fi
        log "Сервис $SERVICE активен"
    fi
fi

if [ -n "$HEALTHCHECK_URL" ]; then
    log "Healthcheck: $HEALTHCHECK_URL"
    if [ "$DRY_RUN" = "1" ]; then
        printf '+ curl -fsS --max-time 2 %q\n' "$HEALTHCHECK_URL"
    else
        attempt=1
        while [ "$attempt" -le "$HEALTHCHECK_RETRIES" ]; do
            if curl -fsS --max-time 2 "$HEALTHCHECK_URL" >/dev/null 2>&1; then
                log "Healthcheck пройден (попытка $attempt)"
                break
            fi
            if [ "$attempt" -eq "$HEALTHCHECK_RETRIES" ]; then
                die "healthcheck не прошёл за ${HEALTHCHECK_RETRIES}с: $HEALTHCHECK_URL"
            fi
            sleep 1
            attempt=$((attempt + 1))
        done
    fi
fi

log "Готово: $AFTER_BRANCH @ $AFTER_COMMIT"
