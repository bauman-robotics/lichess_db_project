#!/usr/bin/env python3
"""
Скачивание и анализ игр любого игрока Lichess
С поддержкой отдельных таблиц для разных игроков
"""
import sys
import argparse
from pathlib import Path
import re

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from services.lichess_client import LichessClient
from services.import_manager import ImportManager
from core.exceptions.custom_exceptions import ImportError


class PlayerGameAnalyzer:
    """Анализ игр другого игрока"""
    
    def __init__(self, username: str):
        self.username = username
        self.config = ConfigLoader()
        self.db = DatabaseManager(self.config, 'local')
        
        # Создаем имя таблицы для этого игрока
        self.table_name = f"games_{self.username.lower()}"
        
    def create_player_table(self) -> bool:
        """Создает таблицу для игрока на основе основной схемы"""
        print(f"\n📋 Создание таблицы для {self.username}...")
        
        try:
            # Получаем схему из основного менеджера
            schema_loader = self.db.schema_loader
            
            # Меняем имя таблицы в схеме
            schema = schema_loader.get_schema()
            schema.table_name = self.table_name
            
            # Генерируем SQL для создания таблицы
            sql = schema_loader.get_create_table_sql(drop_existing=True)
            
            # Выполняем SQL
            with self.db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    conn.commit()
            
            print(f"✅ Таблица {self.table_name} создана")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка создания таблицы: {e}")
            return False
    
    def import_games(self, pgn_content: str) -> dict:
        """Импортирует игры в таблицу игрока"""
        print(f"\n📥 Импорт игр {self.username}...")
        
        # Сохраняем PGN во временный файл
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/downloads/{self.username}_{timestamp}.pgn"
        
        Path("data/downloads").mkdir(parents=True, exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(pgn_content)
        
        # Создаем специальный менеджер импорта для этого игрока
        class TempImportManager:
            def __init__(self, db, player_name):
                self.db = db
                self.player_name = player_name
                self.parser = None  # Будет создан при импорте
            
        # Используем существующий ImportManager, но указываем другую таблицу
        import_manager = ImportManager(self.config, self.db)
        
        # Сохраняем оригинальное имя таблицы и подменяем
        original_table = self.db.table_name
        self.db.table_name = self.table_name
        
        try:
            result = import_manager.import_from_file(
                file_path=filename,
                player_name=self.username,
                delete_after_import=True
            )
            
            # Восстанавливаем имя таблицы
            self.db.table_name = original_table
            
            return result
            
        except Exception as e:
            self.db.table_name = original_table
            raise e
    
    def get_stats(self) -> dict:
        """Получает статистику по таблице игрока"""
        original_table = self.db.table_name
        self.db.table_name = self.table_name
        
        try:
            stats = self.db.get_table_stats()
            self.db.table_name = original_table
            return stats
        except Exception as e:
            self.db.table_name = original_table
            return {'exists': False, 'error': str(e)}
    
    def close(self):
        """Закрывает подключение к БД"""
        self.db.close()


def main():
    parser = argparse.ArgumentParser(description='Скачивание игр любого игрока Lichess')
    parser.add_argument('--username', '-u', required=True,
                       help='Имя пользователя Lichess')
    parser.add_argument('--limit', '-l', type=int, default=None,
                       help='Максимальное количество игр (по умолчанию ВСЕ игры)')
    parser.add_argument('--since', help='Дата начала (YYYY-MM-DD)')
    parser.add_argument('--until', help='Дата окончания (YYYY-MM-DD)')
    parser.add_argument('--perf-type', choices=['rapid', 'blitz', 'classical', 'bullet'],
                       help='Тип игры')
    parser.add_argument('--no-import', action='store_true',
                       help='Только скачать PGN, не импортировать в БД')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    limit_str = "ВСЕ" if args.limit is None else str(args.limit)
    print(f"\n📥 Загрузка игр пользователя: {args.username}")
    print(f"📊 Лимит: {limit_str}")
    print("=" * 50)
    
    try:
        config = ConfigLoader()
        
        # Создаем клиент Lichess без токена
        lichess_client = LichessClient(config)
        
        # Загружаем игры
        pgn_content = lichess_client.download_games(
            username=args.username,
            max_games=args.limit,
            since=args.since,
            until=args.until,
            perf_type=args.perf_type
        )
        
        if not pgn_content:
            print("❌ Не удалось загрузить игры")
            sys.exit(1)
        
        # Подсчитываем игры
        games_count = pgn_content.count('[Event ')
        print(f"📊 Загружено игр: {games_count}")
        
        if games_count == 0:
            print("⚠️ Игры не найдены")
            sys.exit(0)
        
        # Если не нужно импортировать, сохраняем только PGN
        if args.no_import:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"data/downloads/{args.username}_{timestamp}.pgn"
            Path("data/downloads").mkdir(parents=True, exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(pgn_content)
            
            print(f"✅ PGN сохранен: {filename}")
            sys.exit(0)
        
        # Импортируем в отдельную таблицу
        analyzer = PlayerGameAnalyzer(args.username)
        
        # Проверяем, существует ли таблица
        stats = analyzer.get_stats()
        
        if not stats.get('exists'):
            # Создаем таблицу
            if not analyzer.create_player_table():
                print("❌ Не удалось создать таблицу")
                sys.exit(1)
        
        # Импортируем игры
        result = analyzer.import_games(pgn_content)
        
        print(f"✅ Импортировано игр: {result['saved_games']}")
        if result.get('errors'):
            print(f"⚠️  Пропущено дубликатов: {games_count - result['saved_games']}")
        
        # Показываем статистику
        stats = analyzer.get_stats()
        print(f"\n📊 Статистика игр {args.username}:")
        print(f"  Всего игр в БД: {stats.get('total_records', 0)}")
        if stats.get('first_game'):
            print(f"  Первая игра: {stats['first_game']}")
        if stats.get('last_game'):
            print(f"  Последняя игра: {stats['last_game']}")
        if stats.get('avg_accuracy'):
            print(f"  Средняя точность: {stats['avg_accuracy']:.1f}%")
        
        analyzer.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()