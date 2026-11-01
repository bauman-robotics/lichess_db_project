# Обновление приложения на сервере

Схема из двух частей:

- `scripts/deploy/update_remote.py` — запускается **локально**, подключается по SSH,
  загружает серверный скрипт и выполняет его.
- `scripts/deploy/server_update.sh` — выполняется **на сервере**: `git pull`,
  миграции, перезапуск systemd-сервиса, healthcheck.

Локальный скрипт загружает серверный во временный файл `/tmp`, поэтому первый
запуск работает даже если этой папки ещё нет на сервере.

---

## 1. Настройка

Добавьте в `config/secrets.yaml` (файл не коммитится):

```yaml
deploy:
  host: "your-server-ip"          # можно не указывать — возьмётся remote.ssh.host
  user: "ubuntu"                  # можно не указывать — remote.ssh.user
  port: 22
  key_path: "~/.ssh/id_rsa"
  key_password: null
  project_path: "/home/ubuntu/lichess_db_project"
  service: "lichess-analyzer"
  branch: "dev_1_service"         # пусто = текущая ветка сервера
  use_sudo: true
  run_migrations: true
  healthcheck_url: ""             # например http://127.0.0.1:5555/lichess-analyzer/
  strict_host_key: false
```

`host`, `user`, `port`, `key_path` можно не дублировать — они возьмутся из
`remote.ssh`, если в `deploy` их нет.

Проверка без подключения:

```bash
python scripts/deploy/update_remote.py --dry-run
```

---

## 2. SSH-доступ

Рекомендуется ключ без пароля (или с `key_password` в конфиге):

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub ubuntu@your-server-ip
ssh ubuntu@your-server-ip 'echo ok'
```

Если включён `strict_host_key: true`, хост должен быть в `~/.ssh/known_hosts`.

Пароль SSH можно передать через переменную окружения, чтобы не светить в истории:

```bash
DEPLOY_SSH_PASSWORD='...' python scripts/deploy/update_remote.py
```

---

## 3. sudo для systemctl

Скрипт использует `sudo -n` — без интерактивного запроса пароля. Настройте
NOPASSWD для нужных команд:

```bash
sudo visudo -f /etc/sudoers.d/lichess-analyzer
```

```
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart lichess-analyzer
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active lichess-analyzer
```

Путь к `systemctl` проверьте через `which systemctl` и подставьте свой.

Если сервис можно перезапускать без sudo, запустите с `--no-sudo`.

---

## 4. Использование

```bash
# показать план, не подключаясь
python scripts/deploy/update_remote.py --dry-run

# обновить с подтверждением
python scripts/deploy/update_remote.py

# без подтверждения (для автоматизации)
python scripts/deploy/update_remote.py --yes
```

Полезные флаги:

| Флаг | Значение |
|---|---|
| `--branch main` | ветка для `git pull` |
| `--path /path` | путь к проекту на сервере |
| `--service name` | имя systemd-сервиса |
| `--skip-migrations` | не запускать `setup_db.py` |
| `--skip-restart` | только `git pull`, без рестарта |
| `--no-sudo` | `systemctl` без sudo |
| `--healthcheck-url URL` | проверить URL после рестарта |
| `HEALTHCHECK_RETRIES=30` | сколько секунд ждать ответа healthcheck |
| `--strict-host-key` | требовать known_hosts |

Ветку можно не указывать — тогда сервер сделает `git pull --ff-only` для
текущей ветки.

---

## 5. Что делает серверный скрипт

1. Проверяет, что каталог существует и это git-репозиторий.
2. Проверяет, что нет изменений в **отслеживаемых** файлах. Untracked-файлы
   (например, сгенерированный `activate.sh`) обновление не блокируют, но
   выводят предупреждение. Если изменён отслеживаемый файл — скрипт
   останавливается, ничего не удаляя.
3. `git fetch --prune origin` (если задана ветка), при необходимости
   `git checkout`, затем `git pull --ff-only`.
4. Если `RUN_MIGRATIONS=1` — запускает:
   ```bash
   venv/bin/python scripts/setup_db.py --action create
   ```
   Это идемпотентно: создаёт служебные таблицы `game_annotations` и
   `import_tasks`, не трогая таблицы партий.
5. Перезапускает сервис через `sudo -n systemctl restart`.
6. Проверяет `systemctl is-active`.
7. Если задан `healthcheck_url` — проверяет URL с повторами
   (по умолчанию 30 секунд), потому что gunicorn поднимается не мгновенно.

При ошибке печатает статус сервиса и завершается с ненулевым кодом.

---

## 6. Ручной запуск на сервере

Серверный скрипт можно запустить и без локального. `PROJECT_PATH` определяется
автоматически по расположению скрипта, `USE_SUDO` — по пользователю (0 для root):

```bash
cd /root/lichess_db_project
bash scripts/deploy/server_update.sh
# или
cd scripts/deploy && ./server_update.sh
```

Если нужно явно:

```bash
PROJECT_PATH="$PWD" BRANCH=dev_1_service SERVICE=lichess-analyzer \
bash scripts/deploy/server_update.sh
```

Проверка без изменений:

```bash
DRY_RUN=1 bash scripts/deploy/server_update.sh
```

---

## 7. Безопасность и ограничения

- Скрипт не делает `git reset --hard`, не удаляет данные и не пересоздаёт
  таблицы партий.
- `git pull` только `--ff-only`: при расхождении истории обновление
  остановится, а не создаст merge-коммит на сервере.
- Если на сервере изменены отслеживаемые файлы, обновление не начнётся.
  Untracked-файлы не блокируют `git pull`; `activate.sh` добавлен в `.gitignore`.
- Перед первым запуском стоит сделать бэкап БД штатными средствами.
- Локальный скрипт не выполняет `git push`; предполагается, что нужный
  коммит уже есть в удалённой ветке.
