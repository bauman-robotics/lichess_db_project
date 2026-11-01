"""
Flask приложение
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, request
from flask_wtf.csrf import CSRFProtect

from web_app.config import WebConfig
from web_app.import_tasks import start_import_worker
from web_app.engine_tasks import start_engine_worker
from services.engine_analysis import get_engine_config
from config.config_loader import ConfigLoader
from services.deepseek_analyzer import list_prompt_variants
from web_app.routes import get_favorites_count, get_notes_count, main_bp


def create_app():
    """Создает Flask приложение"""
    app = Flask(
        __name__,
        template_folder=str(WebConfig.TEMPLATES_DIR),
        static_folder=str(WebConfig.STATIC_DIR),
        static_url_path='/static'
    )
    
    app.config['SECRET_KEY'] = WebConfig.SECRET_KEY
    app.config['DEBUG'] = WebConfig.DEBUG
     
    csrf = CSRFProtect(app)  
    
    @app.context_processor
    def inject_current_player():
        """Имя игрока из URL — для чипа в шапке, и счётчик избранного."""
        return {
            'current_player': (request.view_args or {}).get('username'),
            'favorite_count': get_favorites_count(),
            'note_count': get_notes_count(),
            'prompt_variants': list_prompt_variants(),
        }
    
    # Регистрируем блюпринт БЕЗ префикса
    app.register_blueprint(main_bp)

    # Один фоновый worker на процесс: забирает queued-задачи импорта.
    start_import_worker()
    # Движок запускаем только если он включён в конфиге.
    if get_engine_config(ConfigLoader())['enabled']:
        start_engine_worker()
    
    return app