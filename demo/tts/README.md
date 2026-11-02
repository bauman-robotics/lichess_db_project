# Озвучка демо

## Готовые версии

| Версия | Видео | Аудио | Сценарий |
|---|---|---|---|
| Десктоп, Alena | [overview-final-v5-voice-alena-sync.mp4](../output/overview-final-v5-voice-alena-sync.mp4) | [desktop-alena-sync.m4a](final/desktop-alena-sync.m4a) | [desktop-script.md](final/desktop-script.md) |
| Мобильная, Filipp | [overview-mobile-voice-filipp.mp4](../output/overview-mobile-voice-filipp.mp4) | [mobile-filipp.m4a](final/mobile-filipp.m4a) | [mobile-script.md](final/mobile-script.md) |

## Структура

```text
demo/tts/
├── final/                 # готовые сценарии и аудиодорожки
├── source/
│   ├── desktop/blocks/    # блоки десктопной озвучки
│   └── mobile/blocks/     # блоки мобильной озвучки
├── archive/
│   ├── edge/              # тесты Edge TTS
│   ├── lichess-variants/  # варианты произношения Lichess
│   ├── full-takes/        # старые цельные дорожки
│   ├── old-scripts/       # старые сценарии
│   └── test-texts/        # тестовые тексты
├── pronunciation.md       # ударения и произношение
└── test_voices.py         # генерация тестовых сэмплов
```

## Секреты

```bash
mkdir -p demo/tts/.secrets
cp demo/tts/tts.env.example demo/tts/.secrets/tts.env
```

Заполните `demo/tts/.secrets/tts.env`. Файл исключён из git.

## Установка и генерация

```bash
demo/.venv/bin/pip install -r demo/tts/requirements.txt

set -a
source demo/tts/.secrets/tts.env
set +a

demo/.venv/bin/python demo/tts/test_voices.py --provider yandex
```

Тестовые файлы создаются в `demo/tts/samples/` — этот каталог временный
и исключён из git.

## Ударения

Для Yandex используйте `+` перед ударной гласной:

```text
Л+ичесс
анализ+атор
Стокф+иш
Дипс+ик
```

Подробнее — в [pronunciation.md](pronunciation.md).

## Перегенерация блоков

Тексты блоков лежат в `source/desktop/blocks/*.txt` и
`source/mobile/blocks/*.txt`. Тайминги — в `timeline.json` рядом с блоками.
