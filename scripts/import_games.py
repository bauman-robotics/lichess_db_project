#!/usr/bin/env python3
"""
Скрипт импорта шахматных партий
"""
import sys
import argparse
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from services.import_manager import ImportManager
from core.exceptions.custom_exceptions import ImportError


def setup_logging(verbose: bool = False):
    """Настройка логирования"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Импорт шахматных партий в базу данных',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Импорт из файла
  python scripts/import_games.py --source file --path data/uploads/games.pgn
  
  # Импорт через API
  python scripts/import_games.py --source api --username your_lichess_name --limit 100
  
  # Использование настроек из конфига
  python scripts/import_games.py
        """
    )
    
    parser.add_argument(
        '--source', '-s',
        choices=['file', 'api', 'auto'],
        default='auto',
        help='Источник импорта (auto - из конфига)'
    )
    
    parser.add_argument(
        '--path', '-p',
        help='Путь к PGN файлу (для режима file)'
    )
    
    parser.add_argument(
        '--username', '-u',
        help='Имя пользователя Lichess (для режима api)'
    )
    
    parser.add_argument(
        '--player', '-P',
        help='Имя игрока (для определения результата)'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        help='Максимальное количество игр (для API)'
    )
    
    parser.add_argument(
        '--since',
        help='Дата начала YYYY-MM-DD (для API)'
    )
    
    parser.add_argument(
        '--until',
        help='Дата окончания YYYY-MM-DD (для API)'
    )
    
    parser.add_argument(
        '--perf-type',
        choices=['rapid', 'blitz', 'classical', 'bullet', 'puzzle'],
        help='Тип игры (для API)'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['local', 'remote'],
        default='local',
        help='Режим подключения к БД'
    )
    
    parser.add_argument(
        '--config',
        default='config/app_config.yaml',
        help='Путь к конфигурационному файлу'
    )
    
    parser.add_argument(
        '--delete-after-import',
        action='store_true',
        help='Удалить PGN файл после импорта'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Подробный вывод'
    )
    
    args = parser.parse_args()
    
    logger = setup_logging(args.verbose)
    
    try:
        # Загрузка конфигурации
        logger.info("Загрузка конфигурации...")
        config_loader = ConfigLoader(args.config)
        
        # Инициализация менеджера БД
        logger.info(f"Подключение к БД (режим: {args.mode})...")
        db_manager = DatabaseManager(config_loader, args.mode)
        
        # Проверка существования таблицы
        if not db_manager.table_exists():
            logger.error("❌ Таблица не существует! Сначала создайте её:")
            logger.error("  python scripts/setup_db.py --action create")
            sys.exit(1)
        
        # Создание менеджера импорта
        import_manager = ImportManager(config_loader, db_manager)
        
        # Выбор источника импорта
        if args.source == 'auto':
            source_config = import_manager.choose_import_source(
                file_path=args.path,
                username=args.username
            )
        elif args.source == 'file':
            if not args.path:
                parser.error("Для режима 'file' укажите --path")
            source_config = {'mode': 'file', 'path': args.path}
        else:  # api
            if not args.username and not config_loader.get('secrets.lichess.username'):
                parser.error("Для режима 'api' укажите --username или настройте в secrets.yaml")
            source_config = {'mode': 'api', 'username': args.username}
        
        # Выполнение импорта
        logger.info("Начало импорта...")
        
        if source_config['mode'] == 'file':
            result = import_manager.import_from_file(
                file_path=source_config['path'],
                player_name=args.player,
                delete_after_import=args.delete_after_import
            )
        else:  # api
            result = import_manager.import_from_api(
                username=args.username or config_loader.get('secrets.lichess.username'),
                max_games=args.limit,
                since=args.since,
                until=args.until,
                perf_type=args.perf_type
            )
        
        # Вывод результатов
        print("\n" + "=" * 50)
        print("📊 Результаты импорта:")
        print(f"  Источник: {result['source']}")
        print(f"  Всего игр: {result['total_parsed']}")
        print(f"  Валидных: {result['valid_games']}")
        print(f"  Сохранено: {result['saved_games']}")
        
        if result.get('errors'):
            print(f"  Ошибок: {len(result['errors'])}")
            if args.verbose:
                for error in result['errors'][:5]:
                    print(f"    - {error}")
        
        print("=" * 50)
        
        # Показываем статистику таблицы
        stats = db_manager.get_table_stats()
        if stats.get('exists') and stats.get('total_records', 0) > 0:
            print(f"\n📈 Общая статистика:")
            print(f"  Всего игр в БД: {stats['total_records']}")
            if stats.get('avg_accuracy'):
                print(f"  Средняя точность: {stats['avg_accuracy']:.1f}%")
        
        db_manager.close()
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
