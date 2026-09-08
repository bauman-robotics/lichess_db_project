#!/usr/bin/env python3
"""
WSGI entry point for production
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

print(f"📁 Project root: {project_root}")

try:
    from web_app.app import create_app
    print("✅ Web app imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Создаем приложение
app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5555)
