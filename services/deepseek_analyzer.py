#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для анализа шахматных партий через DeepSeek.

Поддерживает три режима (deepseek.mode в app_config.yaml):

  • bridge   — Post-Bridge (обёртка над chat.deepseek.com, бесплатно).
  • api      — официальный api.deepseek.com (платно, ключ в secrets.yaml).
  • disabled — DeepSeek не вызывается, analyze_game() бросает DeepSeekError.

Синхронный вызов: analyze_game() блокируется до получения ответа
или таймаута. Вызывать её нужно из фонового потока, чтобы не блокировать
Flask-воркер.
"""
import re
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
import requests


logger = logging.getLogger(__name__)


# ============================================================
# КОНФИГ (значения по умолчанию, если что-то не задано)
# ============================================================

DEFAULT_MODEL         = "deepseek-chat"
DEFAULT_TIMEOUT       = 90
DEFAULT_HEALTH_TO     = 3
DEFAULT_MAX_TOKENS    = 2000
DEFAULT_TEMPERATURE   = 0.7

DEFAULT_BRIDGE_URL    = "http://localhost:8001/v1/chat/completions"
DEFAULT_BRIDGE_HEALTH = "http://localhost:8001/v1/models"
DEFAULT_API_URL       = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_API_HEALTH    = "https://api.deepseek.com/v1/models"

VALID_MODES = ("bridge", "api", "disabled")

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
# ЧТЕНИЕ КОНФИГА
# ============================================================

def _load_config():
    """Возвращает ConfigLoader. Ленивая загрузка, чтобы не тянуть
    конфиг при импорте модуля в тестах."""
    from config.config_loader import ConfigLoader
    return ConfigLoader()


def _get_deepseek_config() -> Dict:
    """
    Читает актуальные настройки DeepSeek из app_config.yaml + secrets.yaml.

    Возвращает dict:
        {
            'mode':        'bridge' | 'api' | 'disabled',
            'url':         str,        # endpoint /chat/completions (None при disabled)
            'healthz':     str,        # endpoint /models (None при disabled)
            'api_key':     str | None, # Bearer для режима api
            'model':       str,
            'temperature': float,
            'max_tokens':  int,
            'timeout':     int,
            'thinking':    bool,
            'search':      bool,
        }

    Raises:
        DeepSeekError — если выбран режим api, но ключ не задан.
    """
    cfg = _load_config()

    mode = (cfg.get('deepseek.mode', 'bridge') or 'bridge').lower()
    if mode not in VALID_MODES:
        logger.warning(f"Неизвестный deepseek.mode='{mode}', используется 'bridge'")
        mode = 'bridge'

    model       = cfg.get('deepseek.model', DEFAULT_MODEL)
    temperature = float(cfg.get('deepseek.temperature', DEFAULT_TEMPERATURE))
    max_tokens  = int(cfg.get('deepseek.max_tokens', DEFAULT_MAX_TOKENS))
    timeout     = int(cfg.get('deepseek.timeout', DEFAULT_TIMEOUT))

    result = {
        'mode':        mode,
        'url':         None,
        'healthz':     None,
        'api_key':     None,
        'model':       model,
        'temperature': temperature,
        'max_tokens':  max_tokens,
        'timeout':     timeout,
        'thinking':    bool(cfg.get('deepseek.thinking', False)),
        'search':      bool(cfg.get('deepseek.search', False)),
    }

    if mode == 'disabled':
        return result

    if mode == 'bridge':
        result['url']     = cfg.get('deepseek.bridge.url', DEFAULT_BRIDGE_URL)
        result['healthz'] = cfg.get('deepseek.bridge.healthz', DEFAULT_BRIDGE_HEALTH)
        return result

    # mode == 'api'
    result['url']     = cfg.get('deepseek.api.url', DEFAULT_API_URL)
    result['healthz'] = cfg.get('deepseek.api.healthz', DEFAULT_API_HEALTH)

    api_key = (
        cfg.get('secrets.deepseek.api_key')
        or cfg.get('deepseek.api_key')
        or ''
    ).strip()

    if not api_key:
        raise DeepSeekError(
            "Режим deepseek.mode='api', но api_key не задан. "
            "Добавьте deepseek.api_key в config/secrets.yaml"
        )

    result['api_key'] = api_key
    return result


# ============================================================
# ПРОВЕРКА ДОСТУПНОСТИ
# ============================================================

def check_health() -> bool:
    """
    Проверяет доступность DeepSeek в текущем режиме.

    Returns:
        True  — если endpoint /models отвечает 200.
        False — в любом другом случае (включая mode='disabled').
    """
    try:
        cfg = _get_deepseek_config()
    except DeepSeekError as e:
        logger.warning(f"DeepSeek health-check: конфиг невалиден: {e}")
        return False

    if cfg['mode'] == 'disabled':
        return False

    try:
        headers = {}
        if cfg['api_key']:
            headers['Authorization'] = f"Bearer {cfg['api_key']}"

        r = requests.get(
            cfg['healthz'],
            headers=headers,
            timeout=DEFAULT_HEALTH_TO,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(
            f"DeepSeek health-check failed ({cfg['mode']}, {cfg['healthz']}): {e}"
        )
        return False


# ============================================================
# ПРОМПТ
# ============================================================

def load_prompts() -> Dict[str, str]:
    """
    Загружает промпты из config/deepseek_prompts.yaml.

    Возвращает {'system': str, 'user_template': str}.
    """
    if not PROMPTS_FILE.exists():
        raise DeepSeekError(f"Файл промптов не найден: {PROMPTS_FILE}")

    try:
        with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise DeepSeekError(f"Ошибка чтения {PROMPTS_FILE}: {e}")

    prompt_key = "game_analysis"
    try:
        cfg = _load_config()
        prompt_key = cfg.get('deepseek.prompt_key', 'game_analysis') or 'game_analysis'
    except Exception:
        pass

    if not data or prompt_key not in data:
        raise DeepSeekError(
            f"В {PROMPTS_FILE} нет секции '{prompt_key}'. "
            f"Проверьте deepseek.prompt_key в app_config.yaml"
        )

    section = data[prompt_key]
    if 'system' not in section or 'user_template' not in section:
        raise DeepSeekError(
            f"В секции '{prompt_key}' должны быть ключи 'system' и 'user_template'"
        )

    return {
        'system':        section['system'],
        'user_template': section['user_template'],
    }


# ============================================================
# ОЧИСТКА PGN
# ============================================================

def strip_clk(pgn: str) -> str:
    """
    Убирает [%clk ...] из PGN, оставляя [%eval ...].
    """
    return re.sub(r'\s*\[%clk[^\]]*\]\s*', ' ', pgn).strip()


def clean_pgn(pgn: str) -> str:
    """
    Убирает {...} из PGN и лишние номера ходов.
    Формат: "1. d4 d5 2. c4 Nf6 3. cxd5 ..."
    """
    pgn = re.sub(r'\s*\{[^}]*\}\s*', ' ', pgn)
    pgn = re.sub(r'(\d+)\.\.\.\s*', ' ', pgn)
    pgn = re.sub(r'\s+', ' ', pgn)
    return pgn.strip()


# ============================================================
# ФОРМИРОВАНИЕ ПРОМПТА
# ============================================================

def build_prompt(game: Dict, prompts: Dict[str, str], player_name: str) -> Tuple[str, str]:
    """
    Формирует system и user промпты.

    Returns:
        (system, user) — обе строки.
    """
    system = prompts['system'].strip()

    opening         = game.get('opening_name')   or '—'
    opponent_rating = game.get('opponent_rating') or '?'
    time_control    = game.get('time_control')   or '—'
    move_count      = game.get('move_count')     or 0

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
    Отправляет запрос в DeepSeek (bridge или api) и возвращает текст ответа.

    Raises:
        DeepSeekError — при любой ошибке.
    """
    cfg = _get_deepseek_config()

    if cfg['mode'] == 'disabled':
        raise DeepSeekError("DeepSeek отключён (deepseek.mode='disabled')")

    payload = {
        "model": cfg['model'],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": cfg['temperature'],
        "max_tokens":  cfg['max_tokens'],
    }

    headers = {"Content-Type": "application/json"}
    if cfg['api_key']:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    t0 = time.time()
    try:
        r = requests.post(
            cfg['url'],
            json=payload,
            headers=headers,
            timeout=cfg['timeout'],
        )
    except requests.exceptions.Timeout:
        raise DeepSeekError(f"Таймаут {cfg['timeout']} сек (mode={cfg['mode']})")
    except requests.exceptions.ConnectionError as e:
        raise DeepSeekError(
            f"Нет соединения с DeepSeek (mode={cfg['mode']}, url={cfg['url']}): {e}"
        )
    except requests.exceptions.RequestException as e:
        raise DeepSeekError(f"Ошибка запроса (mode={cfg['mode']}): {e}")

    elapsed = time.time() - t0

    if r.status_code != 200:
        msg = f"HTTP {r.status_code} (mode={cfg['mode']})"
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
        f"DeepSeek [{cfg['mode']}] ответил за {elapsed:.1f} сек, "
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

    Raises:
        DeepSeekUnavailable — если DeepSeek недоступен.
        DeepSeekError — при любой другой ошибке.
    """
    cfg = _get_deepseek_config()

    if cfg['mode'] == 'disabled':
        raise DeepSeekError("DeepSeek отключён (deepseek.mode='disabled')")

    if not check_health():
        raise DeepSeekUnavailable(
            f"DeepSeek API недоступен (mode={cfg['mode']}, url={cfg['url']})"
        )

    prompts = load_prompts()
    system, user = build_prompt(game, prompts, player_name)

    logger.info(
        f"Анализ партии {game.get('game_id')} для {player_name} "
        f"[mode={cfg['mode']}, model={cfg['model']}]: "
        f"system={len(system)} символов, user={len(user)} символов"
    )

    return _call_deepseek(system, user)