#!/usr/bin/env python3
"""
Скрипт управления базой данных
"""
import sys
import argparse
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.exceptions.custom_exceptions import DatabaseError


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
        description='Управление базой данных шахматных партий',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Создать таблицу
  python scripts/setup_db.py --action create
  
  # Создать таблицу с удалением существующей
  python scripts/setup_db.py --action create --drop-table
  
  # Удалить таблицу
  python scripts/setup_db.py --action drop
  
  # Пересоздать таблицу
  python scripts/setup_db.py --action recreate
  
  # Показать статус
  python scripts/setup_db.py --action status --verbose
        """
    )
    
    parser.add_argument(
        '--action', '-a',
        choices=['create', 'drop', 'recreate', 'status'],
        required=True,
        help='Действие с таблицей'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['local', 'remote'],
        default='local',
        help='Режим подключения к БД (default: local)'
    )
    
    parser.add_argument(
        '--drop-table',
        action='store_true',
        help='Удалить существующую таблицу перед созданием'
    )
    
    parser.add_argument(
        '--config',
        default='config/app_config.yaml',
        help='Путь к файлу конфигурации'
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
        
        # Выполнение действия
        if args.action == 'create':
            logger.info("Создание таблицы...")
            if db_manager.create_table(drop_existing=args.drop_table):
                logger.info("✅ Таблица создана успешно")
            else:
                logger.error("❌ Ошибка создания таблицы")
                sys.exit(1)
                
        elif args.action == 'drop':
            if args.drop_table:  # Для безопасности, явно требуем флаг
                logger.info("Удаление таблицы...")
                if db_manager.drop_table():
                    logger.info("✅ Таблица удалена")
                else:
                    logger.error("❌ Ошибка удаления таблицы")
                    sys.exit(1)
            else:
                logger.error("❌ Для удаления таблицы используйте --drop-table")
                sys.exit(1)
                
        elif args.action == 'recreate':
            logger.info("Пересоздание таблицы...")
            if db_manager.drop_table() and db_manager.create_table(drop_existing=True):
                logger.info("✅ Таблица пересоздана")
            else:
                logger.error("❌ Ошибка пересоздания таблицы")
                sys.exit(1)
                
        elif args.action == 'status':
            logger.info("Получение статуса...")
            
            # Информация о схеме
            info = db_manager.get_table_info()
            print("\n📊 Информация о схеме:")
            print(f"  Название: {info['name']}")
            print(f"  Версия: {info['version']}")
            print(f"  Таблица: {info['table_name']}")
            print(f"  Колонок: {info['column_count']}")
            print(f"  Индексов: {info['index_count']}")
            
            # Статистика таблицы
            stats = db_manager.get_table_stats()
            print("\n📈 Статистика таблицы:")
            print(f"  Существует: {'✅' if stats['exists'] else '❌'}")
            
            if stats['exists']:
                print(f"  Всего записей: {stats.get('total_records', 0)}")
                if stats.get('first_game'):
                    print(f"  Первая игра: {stats['first_game']}")
                if stats.get('last_game'):
                    print(f"  Последняя игра: {stats['last_game']}")
                if stats.get('avg_accuracy'):
                    print(f"  Средняя точность: {stats['avg_accuracy']:.1f}%")
                if stats.get('unique_opponents'):
                    print(f"  Уникальных соперников: {stats['unique_opponents']}")
                
                if stats.get('results_distribution'):
                    print("\n  Распределение результатов:")
                    for result, count in stats['results_distribution']:
                        print(f"    {result}: {count}")
        
        db_manager.close()
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
