#!/usr/bin/env python3
"""Запись демонстрационного видео по YAML-сценарию через Playwright."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

DEMO_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEMO_DIR.parent
BROWSERS_DIR = DEMO_DIR / ".cache" / "ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))

from playwright.sync_api import sync_playwright  # noqa: E402


def wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Сервер не отвечает: {url}")


def resolve_url(base_url: str, value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return base_url.rstrip("/") + "/" + value.lstrip("/")


def target_point(page, step: dict) -> tuple[float, float]:
    selector = step.get("selector")
    if selector:
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=15000)
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if not box:
            raise RuntimeError(f"Не удалось получить координаты: {selector}")
        rel = step.get("relative")
        if rel:
            return (
                box["x"] + box["width"] * float(rel.get("x", 0.5)),
                box["y"] + box["height"] * float(rel.get("y", 0.5)),
            )
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    if "x" in step and "y" in step:
        return float(step["x"]), float(step["y"])
    raise RuntimeError(f"Нужен selector или x/y: {step}")


def move_mouse(page, x: float, y: float, duration_ms: int) -> None:
    steps = max(1, int(duration_ms / 16))
    page.mouse.move(x, y, steps=steps)
    page.wait_for_timeout(80)


def run_step(page, step: dict, defaults: dict, base_url: str) -> None:
    if "goto" in step:
        page.goto(resolve_url(base_url, step["goto"]), wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        return

    if "wait_for" in step:
        page.locator(step["wait_for"]).first.wait_for(state="visible", timeout=15000)
        return

    if "caption" in step:
        page.evaluate("(text) => window.__demoSetCaption(text)", step.get("caption") or "")
        return

    if "move_to" in step:
        args = step["move_to"]
        duration = int(args.get("duration", defaults.get("move_ms", 450)))
        x, y = target_point(page, args)
        move_mouse(page, x, y, duration)
        return

    if "click" in step:
        args = step["click"] if isinstance(step["click"], dict) else {"selector": step["click"]}
        duration = int(args.get("duration", defaults.get("move_ms", 450)))
        x, y = target_point(page, args)
        move_mouse(page, x, y, duration)
        page.mouse.click(x, y)
        return

    if "type" in step:
        args = step["type"]
        selector = args["selector"]
        x, y = target_point(page, args)
        move_mouse(page, x, y, int(defaults.get("move_ms", 450)))
        page.mouse.click(x, y)
        if args.get("clear"):
            page.keyboard.press("Control+A")
        page.keyboard.type(args.get("text", ""), delay=int(args.get("delay", 45)))
        return

    if "press" in step:
        page.keyboard.press(step["press"])
        return

    if "scroll" in step:
        args = step["scroll"]
        page.mouse.wheel(int(args.get("x", 0)), int(args.get("y", 500)))
        return

    if "wait_hidden" in step:
        page.locator(step["wait_hidden"]).first.wait_for(state="hidden", timeout=15000)
        return

    if "scroll_to" in step:
        page.locator(step["scroll_to"]).first.scroll_into_view_if_needed()
        page.wait_for_timeout(350)
        return

    if "highlight" in step:
        args = step["highlight"] if isinstance(step["highlight"], dict) else {"selector": step["highlight"]}
        locator = page.locator(args["selector"]).first
        locator.wait_for(state="visible", timeout=15000)
        locator.scroll_into_view_if_needed()
        locator.evaluate("el => el.classList.add('demo-highlight')")
        page.wait_for_timeout(int(args.get("duration", 1000)))
        locator.evaluate("el => el.classList.remove('demo-highlight')")
        return

    if "check" in step:
        args = step["check"] if isinstance(step["check"], dict) else {"selector": step["check"]}
        page.locator(args["selector"]).first.check()
        return

    if "select" in step:
        args = step["select"]
        page.locator(args["selector"]).first.select_option(args["value"])
        return

    if "copy_text" in step:
        page.evaluate(
            """(text) => {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                let ok = false;
                try { ok = document.execCommand('copy'); } catch (e) {}
                ta.remove();
                return ok;
            }""",
            str(step["copy_text"]),
        )
        return

    if "notepad" in step:
        args = step["notepad"] if isinstance(step["notepad"], dict) else {}
        text = page.evaluate("() => navigator.clipboard.readText()")
        page.evaluate(
            "([text, title]) => window.__demoNotepad(text, title)",
            [text, args.get("title", "Буфер обмена")],
        )
        return

    if "hide_notepad" in step:
        page.evaluate("() => window.__demoHideNotepad()")
        return

    if "chart_click" in step:
        args = step["chart_click"]
        point = page.evaluate(
            """([selector, index, datasetIndex]) => {
                const canvas = document.querySelector(selector);
                if (!canvas || typeof Chart === 'undefined') return null;
                const chart = Chart.getChart(canvas);
                if (!chart) return null;
                const ds = chart.data.datasets[datasetIndex || 0];
                const points = chart.getDatasetMeta(datasetIndex || 0).data;
                if (!ds || !points || !points.length) return null;
                const i = index === 'last' ? points.length - 1 : Number(index || 0);
                const p = points[Math.max(0, Math.min(i, points.length - 1))];
                if (!p) return null;
                const rect = canvas.getBoundingClientRect();
                return {x: rect.left + p.x, y: rect.top + p.y};
            }""",
            [args["selector"], args.get("index", 0), args.get("dataset", 0)],
        )
        if not point:
            raise RuntimeError("Не удалось найти точку на графике")
        move_mouse(page, point["x"], point["y"], int(defaults.get("move_ms", 450)))
        page.mouse.click(point["x"], point["y"])
        return

    if "pause" in step:
        page.wait_for_timeout(int(step["pause"]))
        return

    raise RuntimeError(f"Неизвестный шаг: {json.dumps(step, ensure_ascii=False)}")


def record(config_path: Path, base_url_override: str | None, output_override: str | None) -> Path:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base_url = base_url_override or config.get("base_url", "http://127.0.0.1:5555")
    video_cfg = config.get("video", {})
    width = int(video_cfg.get("width", 1920))
    height = int(video_cfg.get("height", 1080))
    fps = int(video_cfg.get("fps", 30))
    defaults = config.get("defaults", {})

    output = Path(output_override or config.get("output", "demo/output/demo.mp4"))
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    temp_video_dir = output.parent / ".playwright-video"
    shutil.rmtree(temp_video_dir, ignore_errors=True)
    temp_video_dir.mkdir(parents=True, exist_ok=True)

    wait_for_server(base_url)
    print(f"▶ Сценарий: {config_path.name}")
    print(f"▶ Размер: {width}×{height}, {fps} fps")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--hide-scrollbars", "--force-device-scale-factor=1"],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            screen={"width": width, "height": height},
            device_scale_factor=1,
            locale="ru-RU",
            permissions=["clipboard-read", "clipboard-write"],
            record_video_dir=str(temp_video_dir),
            record_video_size={"width": width, "height": height},
        )
        context.add_init_script(path=str(DEMO_DIR / "cursor.js"))
        page = context.new_page()
        page.set_default_timeout(15000)
        video = page.video
        video_path = None

        try:
            for scene in config.get("scenes", []):
                print(f"  • {scene.get('name', 'сцена')}")
                for step in scene.get("steps", []):
                    try:
                        run_step(page, step, defaults, base_url)
                    except Exception:
                        print(f"    URL при ошибке: {page.url}")
                        raise
                    page.wait_for_timeout(int(defaults.get("pause", 200)))
        finally:
            if video is not None:
                video_path = Path(video.path())
            context.close()
            browser.close()

    raw_video = video_path
    if not raw_video.exists():
        raise RuntimeError(f"Playwright не сохранил видео: {raw_video}")

    if output.suffix.lower() == ".webm":
        shutil.copy2(raw_video, output)
    else:
        print("▶ Конвертация в MP4 через ffmpeg…")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(raw_video),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-an",
                "-loglevel", "error",
                "-movflags", "+faststart", str(output),
            ],
            check=True,
        )
    shutil.rmtree(temp_video_dir, ignore_errors=True)
    print(f"✅ Готово: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Запись демо-видео сервиса")
    parser.add_argument("--scenario", default="demo/scenarios/test.yaml")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config_path = Path(args.scenario)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    try:
        record(config_path, args.base_url, args.output)
        return 0
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
