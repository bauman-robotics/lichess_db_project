#!/usr/bin/env python3
"""Миграция 005: stage/progress/total для analysis_tasks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.database.migrations import ensure_analysis_task_columns

db = DatabaseManager(ConfigLoader(), 'local')
try:
    print('✅ Колонки добавлены' if ensure_analysis_task_columns(db)
          else 'analysis_tasks отсутствует')
finally:
    db.close()
