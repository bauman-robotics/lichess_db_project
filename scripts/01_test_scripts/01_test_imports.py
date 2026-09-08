#!/usr/bin/env python3
"""
Временный скрипт для проверки импортов
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
# scripts/test_scripts/ -> scripts/ -> project_root/
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"📁 Project root: {project_root}")

try:
    from core.exceptions.custom_exceptions import ConfigError, ValidationError
    print("✅ Исключения загружены")
except ImportError as e:
    print(f"❌ Ошибка импорта исключений: {e}")
    sys.exit(1)

try:
    from core.models.game import Game
    print("✅ Модель Game загружена")
except ImportError as e:
    print(f"❌ Ошибка импорта Game: {e}")
    sys.exit(1)

try:
    from config.config_loader import ConfigLoader
    print("✅ ConfigLoader загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта ConfigLoader: {e}")
    sys.exit(1)


def test_game_model():
    """Тестируем модель Game"""
    print("\n🧪 Тестирование модели Game...")
    
    from datetime import datetime
    
    try:
        game = Game(
            game_id="test123",
            game_date=datetime.now(),
            time_control="5+3",
            player_color="white",
            result="Win",
            move_count=45,
            opponent_name="TestPlayer",
            my_rating=1500,
            opponent_rating=1450,
            accuracy=85.5,
            opening_name="Sicilian Defense"
        )
        
        print(f"✅ Игра создана: {game}")
        print(f"   Словарь: {game.to_dict()}")
        print(f"   PGN хэш: {game.get_pgn_hash()}")
        
        # Проверяем валидацию
        try:
            invalid_game = Game(
                game_id="test456",
                game_date=datetime.now(),
                time_control="5+3",
                player_color="white",
                result="Win",
                move_count=-5,  # Неверное значение
                opponent_name="TestPlayer",
                my_rating=1500,
                opponent_rating=1450
            )
            print("❌ Валидация не сработала для отрицательного move_count")
            return False
        except ValidationError as e:
            print(f"✅ Валидация сработала: {e}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_loader():
    """Тестируем загрузчик конфигурации"""
    print("\n🧪 Тестирование ConfigLoader...")
    
    try:
        loader = ConfigLoader()
        
        db_name = loader.get('database.db_name')
        print(f"✅ Имя БД: {db_name}")
        
        import_mode = loader.get('import.default_mode')
        print(f"✅ Режим импорта: {import_mode}")
        
        # Проверяем секреты (если есть)
        local_user = loader.get('secrets.local.user', default='not_set')
        print(f"✅ Пользователь БД: {local_user}")
        
        # Проверяем путь к схеме
        schema_path = loader.get_schema_path()
        print(f"✅ Путь к схеме: {schema_path}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 50)
    print("🚀 Проверка базовых модулей")
    print("=" * 50)
    
    success = True
    
    if not test_game_model():
        success = False
    
    if not test_config_loader():
        success = False
    
    if success:
        print("\n✅ Все проверки пройдены успешно!")
    else:
        print("\n❌ Есть ошибки, проверьте вывод выше.")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())