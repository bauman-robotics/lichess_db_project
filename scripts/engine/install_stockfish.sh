#!/usr/bin/env bash
# Установка Stockfish из репозитория Ubuntu/Debian.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Запустите от root: sudo bash $0" >&2
    exit 1
fi

echo "== Проверка ресурсов =="
free -h || true
df -h / || true

if command -v stockfish >/dev/null 2>&1; then
    echo "Stockfish уже установлен: $(command -v stockfish)"
else
    echo "== apt-get update =="
    apt-get update
    echo "== Установка stockfish =="
    DEBIAN_FRONTEND=noninteractive apt-get install -y stockfish
fi

BIN="$(command -v stockfish || true)"
if [[ -z "${BIN}" && -x /usr/games/stockfish ]]; then
    BIN=/usr/games/stockfish
fi
if [[ -z "${BIN}" || ! -x "${BIN}" ]]; then
    echo "Не найден бинарник stockfish" >&2
    exit 1
fi

echo "Бинарник: ${BIN}"
"${BIN}" <<'UCI'
uci
setoption name Hash value 16
setoption name Threads value 1
position startpos moves e2e4 e7e5
go depth 10
quit
UCI

echo "Готово."
