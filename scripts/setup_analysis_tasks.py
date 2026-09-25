#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Создание таблицы analysis_tasks в БД lichess_games.

Идемпотентный скрипт: если таблица уже существует — ничего не делает,
только показывает статус.

Использование:
    python3 scripts/setup_analysis_tasks.py           # создать, если нет
    python3 scripts/setup_analysis_tasks.py --status  # только показать статус
    python3 scripts/setup_analysis_tasks.py --drop    # удалить таблицу (осторожно!)
    python3 scripts/setup_analysis_tasks.py --recreate  # пересоздать
"""
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('setup_analysis_tasks')


# ============================================================
# SQL
# ============================================================

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_tasks (
    task_id     TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    game_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    started_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    error       TEXT
);
"""

SQL_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS one_running_task
    ON analysis_tasks (status) WHERE status = 'running';
"""

SQL_CREATE_USERNAME_INDEX = """
CREATE INDEX IF NOT EXISTS idx_tasks_username_game
    ON analysis_tasks (username, game_id);
"""

SQL_DROP_TABLE = """
DROP TABLE IF EXISTS analysis_tasks CASCADE;
"""

SQL_CHECK_TABLE = """
SELECT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'analysis_tasks'
);
"""

SQL_TABLE_INFO = """
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'analysis_tasks'
ORDER BY ordinal_position;
"""

SQL_INDEXES_INFO = """
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'analysis_tasks';
"""

SQL_COUNT = "SELECT COUNT(*) FROM analysis_tasks;"

SQL_RUNNING = "SELECT COUNT(*) FROM analysis_tasks WHERE status = 'running';"


# ============================================================
# ФУНКЦИИ
# ============================================================

def table_exists(db: DatabaseManager) -> bool:
    """Проверяет, существует ли таблица"""
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(SQL_CHECK_TABLE)
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Ошибка проверки таблицы: {e}")
        return False


def create_table(db: DatabaseManager) -> bool:
    """Создаёт таблицу и индексы"""
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                logger.info("Создание таблицы analysis_tasks...")
                cur.execute(SQL_CREATE_TABLE)

                logger.info("Создание уникального индекса one_running_task...")
                cur.execute(SQL_CREATE_UNIQUE_INDEX)

                logger.info("Создание индекса idx_tasks_username_game...")
                cur.execute(SQL_CREATE_USERNAME_INDEX)

                conn.commit()

        logger.info("✅ Таблица analysis_tasks создана")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка создания таблицы: {e}")
        import traceback
        traceback.print_exc()
        return False


def drop_table(db: DatabaseManager) -> bool:
    """Удаляет таблицу"""
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                logger.warning("Удаление таблицы analysis_tasks...")
                cur.execute(SQL_DROP_TABLE)
                conn.commit()

        logger.info("✅ Таблица analysis_tasks удалена")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка удаления: {e}")
        return False


def show_status(db: DatabaseManager):
    """Показывает информацию о таблице"""
    print()
    print("=" * 70)
    print("📊 СТАТУС ТАБЛИЦЫ analysis_tasks")
    print("=" * 70)

    if not table_exists(db):
        print("❌ Таблица не существует")
        print()
        print("Создать: python3 scripts/setup_analysis_tasks.py")
        return

    print("✅ Таблица существует")
    print()

    # Колонки
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                print("📋 Колонки:")
                cur.execute(SQL_TABLE_INFO)
                for row in cur.fetchall():
                    nullable = "NULL" if row[2] == 'YES' else "NOT NULL"
                    print(f"   {row[0]:15s} {row[1]:20s} {nullable}")
                print()

                print("🔑 Индексы:")
                cur.execute(SQL_INDEXES_INFO)
                for row in cur.fetchall():
                    print(f"   {row[0]}")
                    # Показываем определение, но кратко
                    idx_def = row[1]
                    if len(idx_def) > 100:
                        idx_def = idx_def[:100] + "..."
                    print(f"      {idx_def}")
                print()

                print("📈 Данные:")
                cur.execute(SQL_COUNT)
                total = cur.fetchone()[0]
                cur.execute(SQL_RUNNING)
                running = cur.fetchone()[0]
                print(f"   Всего задач: {total}")
                print(f"   Running:     {running}")

                # Показываем последние 5 задач
                if total > 0:
                    print()
                    print("📋 Последние 5 задач:")
                    cur.execute("""
                        SELECT task_id, username, game_id, status, started_at, finished_at
                        FROM analysis_tasks
                        ORDER BY started_at DESC
                        LIMIT 5
                    """)
                    print(f"   {'task_id':10s} {'username':15s} {'game_id':12s} {'status':8s} {'started':19s}")
                    print(f"   {'-'*10} {'-'*15} {'-'*12} {'-'*8} {'-'*19}")
                    for row in cur.fetchall():
                        tid = row[0][:8] + '...' if len(row[0]) > 10 else row[0]
                        started = row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else '—'
                        print(f"   {tid:10s} {row[1]:15s} {row[2]:12s} {row[3]:8s} {started}")

    except Exception as e:
        logger.error(f"Ошибка чтения статуса: {e}")

    print()
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Управление таблицей analysis_tasks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 scripts/setup_analysis_tasks.py            # создать, если нет
  python3 scripts/setup_analysis_tasks.py --status   # только статус
  python3 scripts/setup_analysis_tasks.py --recreate # пересоздать
  python3 scripts/setup_analysis_tasks.py --drop     # удалить
        """
    )

    parser.add_argument('--status', action='store_true',
                        help='Только показать статус таблицы')
    parser.add_argument('--drop', action='store_true',
                        help='Удалить таблицу (осторожно!)')
    parser.add_argument('--recreate', action='store_true',
                        help='Пересоздать таблицу (drop + create)')
    parser.add_argument('--force', action='store_true',
                        help='Не спрашивать подтверждение при --drop и --recreate')

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("🛠️  УПРАВЛЕНИЕ ТАБЛИЦЕЙ analysis_tasks")
    print("=" * 70)

    # Подключение
    try:
        config = ConfigLoader()
        db = DatabaseManager(config, 'local')
        print(f"✅ Подключение к БД установлено")
        print(f"   База: {config.get('local.db_name', '?')}")
        print(f"   Пользователь: {config.get('local.user', '?')}")
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться к БД: {e}")
        sys.exit(1)

    try:
        # --status
        if args.status:
            show_status(db)
            return

        # --drop
        if args.drop:
            if not table_exists(db):
                print("ℹ️  Таблица не существует, удалять нечего")
                return

            if not args.force:
                print()
                print("⚠️  ВНИМАНИЕ: удаление таблицы analysis_tasks")
                print("    Все задачи будут потеряны.")
                answer = input("    Продолжить? (yes/no): ").strip().lower()
                if answer != 'yes':
                    print("Отменено")
                    return

            if drop_table(db):
                show_status(db)
            return

        # --recreate
        if args.recreate:
            if table_exists(db) and not args.force:
                print()
                print("⚠️  ВНИМАНИЕ: пересоздание таблицы analysis_tasks")
                print("    Все задачи будут потеряны.")
                answer = input("    Продолжить? (yes/no): ").strip().lower()
                if answer != 'yes':
                    print("Отменено")
                    return

            if table_exists(db):
                drop_table(db)

            if create_table(db):
                show_status(db)
            return

        # По умолчанию — создать, если нет
        if table_exists(db):
            print("ℹ️  Таблица уже существует, ничего не создаю")
            print("    Показать статус: --status")
            print("    Пересоздать:     --recreate")
            show_status(db)
        else:
            if create_table(db):
                show_status(db)
            else:
                sys.exit(1)

    finally:
        db.close()


if __name__ == '__main__':
    main()