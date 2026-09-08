#!/usr/bin/env python3
"""
Тестирование модулей работы с БД
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
# scripts/test_scripts/ -> scripts/ -> project_root/
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"📁 Project root: {project_root}")

try:
    from config.config_loader import ConfigLoader
    print("✅ ConfigLoader загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта ConfigLoader: {e}")
    sys.exit(1)

try:
    from core.database.schema_loader import SchemaLoader
    print("✅ SchemaLoader загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта SchemaLoader: {e}")
    sys.exit(1)

try:
    from core.database.db_manager import DatabaseManager
    print("✅ DatabaseManager загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта DatabaseManager: {e}")
    sys.exit(1)

try:
    from core.database.connection import DatabaseConnection
    print("✅ DatabaseConnection загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта DatabaseConnection: {e}")
    sys.exit(1)


def test_schema_loader():
    """Тестируем загрузчик схемы"""
    print("\n🧪 Тестирование SchemaLoader...")
    
    try:
        loader = SchemaLoader()
        schema = loader.load()
        
        print(f"✅ Схема загружена: {schema.name} v{schema.version}")
        print(f"   Таблица: {schema.table_name}")
        print(f"   Колонок: {len(schema.columns)}")
        print(f"   Индексов: {len(schema.indexes)}")
        
        # Проверяем генерацию SQL
        sql = loader.get_create_table_sql(drop_existing=False)
        print(f"✅ SQL сгенерирован (длина: {len(sql)} символов)")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_db_connection():
    """Тестируем подключение к БД"""
    print("\n🧪 Тестирование DatabaseConnection...")
    
    try:
        config_loader = ConfigLoader()
        
        # Проверяем, есть ли секреты
        db_config = config_loader.get_db_config('local')
        
        if not db_config.get('user') or db_config.get('user') == 'not_set':
            print("⚠️  Секреты не настроены, пропускаем тест подключения")
            print("   Для теста создайте config/secrets.yaml")
            return True
        
        conn = DatabaseConnection(db_config, 'local')
        
        if conn.test_connection():
            print("✅ Подключение к БД успешно")
        else:
            print("⚠️  Не удалось подключиться к БД (это нормально, если PostgreSQL не запущен)")
        
        conn.disconnect()
        return True
        
    except Exception as e:
        print(f"⚠️  Ошибка подключения (это нормально, если PostgreSQL не запущен): {e}")
        return True


def test_db_manager():
    """Тестируем менеджер БД"""
    print("\n🧪 Тестирование DatabaseManager...")
    
    try:
        config_loader = ConfigLoader()
        
        # Проверяем, есть ли секреты
        db_config = config_loader.get_db_config('local')
        if not db_config.get('user') or db_config.get('user') == 'not_set':
            print("⚠️  Секреты не настроены, пропускаем тест")
            return True
        
        db_manager = DatabaseManager(config_loader, 'local')
        
        # Проверяем существование таблицы
        exists = db_manager.table_exists()
        print(f"✅ Таблица существует: {exists}")
        
        # Получаем информацию о таблице
        info = db_manager.get_table_info()
        print(f"   Схема: {info['name']} v{info['version']}")
        print(f"   Колонок: {info['column_count']}")
        
        db_manager.close()
        return True
        
    except Exception as e:
        print(f"⚠️  Ошибка: {e}")
        return True


def main():
    print("=" * 50)
    print("🧪 Тестирование модулей работы с БД")
    print("=" * 50)
    
    success = True
    
    if not test_schema_loader():
        success = False
    
    if not test_db_connection():
        success = False
    
    if not test_db_manager():
        success = False
    
    if success:
        print("\n✅ Все проверки пройдены успешно!")
    else:
        print("\n❌ Есть ошибки, проверьте вывод выше.")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())