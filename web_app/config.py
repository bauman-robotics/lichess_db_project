"""
Конфигурация веб-приложения
"""
import os
from pathlib import Path

# Путь к корню проекта
BASE_DIR = Path(__file__).parent.parent

class WebConfig:
    """Конфигурация веб-приложения"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Пути к шаблонам и статике
    TEMPLATES_DIR = BASE_DIR / 'web_app' / 'templates'
    STATIC_DIR = BASE_DIR / 'web_app' / 'static'
    
    # Используем существующую БД
    DB_NAME = os.getenv('DB_NAME', 'lichess_games')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    
    # Lichess API
    LICHESS_API_URL = 'https://lichess.org/api'
    
    # Настройки приложения
    MAX_GAMES_DOWNLOAD = 1000
    RESULTS_PER_PAGE = 20