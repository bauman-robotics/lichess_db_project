"""
Клиент для работы с Lichess API
"""
import requests
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlencode

from core.exceptions.custom_exceptions import LichessAPIError


class LichessClient:
    """
    Клиент для загрузки игр с Lichess API
    """
    
    def __init__(self, config_loader):
        """
        Инициализация клиента
        
        Args:
            config_loader: Загруженный конфиг
        """
        self.logger = logging.getLogger(__name__)
        self.config = config_loader.get_import_config().get('api', {})
        
        self.base_url = self.config.get('base_url', 'https://lichess.org/api')
        self.timeout = self.config.get('timeout', 60)
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 2)
        
        # API токен
        self.api_token = config_loader.get('secrets.lichess.api_token')
        self.username = config_loader.get('secrets.lichess.username')
        
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Создает сессию с заголовками"""
        session = requests.Session()
        
        headers = {
            'User-Agent': 'lichess_db_manager/1.0',
            'Accept': 'application/x-chess-pgn'
        }
        
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        
        session.headers.update(headers)
        return session
    
    def download_games(
        self,
        username: Optional[str] = None,
        max_games: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        perf_type: Optional[str] = None
    ) -> str:
        """
        Скачивает игры пользователя в формате PGN
        
        Args:
            username: Имя пользователя (если не указан, используется из конфига)
            max_games: Максимальное количество игр
            since: Дата начала (YYYY-MM-DD)
            until: Дата окончания (YYYY-MM-DD)
            perf_type: Тип игры (rapid, blitz, classical, etc.)
            
        Returns:
            str: PGN контент
            
        Raises:
            LichessAPIError: При ошибке загрузки
        """
        username = username or self.username
        if not username:
            raise LichessAPIError("Имя пользователя не указано")
        
        # Формируем URL
        url = f"{self.base_url}/games/user/{username}"
        
        # Параметры запроса
        params = {
            'format': self.config.get('export_format', 'pgn'),
            'pgnInJson': False,
            'clocks': True,
            'evals': True,
            'accuracy': True,
            'opening': True,
            'tags': True,
            'moves': True,
        }
        
        # Добавляем параметры из конфига
        config_params = self.config.get('params', {})
        params.update(config_params)
        
        # Переопределяем параметры
        if max_games:
            params['max'] = max_games
        if since:
            params['since'] = self._parse_date(since)
        if until:
            params['until'] = self._parse_date(until)
        if perf_type:
            params['perfType'] = perf_type
        
        # Удаляем None значения
        params = {k: v for k, v in params.items() if v is not None}
        
        self.logger.info(f"Загрузка игр для {username} с параметрами: {params}")
        
        # Выполняем запрос с ретраями
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    stream=True
                )
                
                if response.status_code == 200:
                    content = response.text
                    self.logger.info(f"Загружено {content.count('[Event ')} игр")
                    return content
                
                elif response.status_code == 429:
                    # Too Many Requests
                    retry_after = int(response.headers.get('Retry-After', 60))
                    self.logger.warning(f"Превышен лимит запросов. Ожидание {retry_after} сек...")
                    time.sleep(retry_after)
                    
                else:
                    error_msg = f"Ошибка API: {response.status_code} - {response.text}"
                    self.logger.error(error_msg)
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    else:
                        raise LichessAPIError(error_msg)
                        
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Ошибка запроса (попытка {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise LichessAPIError(f"Ошибка запроса: {e}")
        
        raise LichessAPIError("Не удалось загрузить игры после нескольких попыток")
    
    def _parse_date(self, date_str: str) -> int:
        """
        Преобразует дату в timestamp для API
        
        Args:
            date_str: Дата в формате YYYY-MM-DD
            
        Returns:
            int: Timestamp в миллисекундах
        """
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return int(dt.timestamp() * 1000)
        except ValueError:
            self.logger.warning(f"Неверный формат даты: {date_str}")
            return 0
    
    def get_game_by_id(self, game_id: str, format: str = 'pgn') -> str:
        """
        Загружает конкретную игру по ID
        
        Args:
            game_id: ID игры на Lichess
            format: Формат ('pgn' или 'json')
            
        Returns:
            str: Данные игры в указанном формате
        """
        url = f"{self.base_url}/game/{game_id}"
        
        params = {'format': format}
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.text
            else:
                raise LichessAPIError(
                    f"Ошибка загрузки игры {game_id}: {response.status_code}"
                )
                
        except requests.exceptions.RequestException as e:
            raise LichessAPIError(f"Ошибка запроса: {e}")
    
    def get_player_info(self, username: str) -> Dict[str, Any]:
        """
        Получает информацию о пользователе
        
        Args:
            username: Имя пользователя
            
        Returns:
            Dict: Информация о пользователе
        """
        url = f"{self.base_url}/user/{username}"
        
        try:
            response = self.session.get(
                url,
                headers={'Accept': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"Ошибка получения информации: {response.status_code}")
                return {}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ошибка запроса: {e}")
            return {}