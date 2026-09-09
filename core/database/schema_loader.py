"""
Загрузчик и менеджер схемы таблицы из YAML файла
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from core.exceptions.custom_exceptions import SchemaError


@dataclass
class SchemaColumn:
    """Определение колонки таблицы"""
    name: str
    type: str
    constraints: str = ""
    comment: str = ""
    system: bool = False
    index: bool = False
    trigger_update: bool = False
    default: Any = None


@dataclass
class SchemaIndex:
    """Определение индекса"""
    name: str
    columns: List[str]
    comment: str = ""
    type: str = "BTREE"


@dataclass
class TableSchema:
    """Полная схема таблицы"""
    version: str
    name: str
    description: str
    table_name: str
    columns: List[SchemaColumn]
    indexes: List[SchemaIndex]
    composite_indexes: List[Dict] = field(default_factory=list)
    constraints: List[Dict] = field(default_factory=list)
    field_mappings: Dict[str, Dict] = field(default_factory=dict)


class SchemaLoader:
    """
    Загружает схему таблицы из YAML файла
    """
    
    def __init__(self, schema_path: Optional[str] = None):
        """
        Инициализация загрузчика схемы
        
        Args:
            schema_path: Путь к файлу схемы
        """
        self.logger = logging.getLogger(__name__)
        self.schema_path = schema_path
        self.schema: Optional[TableSchema] = None
        self._loaded = False
    
    def load(self, schema_path: Optional[str] = None) -> TableSchema:
        """
        Загружает схему из файла
        
        Args:
            schema_path: Путь к файлу схемы (если не указан, используется сохраненный)
            
        Returns:
            TableSchema: Загруженная схема
            
        Raises:
            SchemaError: Если файл не найден или имеет неверный формат
        """
        if schema_path:
            self.schema_path = schema_path
        
        if not self.schema_path:
            # Путь по умолчанию
            base_dir = Path(__file__).parent.parent.parent
            self.schema_path = str(base_dir / 'config' / 'schemas' / 'v1_lichess_games.yaml')
        
        if not os.path.exists(self.schema_path):
            raise SchemaError(f"Файл схемы не найден: {self.schema_path}")
        
        self.logger.info(f"Загрузка схемы из {self.schema_path}")
        
        try:
            with open(self.schema_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SchemaError(f"Ошибка парсинга YAML: {e}")
        
        schema_data = data.get('schema', {})
        if not schema_data:
            raise SchemaError("В файле схемы отсутствует секция 'schema'")
        
        # Парсинг колонок
        columns = []
        for col_data in schema_data.get('table', {}).get('columns', []):
            columns.append(SchemaColumn(
                name=col_data['name'],
                type=col_data['type'],
                constraints=col_data.get('constraints', ''),
                comment=col_data.get('comment', ''),
                system=col_data.get('system', False),
                index=col_data.get('index', False),
                trigger_update=col_data.get('trigger_update', False),
                default=col_data.get('default')
            ))
        
        # Парсинг индексов
        indexes = []
        for idx_data in schema_data.get('indexes', []):
            indexes.append(SchemaIndex(
                name=idx_data['name'],
                columns=idx_data['columns'],
                comment=idx_data.get('comment', ''),
                type=idx_data.get('type', 'BTREE')
            ))
        
        # Создаем объект схемы
        self.schema = TableSchema(
            version=schema_data.get('version', '1.0.0'),
            name=schema_data.get('name', 'unknown_schema'),
            description=schema_data.get('description', ''),
            table_name=schema_data.get('table', {}).get('name', 'games'),
            columns=columns,
            indexes=indexes,
            composite_indexes=schema_data.get('composite_indexes', []),
            constraints=schema_data.get('constraints', []),
            field_mappings=data.get('field_mappings', {})
        )
        
        self._loaded = True
        self.logger.info(f"Схема загружена: версия {self.schema.version}, {len(columns)} колонок")
        
        return self.schema
    
    def get_schema(self) -> TableSchema:
        """Возвращает загруженную схему"""
        if not self._loaded:
            self.load()
        return self.schema
    
    def get_create_table_sql(self, drop_existing: bool = False) -> str:
        """
        Генерирует SQL для создания таблицы
        
        Args:
            drop_existing: Удалить существующую таблицу
            
        Returns:
            str: SQL запрос
        """
        schema = self.get_schema()
        table_name = schema.table_name
        
        sql_parts = []
        
        if drop_existing:
            sql_parts.append(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
        
        # Создание таблицы
        columns_sql = []
        for col in schema.columns:
            col_sql = f'"{col.name}" {col.type}'
            if col.constraints:
                col_sql += f" {col.constraints}"
            if col.default is not None:
                col_sql += f" DEFAULT {col.default}"
            columns_sql.append(col_sql)
        
        columns_str = ",\n    ".join(columns_sql)
        create_table = f'''
CREATE TABLE IF NOT EXISTS "{table_name}" (
    {columns_str}
);
'''
        sql_parts.append(create_table)
        
        # Комментарии к колонкам
        for col in schema.columns:
            if col.comment:
                comment = col.comment.replace("'", "''")
                sql_parts.append(
                    f'COMMENT ON COLUMN "{table_name}"."{col.name}" IS \'{comment}\';'
                )
        
        # Создание индексов
        for idx in schema.indexes:
            columns_str = ", ".join(idx.columns)
            sql_parts.append(
                f'CREATE INDEX IF NOT EXISTS "{idx.name}" ON "{table_name}" '
                f'USING {idx.type} ({columns_str});'
            )
        
        # Создание составных индексов
        for idx in schema.composite_indexes:
            columns_str = ", ".join([f'"{col}"' for col in idx.get('columns', [])])
            sql_parts.append(
                f'CREATE INDEX IF NOT EXISTS "{idx["name"]}" ON "{table_name}" '
                f'({columns_str});'
            )
        
        # Ограничения таблицы
        for constraint in schema.constraints:
            sql_parts.append(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT {constraint["name"]} '
                f'CHECK ({constraint["sql"]});'
            )
        
        # Триггер для updated_at
        if any(col.trigger_update for col in schema.columns):
            sql_parts.append(self._create_update_trigger_sql(table_name))
        
        return "\n".join(sql_parts)
    
    def _create_update_trigger_sql(self, table_name: str) -> str:
        """Создает триггер для обновления updated_at"""
        # Очищаем имя таблицы от спецсимволов для имени триггера
        trigger_name = f"update_{table_name}_updated_at".replace('-', '_').replace('.', '_')
        
        return f'''
    -- Функция для обновления updated_at
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ language 'plpgsql';

    -- Триггер для таблицы {table_name}
    DROP TRIGGER IF EXISTS {trigger_name} ON "{table_name}";
    CREATE TRIGGER {trigger_name}
        BEFORE UPDATE ON "{table_name}"
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    '''
        
    def get_field_mapping(self, source: str = 'pgn') -> Dict[str, str]:
        """Возвращает маппинг полей для указанного источника"""
        schema = self.get_schema()
        return schema.field_mappings.get(source, {})
    
    def get_column_names(self, exclude_system: bool = True) -> List[str]:
        """Возвращает список имен колонок"""
        schema = self.get_schema()
        if exclude_system:
            return [col.name for col in schema.columns if not col.system]
        return [col.name for col in schema.columns]
    
    def get_insert_query(self) -> str:
        """Генерирует INSERT запрос"""
        schema = self.get_schema()
        table_name = schema.table_name
        
        exclude_fields = ['id', 'created_at', 'updated_at']
        columns = [col.name for col in schema.columns if col.name not in exclude_fields]
        
        columns_str = ', '.join([f'"{col}"' for col in columns])
        placeholders = ', '.join([f'%({col})s' for col in columns])
        
        return f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders});'
    
    def get_table_info(self) -> Dict[str, Any]:
        """Возвращает информацию о схеме для отображения"""
        schema = self.get_schema()
        return {
            'name': schema.name,
            'version': schema.version,
            'description': schema.description,
            'table_name': schema.table_name,
            'column_count': len(schema.columns),
            'index_count': len(schema.indexes) + len(schema.composite_indexes),
            'columns': [
                {
                    'name': col.name,
                    'type': col.type,
                    'constraints': col.constraints,
                    'comment': col.comment,
                    'system': col.system
                }
                for col in schema.columns
            ]
        }