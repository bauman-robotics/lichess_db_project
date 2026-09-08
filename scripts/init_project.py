#!/usr/bin/env python3
"""
Скрипт инициализации проекта.
Создаёт виртуальное окружение, устанавливает зависимости,
проверяет конфигурацию.
"""
import os
import sys
import subprocess
import venv
import logging
from pathlib import Path
from typing import Optional
import shutil


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


class ProjectInitializer:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.venv_dir = self.root / "venv"
        self.requirements_file = self.root / "requirements.txt"
        self.logger = logging.getLogger(__name__)
        
    def check_python_version(self) -> bool:
        """Проверяет версию Python"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.logger.error(f"Требуется Python 3.8+, текущая версия: {version.major}.{version.minor}")
            return False
        self.logger.info(f"✅ Python версия {version.major}.{version.minor} OK")
        return True
    
    def create_virtual_env(self, force: bool = False) -> bool:
        """Создаёт виртуальное окружение"""
        if self.venv_dir.exists():
            if not force:
                self.logger.info(f"✅ Виртуальное окружение уже существует: {self.venv_dir}")
                return True
            
            self.logger.warning(f"Удаление существующего виртуального окружения...")
            shutil.rmtree(self.venv_dir)
        
        self.logger.info(f"Создание виртуального окружения в {self.venv_dir}")
        
        try:
            venv.create(self.venv_dir, with_pip=True, system_site_packages=False)
            self.logger.info("✅ Виртуальное окружение создано")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания виртуального окружения: {e}")
            return False
    
    def get_pip_path(self) -> Path:
        """Возвращает путь к pip в виртуальном окружении"""
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "pip.exe"
        return self.venv_dir / "bin" / "pip"
    
    def install_requirements(self) -> bool:
        """Устанавливает зависимости из requirements.txt"""
        if not self.requirements_file.exists():
            self.logger.warning(f"Файл {self.requirements_file} не найден")
            return False
        
        pip_path = self.get_pip_path()
        
        if not pip_path.exists():
            self.logger.error(f"pip не найден в {pip_path}")
            return False
        
        self.logger.info("Установка зависимостей...")
        
        cmd = [
            str(pip_path),
            "install",
            "-r",
            str(self.requirements_file),
            "--upgrade"
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.logger.info("✅ Зависимости установлены")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"❌ Ошибка установки зависимостей: {e.stderr}")
            return False
    
    def check_config_files(self) -> bool:
        """Проверяет наличие конфигурационных файлов"""
        secrets_file = self.root / "config" / "secrets.yaml"
        
        if not secrets_file.exists():
            self.logger.warning("""
⚠️  Файл config/secrets.yaml не найден!
    
    Создайте его на основе config/secrets.yaml.example:
    cp config/secrets.yaml.example config/secrets.yaml
    
    И заполните своими данными (пароли, пользователи БД)
            """)
            return False
        
        self.logger.info("✅ Конфигурационные файлы проверены")
        return True
    
    def create_directories(self) -> bool:
        """Создаёт необходимые директории"""
        directories = [
            "data/downloads",
            "data/uploads",
            "logs",
            "migrations"
        ]
        
        for dir_path in directories:
            path = self.root / dir_path
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Создана директория: {path}")
        
        return True
    
    def create_activation_script(self) -> bool:
        """Создаёт bash скрипт для активации окружения"""
        script_path = self.root / "activate.sh"
        
        script_content = f'''#!/bin/bash
# Активация виртуального окружения
source {self.venv_dir}/bin/activate

# Добавление проекта в PYTHONPATH
export PYTHONPATH="{self.root}:$PYTHONPATH"

echo "✅ Виртуальное окружение активировано"
echo "📁 Проект: {self.root}"
echo ""
echo "Доступные команды:"
echo "  python scripts/setup_db.py --help"
echo "  python scripts/import_games.py --help"
'''
        
        try:
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            os.chmod(script_path, 0o755)
            self.logger.info(f"✅ Создан скрипт активации: {script_path}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания скрипта активации: {e}")
            return False
    
    def initialize(self, force_venv: bool = False, skip_deps: bool = False) -> bool:
        """Основной метод инициализации"""
        self.logger.info("🚀 Начало инициализации проекта")
        print("=" * 50)
        
        steps = [
            ("Проверка Python", self.check_python_version),
            ("Создание директорий", self.create_directories),
            ("Создание виртуального окружения", lambda: self.create_virtual_env(force_venv)),
            ("Проверка конфигов", self.check_config_files),
        ]
        
        if not skip_deps:
            steps.append(("Установка зависимостей", self.install_requirements))
        
        steps.append(("Создание скрипта активации", self.create_activation_script))
        
        success = True
        for step_name, step_func in steps:
            self.logger.info(f"▶ {step_name}...")
            try:
                if not step_func():
                    self.logger.error(f"❌ {step_name} не выполнен")
                    success = False
                    break
            except Exception as e:
                self.logger.error(f"❌ {step_name}: ошибка - {e}")
                success = False
                break
        
        if success:
            print("=" * 50)
            self.logger.info("""
✅ Инициализация проекта завершена успешно!
            
Дальнейшие шаги:
1. Активируйте виртуальное окружение:
   source activate.sh
   
2. Настройте секреты в config/secrets.yaml:
   - Укажите пароль PostgreSQL
   - Укажите имя пользователя Lichess (опционально)
   
3. Создайте структуру БД:
   python scripts/setup_db.py --action create
   
4. Импортируйте игры:
   # Из файла:
   python scripts/import_games.py --source file --path data/uploads/games.pgn
   
   # Или через API:
   python scripts/import_games.py --source api --username your_name --limit 100
            """)
        else:
            self.logger.error("❌ Инициализация завершена с ошибками")
        
        return success


def main():
    project_root = Path(__file__).parent.parent.absolute()
    
    import argparse
    parser = argparse.ArgumentParser(description='Инициализация проекта')
    parser.add_argument('--force-venv', action='store_true',
                       help='Пересоздать виртуальное окружение')
    parser.add_argument('--skip-deps', action='store_true',
                       help='Пропустить установку зависимостей')
    parser.add_argument('--verbose', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    logger = setup_logging()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    initializer = ProjectInitializer(project_root)
    success = initializer.initialize(force_venv=args.force_venv, 
                                    skip_deps=args.skip_deps)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
