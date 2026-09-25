#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт: анализ партии через DeepSeek.
Берёт партию из БД, формирует промпт, отправляет в DeepSeek, выводит ответ.

Использование:
    python scripts/test_deepseek_analysis.py --username DenNedelin --game-id 0b43Lfb6
    python scripts/test_deepseek_analysis.py -u DenNedelin -g 0b43Lfb6 --save
"""
import sys
import re
import argparse
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import requests

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


DEEPSEEK_URL = "http://localhost:8001/v1/chat/completions"
DEEPSEEK_HEALTH = "http://localhost:8001/healthz"
DEEPSEEK_TIMEOUT = 90


def get_safe_table_name(username: str) -> str:
    safe = username.replace('-', '_').replace('.', '_')
    return f"games_{safe.lower()}"


def get_game_from_db(username: str, game_id: str) -> dict:
    """Достаёт партию из БД"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return None

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        game_id,
                        game_date,
                        player_color,
                        opponent_name,
                        opponent_rating,
                        result,
                        opening_name,
                        time_control,
                        move_count,
                        pgn_moves,
                        game_analysis
                    FROM {table_name}
                    WHERE game_id = %s;
                """, (game_id,))

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent_name': row[3],
                    'opponent_rating': row[4],
                    'result': row[5],
                    'opening_name': row[6],
                    'time_control': row[7],
                    'move_count': row[8],
                    'pgn_moves': row[9] or '',
                    'existing_analysis': row[10] or '',
                }
    finally:
        db.table_name = original_table
        db.close()


def load_prompts() -> dict:
    """Загружает промпты из config/deepseek_prompts.yaml"""
    path = Path(__file__).parent.parent / 'config' / 'deepseek_prompts.yaml'
    if not path.exists():
        raise FileNotFoundError(f"Файл промптов не найден: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if 'game_analysis' not in data:
        raise ValueError("В файле нет секции 'game_analysis'")

    return data['game_analysis']


def strip_clk(pgn: str) -> str:
    """Убирает [%clk ...] из PGN, оставляет [%eval ...]"""
    return re.sub(r'\s*\[%clk[^\]]*\]\s*', ' ', pgn).strip()


def build_prompt(game: dict, prompts: dict, player_name: str = "Игрок") -> tuple:
    """Формирует system и user промпты"""
    system = prompts['system'].strip()
    user = prompts['user_template'].format(
        player_name=player_name,
        player_color=game['color'],
        opponent_name=game['opponent_name'],
        opponent_rating=game['opponent_rating'],
        result=game['result'],
        opening_name=game['opening_name'] or '—',
        time_control=game['time_control'],
        move_count=game['move_count'],
        pgn=strip_clk(game['pgn_moves']),
    ).strip()
    return system, user


def check_health() -> bool:
    """Проверяет доступность DeepSeek"""
    try:
        r = requests.get(DEEPSEEK_HEALTH, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def call_deepseek(system: str, user: str) -> dict:
    """Отправляет запрос в DeepSeek"""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    t0 = time.time()
    r = requests.post(
        DEEPSEEK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=DEEPSEEK_TIMEOUT,
    )
    elapsed = time.time() - t0

    r.raise_for_status()
    return r.json(), elapsed


def save_analysis_to_db(username: str, game_id: str, analysis: str) -> bool:
    """Сохраняет ответ в game_analysis"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table_name} SET game_analysis = %s WHERE game_id = %s",
                    (analysis, game_id)
                )
                conn.commit()
        return True
    finally:
        db.table_name = original_table
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Тест анализа партии через DeepSeek')
    parser.add_argument('--username', '-u', required=True, help='Имя игрока')
    parser.add_argument('--game-id', '-g', required=True, help='ID партии')
    parser.add_argument('--save', action='store_true', help='Сохранить ответ в game_analysis')
    parser.add_argument('--show-prompt', action='store_true', help='Показать промпт')
    parser.add_argument('--existing', action='store_true', help='Использовать существующий анализ из БД')
    args = parser.parse_args()

    print("=" * 70)
    print("🧪 ТЕСТ АНАЛИЗА ПАРТИИ ЧЕРЕЗ DEEPSEEK")
    print("=" * 70)

    # 1. Проверка DeepSeek
    print("\n1️⃣  Проверка DeepSeek API...")
    if not check_health():
        print(f"❌ DeepSeek недоступен на {DEEPSEEK_HEALTH}")
        print("   Запустите: ./scripts/04_run_server_only.sh start")
        sys.exit(1)
    print("✅ DeepSeek API отвечает")

    # 2. Загрузка партии
    print("\n2️⃣  Загрузка партии из БД...")
    game = get_game_from_db(args.username, args.game_id)
    if not game:
        print(f"❌ Партия {args.game_id} не найдена у {args.username}")
        sys.exit(1)

    print(f"   📅 {game['date']}")
    print(f"   🎨 Цвет: {game['color']}")
    print(f"   👤 Соперник: {game['opponent_name']} ({game['opponent_rating']})")
    print(f"   🏆 Результат: {game['result']}")
    print(f"   📖 Дебют: {game['opening_name']}")
    print(f"   🔢 Ходов: {game['move_count']}")
    print(f"   📏 PGN: {len(game['pgn_moves'])} символов")

    # 3. Проверка существующего анализа
    if args.existing:
        if not game['existing_analysis']:
            print("\n❌ Существующего анализа нет")
            sys.exit(1)
        print("\n3️⃣  Существующий анализ из БД:")
        print("=" * 70)
        print(game['existing_analysis'])
        print("=" * 70)
        return

    if game['existing_analysis']:
        print(f"\n⚠️  В БД уже есть анализ ({len(game['existing_analysis'])} символов)")
        print("   Запускаю новый запрос, чтобы посмотреть свежий ответ")

    # 4. Формирование промпта
    print("\n3️⃣  Формирование промпта...")
    prompts = load_prompts()
    system, user = build_prompt(game, prompts, player_name=args.username)

    print(f"   System: {len(system)} символов")
    print(f"   User: {len(user)} символов")
    print(f"   PGN без [%clk]: {len(strip_clk(game['pgn_moves']))} символов")

    if args.show_prompt:
        print("\n" + "=" * 70)
        print("SYSTEM PROMPT:")
        print("=" * 70)
        print(system)
        print("\n" + "=" * 70)
        print("USER PROMPT:")
        print("=" * 70)
        print(user)
        print("=" * 70)

    # 5. Запрос в DeepSeek
    print(f"\n4️⃣  Отправка в DeepSeek (таймаут {DEEPSEEK_TIMEOUT} сек)...")
    print("   ⏳ Ждём ответа...")

    try:
        response, elapsed = call_deepseek(system, user)
    except requests.exceptions.Timeout:
        print(f"❌ Таймаут {DEEPSEEK_TIMEOUT} сек")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        sys.exit(1)

    print(f"✅ Ответ получен за {elapsed:.1f} сек")

    # 6. Извлечение ответа
    if 'choices' not in response or not response['choices']:
        print("❌ Пустой ответ от DeepSeek")
        print(json.dumps(response, indent=2, ensure_ascii=False)[:500])
        sys.exit(1)

    analysis = response['choices'][0]['message']['content']
    usage = response.get('usage', {})

    print(f"\n📊 Токены: prompt={usage.get('prompt_tokens', 0)}, "
          f"completion={usage.get('completion_tokens', 0)}, "
          f"total={usage.get('total_tokens', 0)}")

    # 7. Вывод ответа
    print("\n" + "=" * 70)
    print("📝 ОТВЕТ DEEPSEEK:")
    print("=" * 70)
    print(analysis)
    print("=" * 70)
    print(f"Длина ответа: {len(analysis)} символов")

    # 8. Сохранение
    if args.save:
        print("\n5️⃣  Сохранение в game_analysis...")
        if save_analysis_to_db(args.username, args.game_id, analysis):
            print("✅ Сохранено")
        else:
            print("❌ Ошибка сохранения")
    else:
        print("\n💡 Для сохранения запустите с флагом --save")


if __name__ == '__main__':
    main()