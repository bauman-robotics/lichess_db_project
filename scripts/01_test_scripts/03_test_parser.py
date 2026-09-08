#!/usr/bin/env python3
"""
Тестирование PGN парсера
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
# scripts/test_scripts/ -> scripts/ -> project_root/
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"📁 Project root: {project_root}")

try:
    from services.pgn_parser import PGNParser
    print("✅ PGNParser загружен")
except ImportError as e:
    print(f"❌ Ошибка импорта PGNParser: {e}")
    sys.exit(1)


def test_parser():
    """Тестируем парсер на примере"""
    print("\n🧪 Тестирование PGN парсера...")
    
    parser = PGNParser()
    
    # Создаем тестовый PGN
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
        print(f"   Точность: {game.accuracy}")
        print(f"   Дебют: {game.opening_name}")
        print(f"   Ходов: {game.move_count}")
        
        # Проверяем валидацию
        print("\n✅ Все данные валидны")
    else:
        print("❌ Не удалось распарсить игры")
        return False
    
    return True


def main():
    print("=" * 50)
    print("🧪 Тестирование PGN парсера")
    print("=" * 50)
    
    success = test_parser()
    
    if success:
        print("\n✅ Все проверки пройдены успешно!")
    else:
        print("\n❌ Есть ошибки, проверьте вывод выше.")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())