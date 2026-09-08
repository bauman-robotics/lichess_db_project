"""
Загрузчик конфигурации из YAML файлов
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union

from core.exceptions.custom_exceptions import ConfigError


class ConfigLoader:
    """
    Загрузчик и менеджер конфигурации
    
    Поддерживает:
    - Загрузку из YAML файлов
    - Переменные окружения (из os.environ)
    - Объединение конфигов
    """
    
    def __init__(self, app_config_path: str = None, secrets_path: str = None):
        """
        Инициализация загрузчика
        
        Args:
            app_config_path: Путь к файлу с общей конфигурацией
            secrets_path: Путь к файлу с секретами
        """
        self.logger = logging.getLogger(__name__)
        self.config: Dict[str, Any] = {}
        
        # Определяем пути по умолчанию
        base_dir = Path(__file__).parent.parent
        
        self.app_config_path = app_config_path or os.getenv(
            'APP_CONFIG', 
            str(base_dir / 'config' / 'app_config.yaml')
        )
        
        self.secrets_path = secrets_path or os.getenv(
            'SECRETS_CONFIG',
            str(base_dir / 'config' / 'secrets.yaml')
        )
        
        # Загружаем конфиги
        self._load_configs()
    
    def _load_configs(self) -> None:
        """Загружает все конфигурационные файлы"""
        # Загружаем основной конфиг
        if not os.path.exists(self.app_config_path):
            raise ConfigError(f"Файл конфигурации не найден: {self.app_config_path}")
        
        with open(self.app_config_path, 'r', encoding='utf-8') as f:
            app_config = yaml.safe_load(f)
            if app_config:
                self.config.update(app_config)
        
        self.logger.info(f"Загружен основной конфиг: {self.app_config_path}")
        
        # Загружаем секреты (если есть)
        if os.path.exists(self.secrets_path):
            with open(self.secrets_path, 'r', encoding='utf-8') as f:
                secrets = yaml.safe_load(f)
                if secrets:
                    # Добавляем секреты в конфиг с префиксом 'secrets'
                    self.config['secrets'] = secrets
                    self.logger.info(f"Загружены секреты: {self.secrets_path}")
        else:
            self.logger.warning(f"Файл секретов не найден: {self.secrets_path}")
        
        # Переопределяем переменными окружения
        self._apply_env_overrides()
    
    def _apply_env_overrides(self) -> None:
        """Применяет переменные окружения для переопределения конфига"""
        env_mappings = {
            'DB_MODE': ('database', 'mode'),
            'DB_NAME': ('database', 'db_name'),
            'LOG_LEVEL': ('app', 'log_level'),
            'IMPORT_MODE': ('import', 'default_mode'),
            'LICHESS_USERNAME': ('lichess', 'username'),
        }
        
        for env_var, path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested_value(path, value)
                self.logger.debug(f"Переопределено {env_var} = {value}")
    
    def _set_nested_value(self, path: tuple, value: Any) -> None:
        """Устанавливает значение по вложенному пути"""
        current = self.config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    def get(self, key: str, default: Any = None, use_secrets: bool = True) -> Any:
        """
        Получает значение по ключу с поддержкой вложенности (через точки)
        
        Примеры:
            config.get('database.db_name')
            config.get('secrets.local.password')
        
        Args:
            key: Ключ с разделителями '.'
            default: Значение по умолчанию
            use_secrets: Использовать секреты
        """
        keys = key.split('.')
        
        # Если запрос начинается с 'secrets' и секреты загружены
        if keys[0] == 'secrets' and use_secrets:
            if 'secrets' not in self.config:
                return default
            current = self.config['secrets']
            keys = keys[1:]
        else:
            current = self.config
        
        try:
            for k in keys:
                if isinstance(current, dict) and k in current:
                    current = current[k]
                else:
                    return default
            return current
        except (KeyError, TypeError):
            return default
    
    def get_db_config(self, mode: str = 'local') -> Dict[str, Any]:
        """
        Получает конфигурацию для подключения к БД
        
        Args:
            mode: 'local' или 'remote'
        """
        if mode == 'remote':
            db_config = self.get('secrets.remote.database', {})
            ssh_config = self.get('secrets.remote.ssh', {})
            return {
                **db_config,
                'ssh': ssh_config,
                'mode': 'remote'
            }
        else:
            db_config = self.get('secrets.local', {})
            return {
                **db_config,
                'mode': 'local'
            }
    
    def get_schema_path(self) -> str:
        """Возвращает путь к файлу схемы"""
        schema_path = self.get('database.schema_path')
        if schema_path:
            return schema_path
        
        # Путь по умолчанию
        base_dir = Path(__file__).parent.parent
        return str(base_dir / 'config' / 'schemas' / 'v1_lichess_games.yaml')
    
    def get_import_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию импорта"""
        return self.get('import', {})
    
    def get_database_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию базы данных"""
        return self.get('database', {})
    
    def set(self, key: str, value: Any) -> None:
        """Устанавливает значение в конфиг (в runtime)"""
        keys = key.split('.')
        current = self.config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
    
    def merge(self, other_config: Dict[str, Any]) -> None:
        """Объединяет с другим конфигом (рекурсивно)"""
        def deep_merge(base: Dict, override: Dict) -> Dict:
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    base[key] = deep_merge(base[key], value)
                else:
                    base[key] = value
            return base
        
        self.config = deep_merge(self.config, other_config)
    
    def to_dict(self) -> Dict[str, Any]:
        """Возвращает полный конфиг"""
        return self.config.copy()
    
    def print_config(self, show_secrets: bool = False) -> None:
        """Выводит конфигурацию в консоль"""
        if show_secrets:
            config = self.config
        else:
            # Скрываем секреты
            config = self.config.copy()
            if 'secrets' in config:
                config['secrets'] = '*** HIDDEN ***'
        
        print(yaml.dump(config, default_flow_style=False, allow_unicode=True))