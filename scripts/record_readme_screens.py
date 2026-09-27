"""Пересъёмка статичных скриншотов README из demo-БД (Playwright, оффлайн).

Запуск:
    uv run python scripts/record_readme_screens.py [--db data/demo.db] [--port 8796] [--out-dir assets]

Скрипт берёт **изолированную копию** demo-БД (или сеет свежую), поднимает временный uvicorn и снимает
три кадра 1280px для README: список расходов (видоискатель 1500px), «Настройки», «Дашборд».
Прод и реальные БД не трогаются: принимается только БД с именем `demo.db` (страховка от съёмки на живой БД).
Данные синтетические (`scripts/demo_data.py`), сервер и браузер — локальные.

Регресс имён: `tests/test_readme_screens.py` сверяет план съёмки с картинками, на которые ссылается README.
"""
from __future__ import annotations

import argparse
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DB = ROOT / "data" / "demo.db"
DEFAULT_OUT_DIR = ROOT / "assets"
VIEWPORT_WIDTH = 1280

# (имя файла в out-dir, путь, высота видоискателя) — имена фиксированы README-ссылками
PLAN: tuple[tuple[str, str, int], ...] = (
    ("screenshot-transactions.png", "/", 1500),
    ("screenshot-settings.png", "/settings", 900),
    ("screenshot-dashboard.png", "/dashboard", 900),
)


def _gif_helpers():
    """Helpers временного стенда из record_demo_gif.py (тот же контур demo.db)."""
    spec = importlib.util.spec_from_file_location("record_demo_gif", ROOT / "scripts" / "record_demo_gif.py")
    assert spec and spec.loader, "record_demo_gif.py не найден"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def capture(base: str, out_dir: Path) -> list[Path]:
    """Снять план кадров; Chromium, 1280px, синтетика. Возвращает пути файлов."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, url, height in PLAN:
                page = browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": height},
                                        device_scale_factor=1)
                try:
                    page.goto(base + url)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(300)  # htmx-догрузка частей страницы
                    path = out_dir / name
                    page.screenshot(path=str(path))  # видоискатель, без full_page
                    shots.append(path)
                finally:
                    page.close()
        finally:
            browser.close()
    return shots


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Скриншоты README из demo-БД (Playwright, оффлайн)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DEMO_DB, help="исходная demo-БД (только demo.db)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--port", type=int, default=8796)
    args = ap.parse_args(argv)

    helpers = _gif_helpers()
    if not helpers.is_demo_db(args.db):
        raise SystemExit(f"отказ: {args.db.name!r} — это не demo.db (реальная БД не снимается)")

    with tempfile.TemporaryDirectory(prefix="readme-shots-") as tmp:
        work_dir = Path(tmp)
        work_db = helpers.prepare_work_db(args.db, work_dir)
        proc = helpers.start_server(work_db, args.port, log_path=work_dir / "server.log")
        try:
            try:
                shots = capture(f"http://127.0.0.1:{args.port}", args.out_dir)
            except Exception as e:  # понятная ошибка вместо стектрейса
                raise SystemExit(f"съёмка не удалась: {type(e).__name__}: {e}") from e
        finally:
            helpers.stop_server(proc)

    for shot in shots:
        print(f"OK {shot} ({shot.stat().st_size // 1024} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
