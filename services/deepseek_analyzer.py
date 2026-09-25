#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для анализа шахматных партий через DeepSeek.

Синхронный вызов: функция analyze_game() блокируется до получения ответа
или таймаута. Вызывать её нужно из фонового потока, чтобы не блокировать
Flask-воркер.

Пример:
    from services.deepseek_analyzer import analyze_game, DeepSeekError
    try:
        analysis = analyze_game(game_dict, player_name="DenNedelin")
    except DeepSeekError as e:
        print(f"Ошибка: {e}")
"""
import re
import time
import logging
from pathlib import Path
from typing import Dict, Optional

import yaml
import requests


logger = logging.getLogger(__name__)


# ============================================================
# КОНФИГ
# ============================================================

DEEPSEEK_URL      = "http://localhost:8001/v1/chat/completions"
DEEPSEEK_HEALTH   = "http://localhost:8001/healthz"
DEEPSEEK_MODEL    = "deepseek-chat"
DEEPSEEK_TIMEOUT  = 90          # секунд
DEEPSEEK_HEALTH_TIMEOUT = 3     # секунд
MAX_TOKENS        = 2000
TEMPERATURE       = 0.7

PROMPTS_FILE = Path(__file__).parent.parent / 'config' / 'deepseek_prompts.yaml'


# ============================================================
# ИСКЛЮЧЕНИЯ
# ============================================================

class DeepSeekError(Exception):
    """Ошибка при работе с DeepSeek (сеть, API, ответ)."""
    pass


class DeepSeekUnavailable(DeepSeekError):
    """DeepSeek API недоступен (healthz не отвечает)."""
    pass


# ============================================================
# ПРОВЕРКА ДОСТУПНОСТИ
# ============================================================

def check_health() -> bool:
    """
    Проверяет доступность DeepSeek-прокси.

    Returns:
        True, если /healthz отвечает 200.
        False в любом другом случае.
    """
    try:
        r = requests.get(DEEPSEEK_HEALTH, timeout=DEEPSEEK_HEALTH_TIMEOUT)
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"DeepSeek health-check failed: {e}")
        return False


# ============================================================
# ПРОМПТ
# ============================================================

def load_prompts() -> Dict[str, str]:
    """
    Загружает промпты из config/deepseek_prompts.yaml.

    Returns:
        Словарь с ключами 'system' и 'user_template'.

    Raises:
        DeepSeekError, если файл отсутствует или повреждён.
    """
    if not PROMPTS_FILE.exists():
        raise DeepSeekError(f"Файл промптов не найден: {PROMPTS_FILE}")

    try:
        with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise DeepSeekError(f"Ошибка чтения {PROMPTS_FILE}: {e}")

    if not data or 'game_analysis' not in data:
        raise DeepSeekError(f"В {PROMPTS_FILE} нет секции 'game_analysis'")

    section = data['game_analysis']
    if 'system' not in section or 'user_template' not in section:
        raise DeepSeekError(
            f"В {PROMPTS_FILE} должны быть ключи 'system' и 'user_template'"
        )

    return {
        'system': section['system'],
        'user_template': section['user_template'],
    }


# ============================================================
# ОЧИСТКА PGN
# ============================================================

def strip_clk(pgn: str) -> str:
    """
    Убирает [%clk ...] из PGN, оставляя [%eval ...].

    Пример:
        "1. d4 { [%eval 0.15] [%clk 0:15:00] } 1... d5 { [%eval 0.27] }"
        → "1. d4 { [%eval 0.15] } 1... d5 { [%eval 0.27] }"
    """
    return re.sub(r'\s*\[%clk[^\]]*\]\s*', ' ', pgn).strip()


def clean_pgn(pgn: str) -> str:
    """
    Убирает все {...} из PGN — для показа в модалке.
    """
    return re.sub(r'\s*\{[^}]*\}\s*', ' ', pgn).strip()


# ============================================================
# ФОРМИРОВАНИЕ ПРОМПТА
# ============================================================

def build_prompt(game: Dict, prompts: Dict[str, str], player_name: str) -> tuple:
    """
    Формирует system и user промпты.

    Args:
        game: словарь с полями game_date, color, opponent_name,
              opponent_rating, result, opening_name, time_control,
              move_count, pgn_moves.
        prompts: словарь из load_prompts().
        player_name: имя игрока.

    Returns:
        (system, user) — обе строки.
    """
    system = prompts['system'].strip()

    # Опциональные поля могут быть None
    opening = game.get('opening_name') or '—'
    opponent_rating = game.get('opponent_rating') or '?'
    time_control = game.get('time_control') or '—'
    move_count = game.get('move_count') or 0

    user = prompts['user_template'].format(
        player_name=player_name,
        player_color=game.get('color', '?'),
        opponent_name=game.get('opponent_name', '?'),
        opponent_rating=opponent_rating,
        result=game.get('result', '?'),
        opening_name=opening,
        time_control=time_control,
        move_count=move_count,
        pgn=strip_clk(game.get('pgn_moves', '')),
    ).strip()

    return system, user


# ============================================================
# ВЫЗОВ DEEPSEEK
# ============================================================

def _call_deepseek(system: str, user: str) -> str:
    """
    Отправляет запрос в DeepSeek и возвращает текст ответа.

    Raises:
        DeepSeekError — при любой ошибке.
    """
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    t0 = time.time()
    try:
        r = requests.post(
            DEEPSEEK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=DEEPSEEK_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise DeepSeekError(f"Таймаут {DEEPSEEK_TIMEOUT} сек")
    except requests.exceptions.ConnectionError as e:
        raise DeepSeekError(f"Нет соединения с DeepSeek: {e}")
    except requests.exceptions.RequestException as e:
        raise DeepSeekError(f"Ошибка запроса: {e}")

    elapsed = time.time() - t0

    if r.status_code != 200:
        # Пытаемся извлечь текст ошибки из JSON
        msg = f"HTTP {r.status_code}"
        try:
            body = r.json()
            if isinstance(body, dict):
                err = body.get('error') or body.get('detail') or body
                if isinstance(err, dict):
                    err = err.get('message', str(err))
                msg += f": {err}"
            else:
                msg += f": {body}"
        except Exception:
            msg += f": {r.text[:200]}"
        raise DeepSeekError(msg)

    try:
        data = r.json()
    except Exception as e:
        raise DeepSeekError(f"Не удалось распарсить ответ: {e}")

    if 'choices' not in data or not data['choices']:
        raise DeepSeekError("DeepSeek вернул пустой ответ (нет choices)")

    content = data['choices'][0].get('message', {}).get('content', '')
    if not content or not content.strip():
        raise DeepSeekError("DeepSeek вернул пустой текст")

    usage = data.get('usage', {})
    logger.info(
        f"DeepSeek ответил за {elapsed:.1f} сек, "
        f"токены: prompt={usage.get('prompt_tokens', 0)}, "
        f"completion={usage.get('completion_tokens', 0)}, "
        f"total={usage.get('total_tokens', 0)}"
    )

    return content.strip()


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def analyze_game(game: Dict, player_name: str) -> str:
    """
    Синхронно анализирует партию через DeepSeek.

    Args:
        game: словарь с данными партии (см. build_prompt).
        player_name: имя игрока.

    Returns:
        Текст разбора от DeepSeek.

    Raises:
        DeepSeekUnavailable — если DeepSeek недоступен.
        DeepSeekError — при любой другой ошибке.
    """
    if not check_health():
        raise DeepSeekUnavailable("DeepSeek API недоступен")

    prompts = load_prompts()
    system, user = build_prompt(game, prompts, player_name)

    logger.info(
        f"Анализ партии {game.get('game_id')} для {player_name}: "
        f"system={len(system)} символов, user={len(user)} символов"
    )

    return _call_deepseek(system, user)