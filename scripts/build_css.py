"""Сборка prebuilt- CSS Tailwind (standalone CLI, без Node) → static/app.css.

Зачем: browser build (Tailwind Play CDN) официально dev-only: компилирует CSS в рантайме,
без JS стилей нет вообще, +282 КБ и FOUC. В проде отдаём готовый `app.css`.

Использование:
    uv run python scripts/build_css.py            # собрать (скачает CLI при необходимости)
    uv run python scripts/build_css.py --check    # проверить, что app.css не пуст/свежий (для CI)

CLI: официальный standalone-бинарник Tailwind (пин версии + sha256), кладётся в
`D:/dev/tools/tailwindcss/` на Windows или `~/.local/share/tailwindcss/` на прочих ОС.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "src" / "spendtrack" / "tailwind.css"
OUTPUT = ROOT / "src" / "spendtrack" / "static" / "app.css"

VERSION = "v4.3.3"
# sha256 — из GitHub API релиза (assets[].digest), проверены при первой загрузке.
ASSETS = {
    "tailwindcss-windows-x64.exe":
        "e0e260ce048014e9268f6237ff18f8ccf02cef521cbd0ae04e82c2cdf7aa3955",
    "tailwindcss-linux-x64":
        "dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a",
    "tailwindcss-macos-x64":
        "7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80cbee7e1",
    "tailwindcss-macos-arm64":
        "cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d",
}
USER_AGENT = "spendtrack-build/1.0 (+https://github.com/ExNihil14/spend-tracker)"


def _tool_dir() -> Path:
    """Кэш CLI: env-override → user-dir (кросс-платформенно, без хардкода машинных путей)."""
    override = os.environ.get("SPENDTRACK_TAILWINDCSS_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "spendtrack" / "tailwindcss"


def _asset() -> str:
    key = {"win32": "windows", "linux": "linux", "darwin": "darwin"}[sys.platform]
    if key == "darwin" and platform.machine() == "arm64":
        return "tailwindcss-macos-arm64"
    return f"tailwindcss-{key}-x64" + (".exe" if key == "windows" else "")


def _download(url: str, dest: Path) -> None:
    """Скачивание с User-Agent и ретраями; urllib сам учитывает HTTP(S)_PROXY из окружения."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=300) as resp, dest.open("wb") as out:
                shutil.copyfileobj(resp, out)
            return
        except Exception as exc:  # noqa: BLE001 — ретраим сеть/5xx, сохраняем последнюю ошибку
            last_error = exc
            print(f"[build_css] попытка {attempt} не удалась: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise SystemExit(f"[build_css] не удалось скачать {url}: {last_error}")


def _binary() -> Path:
    name = _asset()
    path = _tool_dir() / f"{VERSION}-{name}"
    if path.is_file():
        return path
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{VERSION}/{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[build_css] скачиваю {url}", flush=True)
    tmp = path.with_suffix(path.suffix + ".part")
    _download(url, tmp)
    expected = ASSETS.get(name)
    if expected:
        actual = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if actual != expected:
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"[build_css] sha256 не совпал: {actual} != {expected}")
    tmp.replace(path)
    path.chmod(path.stat().st_mode | 0o111)
    return path


def build() -> None:
    binary = _binary()
    cmd = [str(binary), "-i", str(INPUT), "-o", str(OUTPUT), "--minify"]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"[build_css] сборка не удалась (код {result.returncode})")
    size = OUTPUT.stat().st_size
    print(f"[build_css] готово: {OUTPUT.relative_to(ROOT)} ({size} байт)", flush=True)


def check() -> int:
    if not OUTPUT.is_file() or OUTPUT.stat().st_size < 10_000:
        print("[build_css] app.css отсутствует или подозрительно мал", file=sys.stderr)
        return 1
    css = OUTPUT.read_text(encoding="utf-8")
    for needle in (".bg-slate-950", ".md\\:grid-cols-2", ".overflow-x-auto", ".flex-wrap"):
        if needle not in css:
            print(f"[build_css] в app.css нет ожидаемого селектора {needle!r}", file=sys.stderr)
            return 1
    print(f"[build_css] check ok ({OUTPUT.stat().st_size} байт)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prebuilt CSS для spend-tracker (Tailwind standalone CLI)")
    parser.add_argument("--check", action="store_true", help="только проверка артефакта (без сборки)")
    args = parser.parse_args()
    if args.check:
        return check()
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
