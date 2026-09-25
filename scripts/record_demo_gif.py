"""Собрать лендинг-GIF «импорт → подтвердить → дайджест» из demo-БД (Playwright + Pillow, оффлайн).

Запуск:
    uv run python scripts/record_demo_gif.py [--out landing/assets/demo.gif] [--port 8795]

Скрипт берёт **изолированную копию** demo-БД (или сеет свежую), поднимает временный uvicorn,
снимает 4 ключевых кадра в Chromium, накладывает подписи и собирает GIF (960px).
Прод и реальные БД не трогаются: принимается только БД с именем `demo.db` (иначе — ошибка).
Данные синтетические (`scripts/demo_data.py`).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DB = ROOT / "data" / "demo.db"
DEFAULT_OUT = ROOT / "landing" / "assets" / "demo.gif"
WIDTH = 960
FRAME_SECONDS = 1.8

DEMO_CSV = (
    "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;Валюта операции;"
    "Категория;Описание\n"
    "9001;24.09.2026;1234;Выполнено;-549,90;RUB;Супермаркеты;ЛЕНТА 077\n"
    "9002;25.09.2026;1234;Выполнено;-320,00;RUB;Кафе;КАФЕ МОЛОКО\n"
    "9003;25.09.2026;1234;Выполнено;-890,00;RUB;АЗС;АЗС ЛУКОЙЛ 22\n"
)
CAPTIONS = (
    "1. Импорт выписки — вставьте CSV",
    "2. Отчёт: добавлено / пропущено",
    "3. Спорное — подтверждение в один клик",
    "4. Дайджест недели и аномалии",
)


def is_demo_db(path: Path) -> bool:
    """Страховка от съёмки на реальной БД: принимаем только `demo.db`."""
    return Path(path).name == "demo.db"


def prepare_work_db(source: Path, work_dir: Path) -> Path:
    """Копия demo-БД в temp (съёмка не мутирует исходник); нет исходника — сеем свежую."""
    work = work_dir / "demo.db"
    if source.exists():
        shutil.copy2(source, work)
    else:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_data.py"),
                        "seed", "--db", str(work)], cwd=ROOT, check=True)
    return work


def start_server(db: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = {**os.environ, "SPENDTRACK_DB_PATH": str(db)}
    log = open(log_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115 — живёт до конца процесса
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "spendtrack.main:app",
                             "--port", str(port)], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0).status_code == 200:
                return proc
        except Exception:  # noqa: BLE001, S110 — стенд ещё не поднялся (ожидаемо)
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    stop_server(proc)
    log.flush()
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
    log.close()
    raise SystemExit(f"стенд не поднялся (порт {port}) — лог:\n{tail}")


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def capture_frames(base: str, out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    frames: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        try:
            page.goto(base + "/")
            page.wait_for_load_state("networkidle")
            page.click('button[data-toggle="import-panel"]')
            page.fill('#import-panel textarea[name="csv"]', DEMO_CSV)
            page.wait_for_timeout(300)
            frames.append(_shot(page, out_dir, "1-import"))

            page.click('#import-form button:has-text("Импортировать")')  # type="submit" в шаблоне не задан
            page.wait_for_selector("#importmsg:not(:empty)", timeout=15_000)
            page.wait_for_timeout(400)
            frames.append(_shot(page, out_dir, "2-result"))

            page.goto(base + "/approve")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".review-approve")
            page.locator(".review-approve").first.click()
            page.wait_for_timeout(700)
            frames.append(_shot(page, out_dir, "3-approve"))

            page.goto(base + "/dashboard")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("#digest-card")
            page.locator("#digest-card").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            frames.append(_shot(page, out_dir, "4-digest"))
        finally:
            browser.close()
    return frames


def _shot(page, out_dir: Path, name: str) -> Path:
    path = out_dir / f"{name}.png"
    page.screenshot(path=str(path))
    return path


def _with_caption(img, caption: str):
    """Тёмная плашка с подписью внизу кадра (для GIF без альтернативного текста)."""
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    bar_h = 54
    draw.rectangle((0, img.height - bar_h, img.width, img.height), fill=(15, 23, 42))
    try:
        font = ImageFont.truetype("segoeui.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, img.height - bar_h + 14), caption, fill=(241, 245, 249), font=font)
    return img


def assemble_gif(frames: list[Path], out: Path, *, width: int = WIDTH,
                 seconds: float = FRAME_SECONDS, captions: tuple[str, ...] = ()) -> Path:
    """Кадры → GIF (960px, палитра 256, цикл). Чистая функция — тестируется без браузера/сети."""
    from PIL import Image

    imgs = []
    for i, frame in enumerate(frames):
        with Image.open(frame) as src:  # закрываем дескриптор: данные дальше — в памяти
            im = src.convert("RGB")
        if im.width != width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        if i < len(captions):
            im = _with_caption(im, captions[i])
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=256))
    if not imgs:
        raise ValueError("нет кадров")
    out.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(out, save_all=True, append_images=imgs[1:],
                 duration=int(seconds * 1000), loop=0, optimize=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Собрать demo.gif для лендинга (Playwright + Pillow)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DEMO_DB, help="исходная demo-БД (только demo.db)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--port", type=int, default=8795)
    args = ap.parse_args(argv)

    if not is_demo_db(args.db):
        raise SystemExit(f"отказ: {args.db.name!r} — это не demo.db (реальная БД не снимается)")

    with tempfile.TemporaryDirectory(prefix="demo-gif-") as tmp:
        work_dir = Path(tmp)
        work_db = prepare_work_db(args.db, work_dir)
        proc = start_server(work_db, args.port, log_path=work_dir / "server.log")
        try:
            try:
                frames = capture_frames(f"http://127.0.0.1:{args.port}", work_dir)
            except Exception as e:  # понятная ошибка вместо стектрейса (дальше re-raise)
                raise SystemExit(f"съёмка не удалась: {type(e).__name__}: {e}") from e
        finally:
            stop_server(proc)
        out = assemble_gif(frames, args.out, captions=CAPTIONS)

    size_kb = out.stat().st_size // 1024
    print(f"OK {out} ({size_kb} КБ, кадров {len(frames)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
