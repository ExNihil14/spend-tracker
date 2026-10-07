"""F12/F13 (адъюдикация wave8, `gates`): сборщик CSS не должен рапортовать «зелёный» врустную.

F12a — свежесть: `--check` проверял размер и пять подстрок, но никак не связывал `app.css` с
входами сборки (`tailwind.css` + токены + шаблоны). Добавленная в шаблон utility-класса без
пересборки оставляла гейт зелёным — сервис отдавал CSS без этого класса.

F12b — бюджет: обычная сборка только печатала размер; лимит 35 000 и ожидаемые селекторы
проверялись исключительно в `--check`, то есть CI-проверку можно было пройти, а сборку — нет.

F13 — закреплённый CLI: найденный в кэше бинарник запускался без сверки sha256 (подмена/битый
файл принимались за закреплённую версию), а неизвестное имя asset пропускало проверку целиком.
Плюс реальная ошибка: Intel macOS получал `tailwindcss-darwin-x64`, которого нет в ASSETS
(там `tailwindcss-macos-x64`) — скачивание 404 и проверка digest отключалась.

Проверяем публичное поведение: код возврата и текст (`check()`, `_binary()`, `_asset()`).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_css", ROOT / "scripts" / "build_css.py")
bc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bc)

SELECTORS = (".bg-surface", ".md\\:grid-cols-2", ".overflow-x-auto", ".flex-wrap",
             "prefers-reduced-motion")


def _valid_css() -> str:
    """CSS, проходящий sanity-проверки: все пять селекторов и разумный размер."""
    return "".join(SELECTORS) + "\n" + "/* pad */\n" * 2000


# ─────────────────────────────── F12a: свежесть артефакта ───────────────────────────────

def test_check_fails_when_manifest_absent(monkeypatch, tmp_path):
    """Артефакт без манифеста входов → непроверяемо, гейт обязан краснеть."""
    out = tmp_path / "app.css"
    out.write_text(_valid_css(), encoding="utf-8")
    monkeypatch.setattr(bc, "OUTPUT", out)
    monkeypatch.setattr(bc, "MANIFEST", tmp_path / "app.css.inputs.json")

    assert bc.check() == 1, "сборка без манифеста входов прошла как свежая"


def test_check_fails_when_inputs_changed(monkeypatch, tmp_path):
    """Входы изменились, CSS не пересобран → гейт обязан это видеть."""
    out = tmp_path / "app.css"
    out.write_text(_valid_css(), encoding="utf-8")
    manifest = tmp_path / "app.css.inputs.json"
    manifest.write_text(json.dumps({"inputs_digest": "0" * 64}), encoding="utf-8")
    monkeypatch.setattr(bc, "OUTPUT", out)
    monkeypatch.setattr(bc, "MANIFEST", manifest)

    assert bc.check() == 1, "устаревший CSS прошёл как свежий"


def test_check_passes_when_manifest_matches(monkeypatch, tmp_path):
    """Контроль зелёного: манифест соответствует текущим входам."""
    out = tmp_path / "app.css"
    out.write_text(_valid_css(), encoding="utf-8")
    manifest = tmp_path / "app.css.inputs.json"
    manifest.write_text(json.dumps({"inputs_digest": bc.inputs_digest()}), encoding="utf-8")
    monkeypatch.setattr(bc, "OUTPUT", out)
    monkeypatch.setattr(bc, "MANIFEST", manifest)

    assert bc.check() == 0


# ─────────────────────────────── F12b: бюджет после сборки ───────────────────────────────

def test_validate_rejects_oversized_artifact(tmp_path):
    """Сборщик не должен принимать артефакт больше бюджета (F12b)."""
    big = tmp_path / "app.css"
    big.write_text(_valid_css() + "/* pad */\n" * 3000, encoding="utf-8")

    assert bc._validate_artifact(big) == 1


def test_validate_rejects_missing_selectors(tmp_path):
    """Артефакт без ожидаемых селекторов — не сборка, а мусор (F12b)."""
    thin = tmp_path / "app.css"
    thin.write_text("/* пусто */" + "/* pad */\n" * 2000, encoding="utf-8")

    assert bc._validate_artifact(thin) == 1


def test_validate_accepts_good_artifact(tmp_path):
    """Контроль: нормальный артефакт проходит валидацию."""
    good = tmp_path / "app.css"
    good.write_text(_valid_css(), encoding="utf-8")

    assert bc._validate_artifact(good) == 0


# ─────────────────────────────── F13: закреплённый CLI ───────────────────────────────

def test_asset_name_is_known():
    """Имя актива для текущей платформы обязано быть в таблице ASSETS (F13, баг macOS x64)."""
    assert bc._asset() in bc.ASSETS, f"нет digest для {bc._asset()}"


@pytest.mark.parametrize("system, machine, expected", [
    ("darwin", "x86_64", "tailwindcss-macos-x64"),
    ("darwin", "arm64", "tailwindcss-macos-arm64"),
    ("linux", "x86_64", "tailwindcss-linux-x64"),
    ("win32", "AMD64", "tailwindcss-windows-x64.exe"),
])
def test_asset_names_for_platforms(monkeypatch, system, machine, expected):
    """Таблица имён покрывает заявленные платформы (иначе digest пропускается)."""
    monkeypatch.setattr(bc.sys, "platform", system)
    monkeypatch.setattr(bc.platform, "machine", lambda: machine)

    assert bc._asset() == expected


def test_binary_rejects_cached_file_with_wrong_digest(monkeypatch, tmp_path):
    """Подложенный/битый бинарник в кэше не должен приниматься за закреплённую версию."""
    monkeypatch.setenv("SPENDTRACK_TAILWINDCSS_DIR", str(tmp_path))
    name = f"{bc.VERSION}-{bc._asset()}"
    (tmp_path / name).write_bytes(b"not a real tailwind binary")

    with pytest.raises(SystemExit):
        bc._binary()
