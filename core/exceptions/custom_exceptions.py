# Исключения проекта
"""
Кастомные исключения для проекта
"""

class ProjectError(Exception):
    """Базовое исключение проекта"""
    pass

class ConfigError(ProjectError):
    """Ошибка конфигурации"""
    pass

class DatabaseError(ProjectError):
    """Ошибка базы данных"""
    pass

class ConnectionError(DatabaseError):
    """Ошибка подключения к БД"""
    pass

class SchemaError(ProjectError):
    """Ошибка схемы таблицы"""
    pass

class ValidationError(ProjectError):
    """Ошибка валидации данных"""
    pass

class ImportError(ProjectError):
    """Ошибка импорта данных"""
    pass

class PGNParseError(ImportError):
    """Ошибка парсинга PGN"""
    pass

class LichessAPIError(ImportError):
    """Ошибка API Lichess"""
    pass

class DuplicateGameError(ValidationError):
    """Дубликат игры"""
    pass

class TableNotFoundError(DatabaseError):
    """Таблица не найдена"""
    pass