"""Сборка prebuilt- CSS Tailwind (standalone CLI, без Node) → static/app.css.

Зачем: browser build (Tailwind Play CDN) официально dev-only: компилирует CSS в рантайме,
без JS стилей нет вообще, +282 КБ и FOUC. В проде отдаём готовый `app.css`.

F12/F13 (адъюдикация wave8, `gates`):
  * F12a СВЕЖЕСТЬ. `--check` знал только размер и пять подстрок, поэтому не видел связи между
    артефактом и входами: класс, добавленный в шаблон без пересборки, тихо не попадал в CSS, а
    гейт оставался зелёным. Теперь сборка пишет манифест входов (`app.css.inputs.json` с
    sha256 по СОДЕРЖИМОМУ css/токенов/шаблонов), а `--check` сверяет его. Не по mtime: перенос
    или откат не должны «освежать» артефакт, а правка входа обязана его инвалидировать.
  * F12b БЮДЖЕТ — часть успеха сборки, а не только `--check`: собираем во временный файл,
    валидируем и лишь затем подменяем артефакт.
  * F13 ЗАКРЕПЛЁННЫЙ CLI. Кэшированный бинарник раньше запускался без сверки sha256, а
    неизвестное имя asset отключало проверку целиком. Теперь digest сверяется на КАЖДОЕ
    использование, а неизвестное имя — ошибка. Попутно исправлено имя для Intel macOS:
    было `tailwindcss-darwin-x64`, которого нет в ASSETS (там `tailwindcss-macos-x64`).

Использование:
    uv run python scripts/build_css.py            # собрать (скачает CLI при необходимости)
    uv run python scripts/build_css.py --check    # проверить артефакт И его свежесть (для CI)

CLI: официальный standalone-бинарник Tailwind (пин версии + sha256), кладётся в
`D:/dev/tools/tailwindcss/` на Windows или `~/.local/share/tailwindcss/` на прочих ОС.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
SRC = ROOT / "src" / "spendtrack"
INPUT = SRC / "tailwind.css"
TOKENS = SRC / "tokens.css"
TEMPLATES = SRC / "templates"
OUTPUT = SRC / "static" / "app.css"
MANIFEST = OUTPUT.with_name(OUTPUT.name + ".inputs.json")

VERSION = "v4.3.3"
# sha256 — из GitHub API релиза (assets[].digest), проверены при первой загрузке.
ASSETS = {
    "tailwindcss-windows-x64.exe":
        "e0e260ce048014e9268f6237ff18f8ccf02cef521cbd0ae04e82c2cdf7aa3955",
    "tailwindcss-linux-x64":
        "dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a",
    "tailwindcss-macos-x64":
        "7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80bbee7e1",
    "tailwindcss-macos-arm64":
        "cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9e",
}
USER_AGENT = "spendtrack-build/1.0 (+https://github.com/ExNihil14/spend-tracker)"
NEEDLES = (".bg-surface", ".md\\:grid-cols-2", ".overflow-x-auto", ".flex-wrap",
           "prefers-reduced-motion")
MAX_BYTES = 35_000


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
    """Имя закреплённого актива для текущей платформы (F13: без `darwin`, которого нет в ASSETS)."""
    system = sys.platform
    key = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(system)
    if key is None:
        raise SystemExit(f"[build_css] неподдерживаемая платформа: {system}")
    if system == "darwin":
        return "tailwindcss-macos-arm64" if platform.machine() == "arm64" else "tailwindcss-macos-x64"
    return f"tailwindcss-{key}-x64" + (".exe" if system == "win32" else "")


def input_files() -> list[Path]:
    """Входы сборки: CSS + токены + все шаблоны (`@source` в tailwind.css сканирует templates)."""
    files = [INPUT, TOKENS]
    files += sorted(TEMPLATES.rglob("*.html")) if TEMPLATES.is_dir() else []
    return [p for p in files if p.is_file()]


def inputs_digest() -> str:
    """sha256 по содержимому входов (не по именам: переименование файла ≠ другая сборка)."""
    parts = [f"{p.as_posix()}:{hashlib.sha256(p.read_bytes()).hexdigest()}" for p in input_files()]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _expected_digest(name: str) -> str:
    """F13: неизвестное имя актива — ошибка, а не «проверку отключить»."""
    expected = ASSETS.get(name)
    if expected is None:
        raise SystemExit(f"[build_css] нет закреплённого sha256 для {name} — сборка запрещена")
    return expected


def _verify_digest(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"[build_css] sha256 не совпал для {path.name}: {actual} != {expected}")


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
    """Закреплённый CLI из кэша или из сети; digest сверяется на КАЖДОЕ использование (F13)."""
    name = _asset()
    expected = _expected_digest(name)
    path = _tool_dir() / f"{VERSION}-{name}"
    if path.is_file():
        _verify_digest(path, expected)
        return path
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{VERSION}/{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[build_css] скачиваю {url}", flush=True)
    tmp = path.with_suffix(path.suffix + ".part")
    _download(url, tmp)
    try:
        _verify_digest(tmp, expected)
    except SystemExit:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    path.chmod(path.stat().st_mode | 0o111)
    return path


def _validate_artifact(path: Path) -> int:
    """Sanity-артефакта: размер, ожидаемые селекторы, бюджет. 0 = годен."""
    if not path.is_file() or path.stat().st_size < 10_000:
        print(f"[build_css] {path.name} отсутствует или подозрительно мал", file=sys.stderr)
        return 1
    css = path.read_text(encoding="utf-8")
    for needle in NEEDLES:
        if needle not in css:
            print(f"[build_css] в {path.name} нет ожидаемого селектора {needle!r}", file=sys.stderr)
            return 1
    size = path.stat().st_size
    if size > MAX_BYTES:
        print(f"[build_css] {path.name} превышает бюджет {MAX_BYTES} байт ({size})", file=sys.stderr)
        return 1
    return 0


def build() -> None:
    """Собрать во временный файл, проверить и только затем подменить артефакт (F12b)."""
    binary = _binary()
    tmp_out = OUTPUT.with_name(OUTPUT.name + ".tmp")
    cmd = [str(binary), "-i", str(INPUT), "-o", str(tmp_out), "--minify"]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode != 0:
        tmp_out.unlink(missing_ok=True)
        raise SystemExit(f"[build_css] сборка не удалась (код {result.returncode})")
    if _validate_artifact(tmp_out) != 0:
        tmp_out.unlink(missing_ok=True)
        raise SystemExit("[build_css] собранный CSS не прошёл проверку — артефакт оставлен прежним")
    tmp_out.replace(OUTPUT)
    MANIFEST.write_text(json.dumps({"version": 1, "inputs_digest": inputs_digest(),
                                    "inputs": len(input_files())}, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"[build_css] готово: {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} байт), "
          f"манифест входов обновлён", flush=True)


def check() -> int:
    if _validate_artifact(OUTPUT) != 0:
        return 1
    if not MANIFEST.is_file():
        print(f"[build_css] нет манифеста входов ({MANIFEST.name}) — артефакт нечем проверить, "
              "пересобери: `uv run python scripts/build_css.py`", file=sys.stderr)
        return 1
    try:
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8")).get("inputs_digest")
    except (OSError, ValueError) as exc:
        print(f"[build_css] манифест входов не читается ({MANIFEST.name}): {exc}", file=sys.stderr)
        return 1
    if recorded != inputs_digest():
        print("[build_css] app.css устарел: входы сборки изменились после сборки — "
              "`uv run python scripts/build_css.py`", file=sys.stderr)
        return 1
    print(f"[build_css] check ok ({OUTPUT.stat().st_size} байт, входы совпадают)")
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
