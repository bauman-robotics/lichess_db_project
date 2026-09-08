"""
Модель данных для шахматной партии
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import hashlib
import json

from core.exceptions.custom_exceptions import ValidationError


@dataclass
class Game:
    """
    Модель шахматной партии с Lichess
    
    Attributes:
        game_id: Уникальный ID игры на Lichess
        game_date: Дата и время проведения партии
        time_control: Контроль времени (например, "5+3")
        player_color: Цвет фигур игрока ("white" или "black")
        result: Результат ("Win", "Loss", "Draw")
        accuracy: Точность игры (0-100)
        move_count: Количество ходов
        opening_name: Название дебюта
        opponent_name: Имя соперника
        my_rating: Рейтинг игрока
        opponent_rating: Рейтинг соперника
        opponent_games_count: Количество игр у соперника
        game_analysis: Текстовый разбор партии
        game_url: Ссылка на игру
        pgn_moves: Полная PGN нотация
        import_source: Источник импорта
        created_at: Время создания записи
        updated_at: Время обновления записи
    """
    
    # Обязательные поля
    game_id: str
    game_date: datetime
    time_control: str
    player_color: str
    result: str
    move_count: int
    opponent_name: str
    my_rating: int
    opponent_rating: int
    
    # Опциональные поля
    accuracy: Optional[float] = None
    opening_name: Optional[str] = None
    opponent_games_count: Optional[int] = None
    game_analysis: Optional[str] = None
    game_url: Optional[str] = None
    pgn_moves: Optional[str] = None
    import_source: str = "api"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Валидация данных после инициализации"""
        self._validate()
        self._normalize()
    
    def _validate(self) -> None:
        """Базовая валидация полей"""
        if self.accuracy is not None and not (0 <= self.accuracy <= 100):
            raise ValidationError(
                f"Точность должна быть от 0 до 100, получено: {self.accuracy}"
            )
        
        if self.move_count <= 0:
            raise ValidationError(
                f"Количество ходов должно быть положительным: {self.move_count}"
            )
        
        if self.my_rating < 0 or self.opponent_rating < 0:
            raise ValidationError("Рейтинги не могут быть отрицательными")
        
        if self.player_color not in ['white', 'black']:
            raise ValidationError(f"Неверный цвет: {self.player_color}")
        
        if self.result not in ['Win', 'Loss', 'Draw']:
            raise ValidationError(f"Неверный результат: {self.result}")
    
    def _normalize(self) -> None:
        """Нормализация полей"""
        # Приводим строки к единому формату
        self.player_color = self.player_color.lower()
        self.opponent_name = self.opponent_name.strip()
        if self.opening_name:
            self.opening_name = self.opening_name.strip()
    
    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """
        Конвертирует объект в словарь для БД
        
        Args:
            exclude_none: Исключать None значения
        """
        result = {
            'game_id': self.game_id,
            'game_date': self.game_date,
            'time_control': self.time_control,
            'player_color': self.player_color,
            'result': self.result,
            'move_count': self.move_count,
            'opponent_name': self.opponent_name,
            'my_rating': self.my_rating,
            'opponent_rating': self.opponent_rating,
            'accuracy': self.accuracy,
            'opening_name': self.opening_name,
            'opponent_games_count': self.opponent_games_count,
            'game_analysis': self.game_analysis,
            'game_url': self.game_url,
            'pgn_moves': self.pgn_moves,
            'import_source': self.import_source,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        
        if exclude_none:
            return {k: v for k, v in result.items() if v is not None}
        return result
    
    def to_json(self) -> str:
        """Конвертирует объект в JSON строку"""
        def datetime_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        
        return json.dumps(
            self.to_dict(exclude_none=False), 
            default=datetime_serializer, 
            indent=2
        )
    
    def get_pgn_hash(self) -> str:
        """Вычисляет хэш PGN для проверки дубликатов"""
        if self.pgn_moves:
            return hashlib.sha256(self.pgn_moves.encode()).hexdigest()
        return hashlib.sha256(f"{self.game_id}{self.game_date}".encode()).hexdigest()
    
    def is_duplicate(self, other: 'Game') -> bool:
        """Проверяет, является ли игра дубликатом другой"""
        if not isinstance(other, Game):
            return False
        return self.game_id == other.game_id or self.get_pgn_hash() == other.get_pgn_hash()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Game':
        """Создаёт объект из словаря"""
        # Обработка даты
        if 'game_date' in data and isinstance(data['game_date'], str):
            data['game_date'] = datetime.fromisoformat(data['game_date'])
        
        return cls(**data)
    
    def __repr__(self) -> str:
        return (
            f"Game(id={self.game_id}, date={self.game_date.date()}, "
            f"{self.player_color} vs {self.opponent_name}, {self.result})"
        )