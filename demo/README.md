# Демо-запись интерфейса

Отдельный Playwright-проект для записи презентационных роликов сервиса.
Не влияет на production-зависимости и не разворачивается на сервере.

## Установка

```bash
cd demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Chromium скачивается в `demo/.cache/ms-playwright`, чтобы не писать
в домашний кэш.

## Запись

```bash
demo/.venv/bin/python demo/record_demo.py \
  --scenario demo/scenarios/test.yaml
```

Результат: `demo/output/test-demo.mp4` — 1920×1080, 30 fps, H.264.

## Сценарий

Сценарий — YAML-файл. Поддерживаются шаги:

- `goto` — открыть URL;
- `wait_for` — дождаться элемента;
- `caption` — подпись внизу кадра;
- `move_to` — плавно навести курсор;
- `click` — клик;
- `type` — ввод текста;
- `press` — нажатие клавиши;
- `scroll` — прокрутка;
- `pause` — пауза в миллисекундах.

Координаты можно задать через `selector` или вручную:

```yaml
- click:
    selector: "a[href$='/player/DenNedelin']"
```

или:

```yaml
- click:
    x: 420
    y: 310
```

## Особенности

- Курсор и клики рисуются внутри страницы, поэтому попадают в видео.
- Системный курсор скрывается.
- Видео записывается Playwright без окна браузера.
- Для локального сервера используйте `base_url: http://127.0.0.1:5555`.
  В текущей конфигурации приложения публичные ссылки содержат префикс
  `/lichess-analyzer`, поэтому тестовый сценарий записан на production URL.
