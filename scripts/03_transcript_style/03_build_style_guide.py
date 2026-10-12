#!/usr/bin/env python3
"""
Свод стилевых маркеров в единый гайд (DeepSeek v4-pro).

Читает:  data/chess_transcripts/markers/*_markers.md
Пишет:   data/chess_transcripts/style_guide.md
Промпт:  config/prompts/build_style_guide.txt

Запуск (из корня проекта):
    python scripts/03_transcript_style/03_build_style_guide.py
    python scripts/03_transcript_style/03_build_style_guide.py --force
    python scripts/03_transcript_style/03_build_style_guide.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "data" / "chess_transcripts" / "markers"
OUTPUT_FILE = PROJECT_ROOT / "data" / "chess_transcripts" / "style_guide.md"
PROMPT_FILE = PROJECT_ROOT / "config" / "prompts" / "build_style_guide.txt"

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-pro"
MAX_TOKENS = 10000
TEMPERATURE = 0.4
TIMEOUT = 600
RETRIES = 3


def _candidate_env_names():
    return ["DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "DEEPSEEK_TOKEN",
            "DEEPSEEK_SECRET", "API_KEY"]


def _parse_env_file(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _parse_secrets_yaml(path):
    if not path.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    for candidate in (
        (data.get("deepseek") or {}).get("api_key"),
        data.get("deepseek_api_key"),
        data.get("api_key"),
    ):
        if candidate:
            return str(candidate).strip()
    return None


def load_api_key():
    env = _parse_env_file(PROJECT_ROOT / ".env")
    for name in _candidate_env_names():
        if env.get(name):
            return env[name]
    for secrets_path in (
        PROJECT_ROOT / "config" / "secrets.yaml",
        PROJECT_ROOT / "secrets.yaml",
    ):
        key = _parse_secrets_yaml(secrets_path)
        if key:
            return key
    return None


def _post(payload, api_key):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def call_llm(system, user, api_key):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
    }
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            data = _post(payload, api_key)
            content = (data["choices"][0]["message"].get("content") or "").strip()
            if not content:
                raise RuntimeError("пустой ответ")
            return content
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                wait = 2 ** attempt
                print(f"  HTTP {e.code}, retry через {wait}с...", flush=True)
                time.sleep(wait)
                last_err = RuntimeError(f"HTTP {e.code}: {body}")
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}") from e
        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                wait = 2 ** attempt
                print(f"  {type(e).__name__}: {e}, retry через {wait}с...", flush=True)
                time.sleep(wait)
                continue
            raise
    raise last_err or RuntimeError("неизвестная ошибка")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="перезаписать style_guide.md")
    parser.add_argument("--dry-run", action="store_true", help="без вызовов API")
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key and not args.dry_run:
        print("[FAIL] API-ключ не найден")
        return 1
    if api_key:
        print(f"[OK] ключ: {api_key[:10]}...")

    if not PROMPT_FILE.exists():
        print(f"[FAIL] промпт не найден: {PROMPT_FILE}")
        return 1
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    print(f"[OK] промпт: {len(system_prompt)} символов")

    markers_files = sorted(INPUT_DIR.glob("*_markers.md"))
    if not markers_files:
        print(f"[FAIL] нет маркеров в {INPUT_DIR}")
        return 1
    print(f"[OK] маркеров: {len(markers_files)}")

    parts = []
    for i, f in enumerate(markers_files, 1):
        text = f.read_text(encoding="utf-8").strip()
        parts.append(f"### Файл {i}: {f.stem}\n\n{text}")
    user_prompt = (
        f"Ниже — {len(markers_files)} наборов стилевых маркеров.\n\n"
        + "\n\n---\n\n".join(parts)
    )
    print(f"[OK] user-промпт: {len(user_prompt)} символов")

    if args.dry_run:
        print("[DRY-RUN] вызов API пропущен")
        return 0

    if OUTPUT_FILE.exists() and not args.force:
        print(f"[SKIP] {OUTPUT_FILE} уже есть (--force для перезаписи)")
        return 0

    print("Запрос к v4-pro...", flush=True)
    t0 = time.time()
    try:
        guide = call_llm(system_prompt, user_prompt, api_key)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 2
    OUTPUT_FILE.write_text(guide.rstrip() + "\n", encoding="utf-8")
    print(f"[OK] сохранено: {OUTPUT_FILE} ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
