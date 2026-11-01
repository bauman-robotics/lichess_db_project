"""
Утилиты для работы с Lichess: имена игроков, категории контроля времени.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import unquote, urlparse

# Lichess: латиница, цифры, подчёркивание и дефис.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,30}$")
PROFILE_PATH_RE = re.compile(r"^/@/([A-Za-z0-9_-]{2,30})/?$")
LICHESS_HOSTS = {"lichess.org", "www.lichess.org"}


class LichessUsernameError(ValueError):
    """Невалидное имя игрока или ссылка на профиль."""


def normalize_lichess_username(raw: Optional[str]) -> str:
    """
    Приводит имя игрока или ссылку на профиль Lichess к чистому имени.

    Поддерживает:
      - DenNedelin
      - @DenNedelin
      - https://lichess.org/@/DenNedelin
      - http://lichess.org/@/DenNedelin/
      - lichess.org/@/DenNedelin?tab=games
    """
    if raw is None:
        raise LichessUsernameError("Введите имя игрока или ссылку на профиль")

    value = str(raw).strip()
    if not value:
        raise LichessUsernameError("Введите имя игрока или ссылку на профиль")

    if value.startswith("@"):
        value = value[1:].strip()

    lowered = value.lower()
    looks_like_url = "://" in value or "lichess.org" in lowered
    if looks_like_url:
        url = value if "://" in value else f"https://{value}"
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower().split(":", 1)[0]
        if host not in LICHESS_HOSTS:
            raise LichessUsernameError(
                "Это не ссылка на профиль Lichess. Ожидается https://lichess.org/@/Имя"
            )
        path = unquote(parsed.path or "")
        match = PROFILE_PATH_RE.fullmatch(path)
        if not match:
            raise LichessUsernameError(
                "В ссылке нет профиля игрока. Ожидается https://lichess.org/@/Имя"
            )
        value = match.group(1)

    if not USERNAME_RE.fullmatch(value):
        raise LichessUsernameError(
            "Недопустимые символы в имени. Разрешены латиница, цифры, _ и - (2-30 символов)"
        )

    return value


def player_table_name(username: str) -> str:
    """
    Безопасное имя таблицы игрока: games_<lower>, только [a-z0-9_].
    Ограничение PostgreSQL на длину идентификатора — 63 байта.
    """
    value = (username or "").strip().lower()
    safe = re.sub(r"[^a-z0-9_]", "_", value)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        safe = "unknown"
    return f"games_{safe}"[:63]


def safe_filename_part(value: str) -> str:
    """Безопасная часть имени файла (без слэшей и спецсимволов)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", (value or "").strip())
    return safe or "player"


def classify_time_control(time_control: Optional[str]) -> str:
    """
    Категория контроля времени по формуле Lichess: база + 40 * инкремент.

    Возвращает: bullet / blitz / rapid / classical / correspondence / other.
    """
    if not time_control:
        return "other"

    value = str(time_control).strip()
    if not value:
        return "other"
    if value == "-" or "day" in value.lower():
        return "correspondence"

    match = re.fullmatch(r"(\d+)\+(\d+)", value)
    if not match:
        return "other"

    estimated = int(match.group(1)) + 40 * int(match.group(2))
    if estimated < 180:
        return "bullet"
    if estimated < 480:
        return "blitz"
    if estimated < 1500:
        return "rapid"
    return "classical"


def time_control_speed_sql(column: str = "time_control") -> str:
    """
    SQL-выражение категории контроля, эквивалентное classify_time_control.
    Используется в фильтрах и прогресса без изменения схемы БД.
    """
    col = f'"{column}"'
    return f"""
        CASE
            WHEN {col} IS NULL OR {col} = '' THEN 'other'
            WHEN {col} = '-' OR {col} ILIKE '%day%' THEN 'correspondence'
            WHEN {col} ~ '^[0-9]+\\+[0-9]+$' THEN
                CASE
                    WHEN split_part({col},'+',1)::int
                       + 40 * split_part({col},'+',2)::int < 180  THEN 'bullet'
                    WHEN split_part({col},'+',1)::int
                       + 40 * split_part({col},'+',2)::int < 480  THEN 'blitz'
                    WHEN split_part({col},'+',1)::int
                       + 40 * split_part({col},'+',2)::int < 1500 THEN 'rapid'
                    ELSE 'classical'
                END
            ELSE 'other'
        END
    """


SPEED_LABELS = {
    "bullet": "Пуля",
    "blitz": "Блиц",
    "rapid": "Рапид",
    "classical": "Классика",
    "correspondence": "Переписка",
    "other": "Другое",
}
