#!/usr/bin/env bash
#
# collect_bundle.sh — сбор контекста для нового чата по lichess_db_project.
#
# Запуск (из корня проекта):
#     bash docs/bundle/collect_bundle.sh
#
# Результат: docs/bundle/bundle.md
#
# НЕ включает: .env, config/secrets.yaml, *_punctuated.txt, cleaned/,
#              venv/, __pycache__.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

OUT="docs/bundle/bundle.md"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# --- helpers ---
section() {
    echo "" >> "$TMP"
    echo "---" >> "$TMP"
    echo "" >> "$TMP"
    echo "# $1" >> "$TMP"
    echo "" >> "$TMP"
}

code_block() {
    echo '```' >> "$TMP"
    cat >> "$TMP"
    echo '```' >> "$TMP"
}

# --- header ---
{
    echo "# lichess_db_project — контекст для нового чата"
    echo ""
    echo "**Дата:** $(date '+%Y-%m-%d %H:%M')"
    echo "**HEAD:** $(git rev-parse HEAD 2>/dev/null || echo 'нет git')"
    echo "**Ветка:** $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '—')"
    echo ""
    echo "**О проекте:** шахматный анализатор — PostgreSQL + Flask + DeepSeek."
    echo "Стек: Python 3.10+, psycopg2, Flask, python-chess, pyyaml, requests."
    echo "Взаимодействие с ассистентом: как в ai-coder — через скрипты (heredoc)."
} > "$TMP"

# --- git log ---
section "git log (последние 20)"
git log --oneline -20 2>/dev/null | code_block || echo "(нет git)" >> "$TMP"

# --- git status ---
section "git status"
git status --short 2>/dev/null | code_block || echo "(нет git)" >> "$TMP"

# --- CHANGELOG ---
if [ -f CHANGELOG.md ]; then
    section "CHANGELOG.md (последние 4 секции)"
    awk '/^## \[/{n++} n<=4' CHANGELOG.md | head -250 | code_block
fi

# --- TODO ---
if [ -f TODO.md ]; then
    section "TODO.md"
    head -150 TODO.md | code_block
fi

# --- README ---
if [ -f README.md ]; then
    section "README.md (первые 100 строк)"
    head -100 README.md | code_block
fi

# --- структура проекта ---
section "Структура проекта (без venv/.git)"
find . -type f \
    -not -path './.git/*' \
    -not -path './venv/*' \
    -not -path './.venv/*' \
    -not -path './__pycache__/*' \
    -not -path '*/__pycache__/*' \
    -not -path './.ai-out/*' \
    -not -path './logs/*' \
    -not -path './data/chess_transcripts/cleaned/*' \
    -not -name '*.bak*' \
    -not -name '*.pyc' \
    -not -name '.env' \
    -not -name 'secrets.yaml' \
    -not -name '*_punctuated.txt' \
    -not -name 'bundle.md' \
    | sort | head -200 | code_block

# --- структурная карта (class + def) ---
section "Структурная карта (class + def с номерами строк)"
{
    find . -name "*.py" \
        -not -path './venv/*' \
        -not -path './.venv/*' \
        -not -path '*/__pycache__/*' \
        -not -path './scripts/01_test_scripts/*' \
        | sort | while read -r f; do
            matches=$(grep -nE '^(class |def |async def )' "$f" 2>/dev/null || true)
            if [ -n "$matches" ]; then
                echo "## $f"
                echo "$matches"
                echo ""
            fi
        done
} | code_block

# --- config: app_config.yaml (без секретов) ---
if [ -f config/app_config.yaml ]; then
    section "config/app_config.yaml (без секретов)"
    grep -vE '^\s*(api_key|password|token|secret)' config/app_config.yaml \
        | head -150 | code_block
fi

# --- config: deepseek_prompts.yaml — список ключей и размеры ---
if [ -f config/deepseek_prompts.yaml ]; then
    section "config/deepseek_prompts.yaml — ключи промптов"
    {
        python3 - <<'PY' 2>/dev/null || true
import yaml
from pathlib import Path
d = yaml.safe_load(Path("config/deepseek_prompts.yaml").read_text(encoding="utf-8"))
if isinstance(d, dict):
    for k, v in d.items():
        system_len = len((v or {}).get("system", ""))
        user_len = len((v or {}).get("user_template", ""))
        print(f"  {k}: system={system_len} символов, user_template={user_len} символов")
PY
    } | code_block
fi

# --- схема БД ---
if [ -f config/schemas/v1_lichess_games.yaml ]; then
    section "config/schemas/v1_lichess_games.yaml (первые 120 строк)"
    head -120 config/schemas/v1_lichess_games.yaml | code_block
fi

# --- список таблиц (через venv, если есть) ---
section "Список таблиц в БД"
if [ -x venv/bin/python ]; then
    {
        venv/bin/python - <<'PY' 2>&1 || echo "(не удалось подключиться к БД)"
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
try:
    from config.config_loader import ConfigLoader
    from core.database.db_manager import DatabaseManager
    cfg = ConfigLoader()
    db = DatabaseManager(cfg, "local")
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name,
                       (SELECT COUNT(*) FROM information_schema.columns
                        WHERE table_name = t.table_name) AS cols
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            for name, cols in cur.fetchall():
                cur.execute(f'SELECT COUNT(*) FROM "{name}"')
                rows = cur.fetchone()[0]
                print(f"  {name}: {cols} колонок, {rows} записей")
except Exception as e:
    print(f"(ошибка: {e})")
PY
    } | code_block
else
    echo "(venv/bin/python не найден — пропущено)" >> "$TMP"
fi

# --- ключевые функции: сигнатуры ---
section "Ключевые модули — сигнатуры функций"
for f in services/deepseek_analyzer.py services/pgn_parser.py core/database/db_manager.py; do
    if [ -f "$f" ]; then
        echo "## $f"
        grep -nE '^(class |def )' "$f" 2>/dev/null || echo "  (нет)"
        echo ""
    fi
done | code_block

# --- requirements ---
if [ -f requirements.txt ]; then
    section "requirements.txt"
    cat requirements.txt | code_block
fi

# --- scripts ---
section "scripts/ — список файлов"
find scripts -maxdepth 2 -type f -name "*.py" 2>/dev/null | sort | code_block

# --- data/chess_transcripts ---
section "data/chess_transcripts — структура"
{
    echo "markers/: $(ls data/chess_transcripts/markers/ 2>/dev/null | wc -l) файлов"
    echo "style_guide.md: $(wc -l < data/chess_transcripts/style_guide.md 2>/dev/null || echo '?') строк"
    echo "cleaned/: $(ls data/chess_transcripts/cleaned/ 2>/dev/null | wc -l) файлов (gitignored)"
} | code_block

# --- последние ревью ---
if [ -d docs/reviews ]; then
    section "docs/reviews/ — последние файлы"
    ls -t docs/reviews/*.md 2>/dev/null | head -3 | while read -r f; do
        echo "## $f"
        echo ""
        head -80 "$f"
        echo ""
    done | code_block
fi

# --- финал ---
{
    echo ""
    echo "---"
    echo ""
    echo "**Промпт для ассистента:** см. \`docs/bundle/prompt.md\`"
    echo "**Сборщик:** \`docs/bundle/collect_bundle.sh\`"
} >> "$TMP"

# --- перемещаем в bundle.md ---
mv "$TMP" "$OUT"
echo "✓ Собрано: $OUT"
echo "  Строк: $(wc -l < "$OUT")"
echo "  Размер: $(du -h "$OUT" | cut -f1)"

# trap не сработает (файл перемещён)
trap - EXIT
