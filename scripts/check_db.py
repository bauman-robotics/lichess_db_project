#!/usr/bin/env python3
"""
Быстрая проверка подключения к БД
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.connection import DatabaseConnection

def main():
    print("🔄 Проверка подключения к PostgreSQL...")
    
    config_loader = ConfigLoader()
    db_config = config_loader.get_db_config('local')
    
    print(f"  Хост: {db_config.get('host')}")
    print(f"  Порт: {db_config.get('port')}")
    print(f"  Пользователь: {db_config.get('user')}")
    print(f"  Пароль: {'*' * len(db_config.get('password', ''))}")
    
    conn = DatabaseConnection(db_config, 'local')
    
    if conn.test_connection():
        print("✅ Подключение успешно!")
    else:
        print("❌ Не удалось подключиться")
        print("\nВозможные решения:")
        print("1. Убедитесь, что PostgreSQL запущен: sudo systemctl status postgresql")
        print("2. Проверьте пароль в config/secrets.yaml")
        print("3. Проверьте, что пользователь существует: sudo -u postgres psql -c '\\du'")
        
    conn.disconnect()

if __name__ == '__main__':
    main()