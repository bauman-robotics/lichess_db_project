#!/usr/bin/env python3
"""
Обновление приложения на сервере по SSH.

Запускается локально:
    python scripts/deploy/update_remote.py --dry-run
    python scripts/deploy/update_remote.py
    python scripts/deploy/update_remote.py --yes

Что делает:
  1. читает настройки из config/secrets.yaml (секция deploy / remote.ssh);
  2. подключается к серверу по SSH;
  3. загружает scripts/deploy/server_update.sh во временный файл;
  4. запускает его: git pull, миграции, перезапуск systemd-сервиса,
     опциональный healthcheck;
  5. удаляет временный файл.

Серверный скрипт лежит в репозитории и может запускаться вручную.
"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "secrets.yaml"
SERVER_SCRIPT = Path(__file__).with_name("server_update.sh")


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Конфиг не найден: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Ожидался словарь в конфиге: {path}")
    return data


def first(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def build_settings(args) -> Dict[str, Any]:
    config = load_config(Path(args.config).expanduser())
    remote = config.get("remote") or {}
    ssh = remote.get("ssh") or {}
    deploy = config.get("deploy") or {}

    host = first(args.host, deploy.get("host"), ssh.get("host"))
    user = first(args.user, deploy.get("user"), ssh.get("user"))
    port = first(args.port, deploy.get("port"), ssh.get("port"), 22)
    project_path = first(args.path, deploy.get("project_path"))
    key_path = first(args.key_path, deploy.get("key_path"), ssh.get("key_path"))
    key_password = first(
        args.key_password,
        os.environ.get("DEPLOY_KEY_PASSWORD"),
        deploy.get("key_password"),
        ssh.get("key_password"),
    )
    password = first(
        args.password,
        os.environ.get("DEPLOY_SSH_PASSWORD"),
        deploy.get("password"),
        ssh.get("password"),
    )

    if not host:
        raise SystemExit("Не задан host: укажите deploy.host / remote.ssh.host или --host")
    if not user:
        raise SystemExit("Не задан user: укажите deploy.user / remote.ssh.user или --user")
    if not project_path:
        raise SystemExit("Не задан project_path: укажите deploy.project_path или --path")

    run_migrations = bool(deploy.get("run_migrations", True))
    if args.skip_migrations:
        run_migrations = False

    return {
        "host": str(host),
        "user": str(user),
        "port": int(port or 22),
        "project_path": str(project_path),
        "branch": str(first(args.branch, deploy.get("branch"), "") or ""),
        "service": str(first(args.service, deploy.get("service"), "lichess-analyzer")),
        "key_path": str(Path(key_path).expanduser()) if key_path else None,
        "key_password": str(key_password) if key_password else None,
        "password": str(password) if password else None,
        "python_bin": str(first(args.python_bin, deploy.get("python_bin"), "") or ""),
        "use_sudo": bool(deploy.get("use_sudo", True)),
        "run_migrations": run_migrations,
        "skip_restart": bool(args.skip_restart),
        "healthcheck_url": str(first(args.healthcheck_url, deploy.get("healthcheck_url"), "") or ""),
        "strict_host_key": bool(deploy.get("strict_host_key", False)),
        "connect_timeout": int(first(args.timeout, deploy.get("connect_timeout"), 15)),
    }


def print_plan(settings: Dict[str, Any]) -> None:
    print("\n📦 Обновление приложения")
    print(f"  Сервер:      {settings['user']}@{settings['host']}:{settings['port']}")
    print(f"  Проект:      {settings['project_path']}")
    print(f"  Ветка:       {settings['branch'] or 'текущая ветка сервера'}")
    print(f"  Сервис:      {settings['service']}")
    print(f"  Миграции:    {'да' if settings['run_migrations'] else 'нет'}")
    print(f"  Перезапуск:  {'нет' if settings['skip_restart'] else 'да'}")
    if settings["healthcheck_url"]:
        print(f"  Healthcheck: {settings['healthcheck_url']}")
    print(f"  SSH-ключ:    {settings['key_path'] or 'пароль/agent'}")


def confirm(settings: Dict[str, Any], assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("Нет TTY для подтверждения. Запустите с --yes.")
    answer = input("\nПродолжить? [y/N]: ").strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        raise SystemExit("Отменено.")


def connect_ssh(settings: Dict[str, Any]):
    try:
        import paramiko
    except ImportError as e:
        raise SystemExit(
            "Не установлен paramiko. Установите: pip install paramiko"
        ) from e

    client = paramiko.SSHClient()
    client.load_system_host_keys()

    if settings["strict_host_key"]:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: Dict[str, Any] = {
        "hostname": settings["host"],
        "port": settings["port"],
        "username": settings["user"],
        "timeout": settings["connect_timeout"],
        "banner_timeout": settings["connect_timeout"],
        "auth_timeout": settings["connect_timeout"],
        "allow_agent": True,
        "look_for_keys": True,
    }

    key_path = settings["key_path"]
    if key_path:
        if not Path(key_path).exists():
            print(f"⚠️  SSH-ключ не найден локально: {key_path}", file=sys.stderr)
        else:
            connect_kwargs["key_filename"] = key_path
    if settings["key_password"]:
        connect_kwargs["passphrase"] = settings["key_password"]
    if settings["password"]:
        connect_kwargs["password"] = settings["password"]

    try:
        client.connect(**connect_kwargs)
    except paramiko.BadHostKeyException as e:
        raise SystemExit(
            f"Не совпал host key для {settings['host']}: {e}. "
            "Проверьте ~/.ssh/known_hosts."
        ) from e
    except paramiko.AuthenticationException as e:
        raise SystemExit(
            f"Ошибка аутентификации SSH для {settings['user']}@{settings['host']}: {e}"
        ) from e
    except Exception as e:
        raise SystemExit(f"Не удалось подключиться по SSH: {e}") from e

    return client


def upload_server_script(client, local_script: Path) -> str:
    if not local_script.exists():
        raise SystemExit(f"Серверный скрипт не найден: {local_script}")
    remote_path = f"/tmp/lichess_update_{uuid.uuid4().hex}.sh"
    sftp = client.open_sftp()
    try:
        sftp.put(str(local_script), remote_path)
        sftp.chmod(remote_path, 0o700)
    finally:
        sftp.close()
    return remote_path


def run_remote_command(client, command: str) -> int:
    """Выполняет команду, стримит объединённый stdout/stderr, возвращает код."""
    transport = client.get_transport()
    if transport is None:
        raise SystemExit("SSH-соединение потеряно")

    channel = transport.open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(command)

    while True:
        if channel.recv_ready():
            data = channel.recv(4096)
            if data:
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()
                continue
        if channel.exit_status_ready():
            break
        time.sleep(0.05)

    while channel.recv_ready():
        data = channel.recv(4096)
        if not data:
            break
        sys.stdout.write(data.decode("utf-8", errors="replace"))
        sys.stdout.flush()

    return channel.recv_exit_status()


def build_remote_command(settings: Dict[str, Any], remote_script: str) -> str:
    env = {
        "PROJECT_PATH": settings["project_path"],
        "BRANCH": settings["branch"],
        "SERVICE": settings["service"],
        "RUN_MIGRATIONS": "1" if settings["run_migrations"] else "0",
        "SKIP_RESTART": "1" if settings["skip_restart"] else "0",
        "USE_SUDO": "1" if settings["use_sudo"] else "0",
        "PYTHON_BIN": settings["python_bin"],
        "HEALTHCHECK_URL": settings["healthcheck_url"],
    }
    env_parts = [
        f"{key}={shlex.quote(value)}"
        for key, value in env.items()
        if value != ""
    ]
    return f"env {' '.join(env_parts)} bash {shlex.quote(remote_script)}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Обновить приложение на сервере по SSH",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/deploy/update_remote.py --dry-run
  python scripts/deploy/update_remote.py
  python scripts/deploy/update_remote.py --yes
  python scripts/deploy/update_remote.py --branch main --skip-migrations
        """,
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="путь к secrets.yaml")
    parser.add_argument("--host", help="IP или домен сервера")
    parser.add_argument("--user", help="пользователь SSH")
    parser.add_argument("--port", type=int, help="порт SSH")
    parser.add_argument("--path", help="путь к проекту на сервере")
    parser.add_argument("--branch", help="ветка для git pull (по умолчанию текущая)")
    parser.add_argument("--service", help="имя systemd-сервиса")
    parser.add_argument("--key-path", help="путь к SSH-ключу")
    parser.add_argument("--key-password", help="пароль SSH-ключа (лучше через env)")
    parser.add_argument("--password", help="пароль SSH (лучше через env)")
    parser.add_argument("--python-bin", help="python на сервере (venv/bin/python)")
    parser.add_argument("--healthcheck-url", help="URL для проверки после рестарта")
    parser.add_argument("--timeout", type=int, help="таймаут SSH-подключения, сек")
    parser.add_argument("--skip-migrations", action="store_true", help="не запускать setup_db")
    parser.add_argument("--skip-restart", action="store_true", help="не перезапускать сервис")
    parser.add_argument("--strict-host-key", action="store_true", help="строгая проверка host key")
    parser.add_argument("--no-sudo", action="store_true", help="не использовать sudo для systemctl")
    parser.add_argument("--dry-run", action="store_true", help="показать план без подключения")
    parser.add_argument("--yes", "-y", action="store_true", help="без подтверждения")
    args = parser.parse_args()

    settings = build_settings(args)
    if args.strict_host_key:
        settings["strict_host_key"] = True
    if args.no_sudo:
        settings["use_sudo"] = False

    print_plan(settings)

    if args.dry_run:
        print("\n[dry-run] SSH-подключение не выполняется.")
        print(f"[dry-run] Будет загружен: {SERVER_SCRIPT}")
        print(f"[dry-run] Команда: {build_remote_command(settings, '<remote-tmp-script>')}")
        return 0

    confirm(settings, args.yes)
    client = connect_ssh(settings)
    remote_script: Optional[str] = None

    try:
        remote_script = upload_server_script(client, SERVER_SCRIPT)
        command = build_remote_command(settings, remote_script)
        print("\n▶ Выполнение на сервере...\n")
        status = run_remote_command(client, command)
        if status == 0:
            print("\n✅ Обновление завершено успешно")
        else:
            print(f"\n❌ Серверный скрипт завершился с кодом {status}", file=sys.stderr)
        return status
    finally:
        if remote_script:
            try:
                client.exec_command(f"rm -f {shlex.quote(remote_script)}")
            except Exception:
                pass
        client.close()


if __name__ == "__main__":
    sys.exit(main())
