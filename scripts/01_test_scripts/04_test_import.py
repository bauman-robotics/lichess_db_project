#!/usr/bin/env python3
"""
Тестирование импорта игр
"""
import sys
from pathlib import Path
from datetime import datetime

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
    from core.database.db_manager import DatabaseManager
    print("✅ DatabaseManager загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта DatabaseManager: {e}")
    sys.exit(1)

try:
    from services.pgn_parser import PGNParser
    print("✅ PGNParser загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта PGNParser: {e}")
    sys.exit(1)

try:
    from services.import_manager import ImportManager
    print("✅ ImportManager загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта ImportManager: {e}")
    sys.exit(1)


def test_pgn_parser():
    """Тестируем PGN парсер"""
    print("\n🧪 Тестирование PGN парсера...")
    
    parser = PGNParser()
    
    # Тестовый PGN
    test_pgn = """[Event "Rated Blitz game"]
[Site "https://lichess.org/abc123def456"]
[Date "2024.01.15"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]
[WhiteElo "1500"]
[BlackElo "1450"]
[TimeControl "300+3"]
[Opening "Sicilian Defense"]
[LichessGameID "abc123def456"]
[WhiteAccuracy "85.5"]

1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 1-0
"""
    
    games = parser.parse_content(test_pgn, "Player1")
    
    print(f"✅ Распарсено игр: {len(games)}")
    
    if games:
        game = games[0]
        print(f"   ID: {game.game_id}")
        print(f"   Дата: {game.game_date}")
        print(f"   Цвет: {game.player_color}")
        print(f"   Результат: {game.result}")
        print(f"   Соперник: {game.opponent_name}")
        print(f"   Рейтинг игрока: {game.my_rating}")
        print(f"   Рейтинг соперника: {game.opponent_rating}")
        print(f"   Точность: {game.accuracy}")
        print(f"   Дебют: {game.opening_name}")
        print(f"   Ходов: {game.move_count}")
        return True
    
    return False


def test_import_manager():
    """Тестируем менеджер импорта"""
    print("\n🧪 Тестирование ImportManager...")
    
    try:
        config_loader = ConfigLoader()
        
        # Проверяем наличие секретов
        db_config = config_loader.get_db_config('local')
        if not db_config.get('user') or db_config.get('user') == 'not_set':
            print("⚠️  Секреты не настроены, пропускаем тест")
            print("   Для теста создайте config/secrets.yaml")
            return True
        
        db_manager = DatabaseManager(config_loader, 'local')
        import_manager = ImportManager(config_loader, db_manager)
        
        print("✅ ImportManager создан")
        print(f"   Режим импорта: {config_loader.get('import.default_mode')}")
        
        db_manager.close()
        return True
        
    except Exception as e:
        print(f"⚠️  Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return True


def main():
    print("=" * 50)
    print("🧪 Тестирование импорта")
    print("=" * 50)
    
    success = True
    
    if not test_pgn_parser():
        success = False
    
    if not test_import_manager():
        success = False
    
    if success:
        print("\n✅ Все проверки пройдены успешно!")
    else:
        print("\n❌ Есть ошибки, проверьте вывод выше.")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())