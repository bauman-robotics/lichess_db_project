#!/usr/bin/env python3
"""Генерация тестовых TTS-сэмплов для сравнения голосов."""
from __future__ import annotations

import argparse
import base64
import html
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
TEXT_FILE = ROOT / "sample_text.txt"

VOICES = {
    "yandex-filipp": ("yandex", "filipp"),
    "yandex-alena": ("yandex", "alena"),
    "azure-dmitry": ("azure", "ru-RU-DmitryNeural"),
    "azure-svetlana": ("azure", "ru-RU-SvetlanaNeural"),
    "google-wavenet-d": ("google", "ru-RU-Wavenet-D"),
    "google-wavenet-a": ("google", "ru-RU-Wavenet-A"),
    "polly-tatyana": ("polly", "Tatyana"),
    "polly-maxim": ("polly", "Maxim"),
}


def env(name: str, required: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise RuntimeError(f"Не задана переменная {name}")
    return value


def yandex(text: str, voice: str) -> bytes:
    response = requests.post(
        "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
        headers={
            "Authorization": "Api-Key " + env("YANDEX_API_KEY"),
            "x-folder-id": env("YANDEX_FOLDER_ID"),
        },
        data={
            "text": text,
            "lang": "ru-RU",
            "voice": voice,
            "folderId": env("YANDEX_FOLDER_ID"),
            "format": "mp3",
            "speed": os.environ.get("YANDEX_SPEED", "1.0"),
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.content


def azure(text: str, voice: str) -> bytes:
    region = env("AZURE_SPEECH_REGION")
    ssml = (
        f'<speak version="1.0" xml:lang="ru-RU">'
        f'<voice name="{html.escape(voice)}">{html.escape(text)}</voice>'
        f'</speak>'
    )
    response = requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": env("AZURE_SPEECH_KEY"),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "lichess-analyzer-tts-test",
        },
        data=ssml.encode("utf-8"),
        timeout=90,
    )
    response.raise_for_status()
    return response.content


def google(text: str, voice: str) -> bytes:
    response = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        params={"key": env("GOOGLE_TTS_API_KEY")},
        json={
            "input": {"text": text},
            "voice": {"languageCode": "ru-RU", "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95},
        },
        timeout=90,
    )
    response.raise_for_status()
    return base64.b64decode(response.json()["audioContent"])


def polly(text: str, voice: str) -> bytes:
    import boto3

    client = boto3.client(
        "polly",
        region_name=env("AWS_REGION"),
        aws_access_key_id=env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=env("AWS_SECRET_ACCESS_KEY"),
    )
    response = client.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice,
        Engine="neural",
        LanguageCode="ru-RU",
    )
    return response["AudioStream"].read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="all",
                        choices=["all", "yandex", "azure", "google", "polly"])
    parser.add_argument("--voice", action="append", default=[],
                        help="Имя файла голоса, можно несколько")
    parser.add_argument("--text-file", default=str(TEXT_FILE))
    args = parser.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    selected = [
        (name, provider, voice)
        for name, (provider, voice) in VOICES.items()
        if (args.provider == "all" or provider == args.provider)
        and (not args.voice or name in args.voice)
    ]
    if not selected:
        raise SystemExit("Нет голосов для выбранного провайдера")

    SAMPLES.mkdir(parents=True, exist_ok=True)
    for name, provider, voice in selected:
        try:
            if provider == "yandex":
                audio = yandex(text, voice)
            elif provider == "azure":
                audio = azure(text, voice)
            elif provider == "google":
                audio = google(text, voice)
            else:
                audio = polly(text, voice)
            path = SAMPLES / f"{name}.mp3"
            path.write_bytes(audio)
            print(f"✅ {path} ({len(audio)} байт)")
        except Exception as error:
            print(f"❌ {name}: {type(error).__name__}: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
