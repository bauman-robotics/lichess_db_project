"""
Менеджер импорта игр из различных источников
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from datetime import datetime

from services.pgn_parser import PGNParser
from services.lichess_client import LichessClient
from core.models.game import Game
from core.database.db_manager import DatabaseManager
from core.exceptions.custom_exceptions import ImportError, ValidationError


class ImportMode(Enum):
    """Режимы импорта"""
    FILE = "file"
    API = "api"


class ImportManager:
    """
    Менеджер импорта игр из PGN файлов или Lichess API
    """
    
    def __init__(self, config_loader, db_manager: DatabaseManager):
        """
        Инициализация менеджера импорта
        
        Args:
            config_loader: Загруженный конфиг
            db_manager: Менеджер БД
        """
        self.logger = logging.getLogger(__name__)
        self.config_loader = config_loader
        self.db_manager = db_manager
        
        self.parser = PGNParser()
        self.lichess_client = LichessClient(config_loader)
        
        self.import_config = config_loader.get_import_config()
        self.username = config_loader.get('secrets.lichess.username')
    
    def import_from_file(
        self,
        file_path: str,
        player_name: Optional[str] = None,
        delete_after_import: bool = False
    ) -> Dict[str, Any]:
        """
        Импортирует игры из PGN файла
        
        Args:
            file_path: Путь к PGN файлу
            player_name: Имя игрока (если не указан, берется из конфига)
            delete_after_import: Удалить файл после успешного импорта
            
        Returns:
            Dict: Статистика импорта
        """
        if not os.path.exists(file_path):
            raise ImportError(f"Файл не найден: {file_path}")
        
        player_name = player_name or self.username
        if not player_name:
            raise ImportError("Имя игрока не указано")
        
        self.logger.info(f"Начинаю импорт из файла: {file_path}")
        
        # Парсим PGN
        try:
            games = self.parser.parse_file(file_path, player_name)
        except Exception as e:
            raise ImportError(f"Ошибка парсинга PGN: {e}")
        
        if not games:
            self.logger.warning("Игры не найдены в файле")
            return {
                'total_parsed': 0,
                'valid_games': 0,
                'saved_games': 0,
                'errors': ['Игры не найдены'],
                'source': 'file',
                'source_path': file_path
            }
        
        # Сохраняем в БД
        saved_count = self.db_manager.insert_games(games)
        
        # Удаляем файл если нужно
        if delete_after_import and saved_count > 0:
            try:
                os.remove(file_path)
                self.logger.info(f"Файл удален: {file_path}")
            except Exception as e:
                self.logger.warning(f"Не удалось удалить файл: {e}")
        
        return {
            'total_parsed': len(games),
            'valid_games': len(games),
            'saved_games': saved_count,
            'errors': [],
            'source': 'file',
            'source_path': file_path
        }
    
    def import_from_api(
        self,
        username: Optional[str] = None,
        max_games: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        perf_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Импортирует игры через Lichess API
        
        Args:
            username: Имя пользователя
            max_games: Максимальное количество игр
            since: Дата начала (YYYY-MM-DD)
            until: Дата окончания (YYYY-MM-DD)
            perf_type: Тип игры
            
        Returns:
            Dict: Статистика импорта
        """
        username = username or self.username
        if not username:
            raise ImportError("Имя пользователя не указано")
        
        self.logger.info(f"Загрузка игр для {username} через API")
        
        # Загружаем PGN
        try:
            pgn_content = self.lichess_client.download_games(
                username=username,
                max_games=max_games,
                since=since,
                until=until,
                perf_type=perf_type
            )
        except Exception as e:
            raise ImportError(f"Ошибка загрузки из API: {e}")
        
        if not pgn_content:
            return {
                'total_parsed': 0,
                'valid_games': 0,
                'saved_games': 0,
                'errors': ['Нет данных от API'],
                'source': 'api',
                'username': username
            }
        
        # Сохраняем во временный файл
        temp_file = self._save_temp_pgn(pgn_content, username)
        
        # Импортируем из файла
        result = self.import_from_file(temp_file, username, delete_after_import=True)
        result['source'] = 'api'
        result['username'] = username
        
        return result
    
    def _save_temp_pgn(self, content: str, username: str) -> str:
        """
        Сохраняет PGN во временный файл
        
        Args:
            content: PGN контент
            username: Имя пользователя
            
        Returns:
            str: Путь к сохраненному файлу
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"lichess_{username}_{timestamp}.pgn"
        
        # Используем директорию из конфига или по умолчанию
        data_dir = self.config_loader.get('app.data_dir', 'data')
        download_dir = Path(data_dir) / 'downloads'
        download_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = download_dir / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.info(f"PGN сохранен в {file_path}")
        return str(file_path)
    
    def choose_import_source(
        self,
        file_path: Optional[str] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Интеллектуальный выбор источника импорта
        
        Приоритет:
        1. Явно указанный file_path
        2. Явно указанный username (API)
        3. Настройки из конфига
        """
        if file_path:
            if os.path.exists(file_path):
                self.logger.info(f"Использован указанный файл: {file_path}")
                return {'mode': ImportMode.FILE, 'path': file_path}
            else:
                raise ImportError(f"Файл не найден: {file_path}")
        
        if username:
            self.logger.info(f"Использован указанный username для API: {username}")
            return {'mode': ImportMode.API, 'username': username}
        
        # Проверяем конфиг
        default_mode = self.import_config.get('default_mode', 'file')
        
        if default_mode == 'api':
            username = self.username
            if not username:
                raise ImportError("Username не указан в конфиге для API режима")
            return {'mode': ImportMode.API, 'username': username}
        else:
            file_path = self.import_config.get('file', {}).get('default_path')
            if not file_path or not os.path.exists(file_path):
                raise ImportError(f"Файл не найден: {file_path}")
            return {'mode': ImportMode.FILE, 'path': file_path}
    
    def get_import_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику импорта
        
        Returns:
            Dict: Статистика
        """
        return {
            'total_games': self.db_manager.get_table_stats().get('total_records', 0),
            'last_import': None,  # Можно добавить логирование времени
            'source': self.import_config.get('default_mode', 'file')
        }