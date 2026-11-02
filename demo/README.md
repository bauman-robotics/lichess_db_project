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

## Обзорный сценарий

`scenarios/overview.yaml` — расширенный ролик:

- поиск и список стримеров;
- страница игрока и количество игр;
- готовый разбор DeepSeek;
- выбор варианта промпта;
- доска, комментарии, переход по ходу из комментария;
- график Stockfish, клик по точке и текущая оценка;
- переход к фильтру по дебюту;
- фильтр по цвету и популярные дебюты;
- прогресс рейтинга и переход к партии по клику на графике;
- избранное и заметки;
- ссылки на Lichess.

Запись: `demo/.venv/bin/python demo/record_demo.py --scenario demo/scenarios/overview.yaml`.

## Большой обзор

`scenarios/overview_v4.yaml` — продолжение после вступления с Lichess:

- 300 игр и пагинация;
- топ дебютов с сортировкой по победам и поражениям;
- переход к партиям проблемного дебюта;
- подсказки на кнопках анализа (Lichess / Stockfish / DeepSeek);
- готовый разбор и переключение вариантов промпта;
- переворот доски, навигация, переходы по комментариям;
- график и текущая оценка;
- копирование всей и части нотации;
- заметка с посимвольным вводом, сохранением и удалением;
- избранное и фильтр по нотации;
- прогресс, длина партий, избранное с поиском;
- тёмная страница README на GitHub в финале.

## Сборка финального видео

Вступление `overview_intro` (1680×1050) нормализуется до 1920×1080:

```bash
ffmpeg -y -i demo/output/Личесс_Аниш_Гири.mp4 \
  -vf "scale=1728:1080:force_original_aspect_ratio=decrease,\
pad=1920:1080:96:0:color=0x161512,setsar=1" \
  -r 30 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -an \
  demo/output/intro-normalized.mp4
```

Затем склеить с `overview-v4.mp4`:

```bash
printf "file '%s'\nfile '%s'\n" \
  "$PWD/demo/output/intro-normalized.mp4" \
  "$PWD/demo/output/overview-v4.mp4" > demo/output/concat-v4.txt
ffmpeg -y -f concat -safe 0 -i demo/output/concat-v4.txt \
  -c copy -movflags +faststart demo/output/overview-user-final.mp4
```

## Особенности

- Курсор и клики рисуются внутри страницы, поэтому попадают в видео.
- Системный курсор скрывается.
- Видео записывается Playwright без окна браузера.
- Для локального сервера используйте `base_url: http://127.0.0.1:5555`.
  В текущей конфигурации приложения публичные ссылки содержат префикс
  `/lichess-analyzer`, поэтому тестовый сценарий записан на production URL.
