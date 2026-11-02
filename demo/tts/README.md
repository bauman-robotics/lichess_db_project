# Тест голосов TTS

Сравнение русских голосов на одном тексте:

- Edge TTS — бесплатный baseline;
- Yandex SpeechKit;
- Azure Neural TTS;
- Google Cloud TTS;
- Amazon Polly.

## Секреты

Создайте `demo/tts/.secrets/tts.env`:

```bash
YANDEX_API_KEY=
YANDEX_FOLDER_ID=

AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=westeurope

GOOGLE_TTS_API_KEY=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=eu-central-1
```

Файл исключён из git.

## Установка

```bash
demo/.venv/bin/pip install -r demo/tts/requirements.txt
```

## Генерация

```bash
set -a
source demo/tts/.secrets/tts.env
set +a

demo/.venv/bin/python demo/tts/test_voices.py --provider all
```

Будут созданы файлы в `demo/tts/samples/`:

- `yandex-filipp.mp3`;
- `yandex-alena.mp3`;
- `azure-dmitry.mp3`;
- `azure-svetlana.mp3`;
- `google-wavenet-d.mp3`;
- `google-wavenet-a.mp3`;
- `polly-tatyana.mp3`;
- `polly-maxim.mp3`.

## Голоса

### Yandex

- `filipp` — мужской;
- `ermil` — мужской;
- `alena` — женский;
- `jane` — женский.

### Azure

- `ru-RU-DmitryNeural`;
- `ru-RU-SvetlanaNeural`;
- `ru-RU-DariyaNeural`.

### Google

- `ru-RU-Wavenet-D` — мужской;
- `ru-RU-Wavenet-A` — женский.

### Polly

- `Tatyana` — женский;
- `Maxim` — мужской.

## Проверка

```bash
for f in demo/tts/samples/*.mp3; do
  echo "$f"
  ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$f"
done
```
