"""
Flask приложение
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from web_app.config import WebConfig
from web_app.routes import main_bp


def create_app():
    """Создает Flask приложение"""
    app = Flask(
        __name__,
        template_folder=str(WebConfig.TEMPLATES_DIR),
        static_folder=str(WebConfig.STATIC_DIR),
        static_url_path='/static'  # ← без префикса
    )
    
    app.config['SECRET_KEY'] = WebConfig.SECRET_KEY
    app.config['DEBUG'] = WebConfig.DEBUG
    
    csrf = CSRFProtect(app)
    
    # Регистрируем блюпринт БЕЗ префикса
    app.register_blueprint(main_bp)  # ← убрали url_prefix
    
    return app