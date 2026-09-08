#!/usr/bin/env python3
"""
Запуск веб-приложения
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

app = create_app()

if __name__ == '__main__':
    print("🚀 Starting web server at http://localhost:5555")
    print("🌐 Available at: https://84-252-143-212.nip.io/lichess-analyzer/")
    app.run(debug=True, host='0.0.0.0', port=5555)