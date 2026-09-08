"""
Менеджер базы данных
Управляет созданием, удалением и работой с таблицами
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from core.database.connection import DatabaseConnection
from core.database.schema_loader import SchemaLoader
from core.models.game import Game
from core.exceptions.custom_exceptions import DatabaseError, TableNotFoundError


class DatabaseManager:
    """
    Управление базой данных и таблицами
    """
    
    def __init__(self, config_loader, mode: str = 'local'):
        """
        Инициализация менеджера БД
        
        Args:
            config_loader: Загруженный конфиг
            mode: Режим подключения ('local' или 'remote')
        """
        self.logger = logging.getLogger(__name__)
        self.config_loader = config_loader
        self.mode = mode
        
        # Получаем конфигурацию БД
        db_config = config_loader.get_db_config(mode)
        self.db_name = config_loader.get('database.db_name', 'lichess_games')
        
        # Инициализируем подключение
        self.connection = DatabaseConnection(db_config, mode)
        
        # Загружаем схему
        schema_path = config_loader.get_schema_path()
        self.schema_loader = SchemaLoader(schema_path)
        self.schema = self.schema_loader.load()
        self.table_name = self.schema.table_name
        
        self.logger.info(f"DatabaseManager инициализирован (таблица: {self.table_name})")
    
    def create_database(self) -> bool:
        """
        Создает базу данных, если она не существует
        """
        try:
            # Подключаемся к стандартной БД postgres
            conn_params = {
                'dbname': 'postgres'
            }
            
            # Получаем параметры подключения из конфига
            db_config = self.config_loader.get_db_config(self.mode)
            
            # Проверяем существование БД
            with self.connection.get_cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM pg_database WHERE datname = %s
                """, (self.db_name,))
                
                if cur.fetchone():
                    self.logger.info(f"База данных {self.db_name} уже существует")
                    return True
                
                # Создаем БД
                # Отключаемся от текущей БД
                self.connection.disconnect()
                
                # Создаем временное подключение к postgres
                temp_conn_params = {
                    'host': db_config.get('host', 'localhost'),
                    'port': db_config.get('port', 5432),
                    'user': db_config.get('user'),
                    'password': db_config.get('password'),
                    'dbname': 'postgres'
                }
                
                import psycopg2
                temp_conn = psycopg2.connect(**temp_conn_params)
                temp_conn.autocommit = True
                
                with temp_conn.cursor() as cur:
                    cur.execute(f'CREATE DATABASE "{self.db_name}"')
                    self.logger.info(f"База данных {self.db_name} создана")
                
                temp_conn.close()
                
                # Переподключаемся к новой БД
                self.connection.connect()
                
                return True
                
        except Exception as e:
            self.logger.error(f"Ошибка создания БД: {e}")
            return False
    
    def create_table(self, drop_existing: bool = False) -> bool:
        """
        Создает таблицу на основе схемы
        
        Args:
            drop_existing: Удалить существующую таблицу
            
        Returns:
            bool: True если таблица создана успешно
        """
        try:
            # Сначала создаем БД, если нужно
            if not self.database_exists():
                self.create_database()
            
            # Генерируем SQL для создания таблицы
            sql = self.schema_loader.get_create_table_sql(drop_existing)
            
            # Выполняем SQL
            with self.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    conn.commit()
            
            self.logger.info(f"Таблица {self.table_name} создана (схема {self.schema.version})")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка создания таблицы: {e}")
            return False
    
    def database_exists(self) -> bool:
        """Проверяет существование базы данных"""
        try:
            with self.connection.get_cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM pg_database WHERE datname = %s
                """, (self.db_name,))
                return cur.fetchone() is not None
        except Exception:
            return False
    
    def table_exists(self) -> bool:
        """Проверяет существование таблицы"""
        try:
            with self.connection.get_cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s
                """, (self.table_name,))
                return cur.fetchone() is not None
        except Exception as e:
            self.logger.warning(f"Ошибка проверки таблицы: {e}")
            return False
    
    def drop_table(self) -> bool:
        """Удаляет таблицу"""
        try:
            if not self.table_exists():
                self.logger.warning(f"Таблица {self.table_name} не существует")
                return True
            
            with self.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f'DROP TABLE IF EXISTS "{self.table_name}" CASCADE;')
                    conn.commit()
            
            self.logger.info(f"Таблица {self.table_name} удалена")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка удаления таблицы: {e}")
            return False
    
    def insert_games(self, games: List[Game]) -> int:
        """
        Вставляет игры в таблицу
        """
        if not games:
            return 0
        
        if not self.table_exists():
            raise TableNotFoundError(f"Таблица {self.table_name} не существует")
        
        # Получаем маппинг полей
        field_mapping = self.schema_loader.get_field_mapping('pgn')
        
        inserted = 0
        errors = []
        
        try:
            with self.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    for game in games:
                        try:
                            # Преобразуем Game в словарь для БД
                            data = self._game_to_db_dict_fixed(game, field_mapping)
                            
                            # Строим INSERT запрос динамически
                            columns = list(data.keys())
                            values = [data[col] for col in columns]
                            
                            columns_str = ', '.join([f'"{col}"' for col in columns])
                            placeholders = ', '.join(['%s'] * len(values))
                            
                            query = f'INSERT INTO "{self.table_name}" ({columns_str}) VALUES ({placeholders})'
                            
                            cur.execute(query, values)
                            inserted += 1
                            
                        except Exception as e:
                            errors.append(f"Ошибка вставки игры {game.game_id}: {e}")
                            if len(errors) <= 3:  # Логируем только первые 3 ошибки
                                self.logger.debug(f"Данные вызвавшие ошибку: {data if 'data' in locals() else 'N/A'}")
                            continue
                    
                    conn.commit()
                    
        except Exception as e:
            self.logger.error(f"Ошибка вставки данных: {e}")
            if 'conn' in locals():
                conn.rollback()
            return 0
        
        if errors:
            self.logger.warning(f"Ошибок при вставке: {len(errors)}")
            for error in errors[:5]:
                self.logger.warning(error)
        
        self.logger.info(f"Вставлено {inserted} игр из {len(games)}")
        return inserted

    def _game_to_db_dict_fixed(self, game: Game, mapping: Dict[str, str]) -> Dict:
        """
        Преобразует объект Game в словарь для БД
        Использует правильное имя поля из маппинга
        """
        db_dict = {}
        
        # mapping: {поле_в_pgn: колонка_бд}
        # Нужно маппить атрибуты Game -> колонки БД
        for pgn_field, db_field in mapping.items():
            # Пытаемся получить значение из Game
            if hasattr(game, pgn_field):
                value = getattr(game, pgn_field)
                if value is not None:
                    # Преобразуем datetime в строку для БД
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    db_dict[db_field] = value
            else:
                # Поле не найдено в Game - пропускаем
                continue
        
        # Добавляем import_source
        db_dict['import_source'] = game.import_source
        
        return db_dict

    def _game_to_db_dict(self, game: Game, mapping: Dict[str, str]) -> Dict:
        """
        Преобразует объект Game в словарь для БД
        
        Args:
            game: Объект игры
            mapping: Маппинг полей (из схемы)
            
        Returns:
            Dict: Словарь для вставки в БД с правильными именами колонок
        """
        db_dict = {}
        
        # mapping: {источник: колонка_бд}
        # Нужно преобразовать поля Game в колонки БД
        for game_field, db_field in mapping.items():
            if hasattr(game, game_field):
                value = getattr(game, game_field)
                if value is not None:
                    # Преобразуем datetime в строку для БД
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    db_dict[db_field] = value
        
        # Добавляем import_source
        db_dict['import_source'] = game.import_source
        
        return db_dict
    
    def get_table_stats(self) -> Dict[str, Any]:
        """
        Получает статистику по таблице
        
        Returns:
            Dict: Статистика таблицы
        """
        stats = {
            'table_name': self.table_name,
            'exists': self.table_exists()
        }
        
        if not stats['exists']:
            return stats
        
        try:
            with self.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    # Количество записей
                    cur.execute(f'SELECT COUNT(*) FROM "{self.table_name}"')
                    stats['total_records'] = cur.fetchone()[0]
                    
                    # Статистика по результатам
                    cur.execute(f"""
                        SELECT result, COUNT(*) as count
                        FROM "{self.table_name}"
                        GROUP BY result
                    """)
                    stats['results_distribution'] = cur.fetchall()
                    
                    # Диапазон дат
                    cur.execute(f"""
                        SELECT 
                            MIN(game_date) as first_game,
                            MAX(game_date) as last_game
                        FROM "{self.table_name}"
                    """)
                    date_range = cur.fetchone()
                    stats['first_game'] = date_range[0]
                    stats['last_game'] = date_range[1]
                    
                    # Средняя точность
                    cur.execute(f"""
                        SELECT AVG(accuracy) 
                        FROM "{self.table_name}" 
                        WHERE accuracy IS NOT NULL
                    """)
                    stats['avg_accuracy'] = cur.fetchone()[0]
                    
                    # Количество уникальных соперников
                    cur.execute(f"""
                        SELECT COUNT(DISTINCT opponent_name)
                        FROM "{self.table_name}"
                    """)
                    stats['unique_opponents'] = cur.fetchone()[0]
                    
        except Exception as e:
            self.logger.warning(f"Ошибка получения статистики: {e}")
            stats['error'] = str(e)
        
        return stats
    
    def get_table_info(self) -> Dict[str, Any]:
        """Возвращает информацию о схеме"""
        return self.schema_loader.get_table_info()
    
    def close(self):
        """Закрывает подключение к БД"""
        self.connection.disconnect()
    
    def __enter__(self):
        """Вход в контекстный менеджер"""
        self.connection.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        self.close()