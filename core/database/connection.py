"""
Модуль для управления подключением к базе данных
Поддерживает локальное и удаленное подключение через SSH
"""
import logging
from contextlib import contextmanager
from typing import Optional, Generator, Dict, Any

import psycopg2
from psycopg2 import extras
from psycopg2.extensions import connection as PsycopgConnection

try:
    import paramiko
    from sshtunnel import SSHTunnelForwarder
    SSH_AVAILABLE = True
except ImportError:
    SSH_AVAILABLE = False

from core.exceptions.custom_exceptions import ConnectionError


class DatabaseConnection:
    """
    Управление подключением к PostgreSQL
    Поддерживает локальные и удаленные подключения (через SSH туннель)
    """
    
    def __init__(self, config: Dict[str, Any], mode: str = 'local'):
        """
        Инициализация подключения
        
        Args:
            config: Конфигурация подключения
            mode: 'local' или 'remote'
        """
        self.logger = logging.getLogger(__name__)
        self.mode = mode
        self.config = config
        self.connection: Optional[PsycopgConnection] = None
        self.tunnel: Optional[SSHTunnelForwarder] = None
        
    def connect(self) -> PsycopgConnection:
        """
        Устанавливает подключение к БД
        
        Returns:
            PsycopgConnection: Активное подключение
            
        Raises:
            ConnectionError: Если не удалось подключиться
        """
        if self.connection and not self.connection.closed:
            return self.connection
        
        try:
            if self.mode == 'remote':
                self.connection = self._connect_remote()
            else:
                self.connection = self._connect_local()
            
            self.logger.info(f"Подключение к БД установлено (режим: {self.mode})")
            return self.connection
            
        except Exception as e:
            raise ConnectionError(f"Ошибка подключения к БД: {e}")
    
    def _connect_local(self) -> PsycopgConnection:
        """Подключение к локальной БД"""
        db_config = self.config
        
        # Параметры подключения
        conn_params = {
            'host': db_config.get('host', 'localhost'),
            'port': db_config.get('port', 5432),
            'user': db_config.get('user'),
            'password': db_config.get('password'),
            'dbname': db_config.get('db_name', 'postgres'),
            'sslmode': db_config.get('sslmode', 'disable')
        }
        
        self.logger.debug(f"Подключение к {conn_params['host']}:{conn_params['port']}")
        
        try:
            return psycopg2.connect(**conn_params)
        except Exception as e:
            raise ConnectionError(f"Ошибка подключения к локальной БД: {e}")
    
    def _connect_remote(self) -> PsycopgConnection:
        """Подключение к удаленной БД через SSH туннель"""
        if not SSH_AVAILABLE:
            raise ConnectionError("Модули paramiko/sshtunnel не установлены")
        
        db_config = self.config.get('database', {})
        ssh_config = self.config.get('ssh', {})
        
        # Параметры SSH
        ssh_params = {
            'ssh_address_or_host': (ssh_config.get('host'), ssh_config.get('port', 22)),
            'ssh_username': ssh_config.get('user'),
            'ssh_pkey': self._get_ssh_key(ssh_config.get('key_path')),
            'ssh_password': ssh_config.get('key_password'),
            'remote_bind_address': (db_config.get('host'), db_config.get('port', 5432)),
            'local_bind_address': ('localhost', 0),  # Динамический порт
        }
        
        # Удаляем None значения
        ssh_params = {k: v for k, v in ssh_params.items() if v is not None}
        
        self.logger.info(f"Создание SSH туннеля к {ssh_config.get('host')}")
        
        try:
            self.tunnel = SSHTunnelForwarder(**ssh_params)
            self.tunnel.start()
            
            # Подключаемся через локальный порт туннеля
            conn_params = {
                'host': 'localhost',
                'port': self.tunnel.local_bind_port,
                'user': db_config.get('user'),
                'password': db_config.get('password'),
                'dbname': db_config.get('db_name', 'postgres'),
                'sslmode': db_config.get('sslmode', 'disable')
            }
            
            return psycopg2.connect(**conn_params)
            
        except Exception as e:
            if self.tunnel:
                self.tunnel.stop()
            raise ConnectionError(f"Ошибка SSH подключения: {e}")
    
    def _get_ssh_key(self, key_path: str):
        """Загружает SSH ключ"""
        if not key_path:
            return None
        
        # Расширяем ~ в путь
        key_path = os.path.expanduser(key_path)
        
        if not os.path.exists(key_path):
            self.logger.warning(f"SSH ключ не найден: {key_path}")
            return None
        
        try:
            return paramiko.RSAKey.from_private_key_file(key_path)
        except Exception as e:
            self.logger.warning(f"Не удалось загрузить ключ: {e}")
            return None
    
    @contextmanager
    def get_connection(self) -> Generator[PsycopgConnection, None, None]:
        """
        Контекстный менеджер для работы с подключением
        
        Использование:
            with db_conn.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM table")
        """
        conn = self.connect()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            # Не закрываем подключение здесь, чтобы можно было использовать повторно
            pass
    
    @contextmanager
    def get_cursor(self, cursor_factory=None) -> Generator:
        """
        Контекстный менеджер для работы с курсором
        
        Использование:
            with db_conn.get_cursor() as cur:
                cur.execute("SELECT * FROM table")
        """
        conn = self.connect()
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def disconnect(self) -> None:
        """Закрывает подключение и SSH туннель"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.logger.info("Подключение к БД закрыто")
        
        if self.tunnel and self.tunnel.is_active:
            self.tunnel.stop()
            self.logger.info("SSH туннель закрыт")
    
    def is_connected(self) -> bool:
        """Проверяет, активно ли подключение"""
        return (self.connection is not None and 
                not self.connection.closed)
    
    def test_connection(self) -> bool:
        """Тестирует подключение простым запросом"""
        try:
            with self.get_cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                return result is not None and result[0] == 1
        except Exception as e:
            self.logger.error(f"Ошибка тестирования подключения: {e}")
            return False
    
    def __enter__(self):
        """Вход в контекстный менеджер"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        self.disconnect()


# Добавляем os для работы с путями
import os