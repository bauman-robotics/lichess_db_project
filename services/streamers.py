"""
Курируемый список шахматных стримеров.

Список хранится в config/streamers.yaml, а статус «загружен»
определяется наличием таблицы games_<username>.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from core.utils.lichess import LichessUsernameError, normalize_lichess_username, player_table_name

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "streamers.yaml"


def load_streamer_config(path: Optional[Path] = None) -> dict:
    """Читает и валидирует config/streamers.yaml."""
    config_path = Path(path) if path else DEFAULT_CONFIG
    if not config_path.exists():
        logger.warning("Список стримеров не найден: %s", config_path)
        return {"default_limit": 300, "streamers": []}

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("Не удалось прочитать %s: %s", config_path, e)
        return {"default_limit": 300, "streamers": []}

    default_limit = data.get("default_limit", 300)
    try:
        default_limit = max(1, int(default_limit))
    except (TypeError, ValueError):
        default_limit = 300

    streamers = []
    seen = set()
    for entry in data.get("streamers", []) or []:
        if not isinstance(entry, dict) or entry.get("enabled", True) is False:
            continue
        raw_username = entry.get("username")
        try:
            username = normalize_lichess_username(raw_username)
        except LichessUsernameError as e:
            logger.warning("Пропущен стример %r: %s", raw_username, e)
            continue

        table_name = player_table_name(username)
        if table_name in seen:
            logger.warning("Дубликат стримера: %s", username)
            continue
        seen.add(table_name)

        try:
            limit = int(entry.get("limit") or default_limit)
        except (TypeError, ValueError):
            limit = default_limit
        limit = max(1, limit)

        streamers.append({
            "username": username,
            "table_name": table_name,
            "name": str(entry.get("name") or username).strip(),
            "title": str(entry.get("title") or "").strip(),
            "limit": limit,
            "url": f"https://lichess.org/@/{username}",
        })

    return {"default_limit": default_limit, "streamers": streamers}


def streamer_table_names(path: Optional[Path] = None) -> set:
    return {item["table_name"] for item in load_streamer_config(path)["streamers"]}


def get_streamer_cards(known_players: list, path: Optional[Path] = None) -> list:
    """Сопоставляет список из YAML с уже загруженными игроками."""
    loaded = {player["table_name"]: player for player in known_players}
    cards = []
    for streamer in load_streamer_config(path)["streamers"]:
        player = loaded.get(streamer["table_name"])
        cards.append({
            **streamer,
            "loaded": bool(player),
            "games": player["games"] if player else 0,
            "last_game": player["last_game"] if player else None,
        })
    return cards
