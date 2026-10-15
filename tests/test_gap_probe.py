"""Регресс-оракулы build_css (B-16, адъюдикация wave9 P3, gatetests C1–C3).

Закрывают ложно-зелёные места прошлого набора: мутации «сборка не валидирует артефакт» (M1),
«inputs_digest — константа» (M2a), «входы digest без glob шаблонов» (M2b), «_binary() всегда
SystemExit» (M4), «любой один селектор достаточен» (M6), «MAX_BYTES 35 000→40 000» (M5)
проходили старые 12 тестов — здесь они убиваются.

Происхождение: валидированные в %TEMP%-копии оракулы из адъюдикации P3
(`ADJUDICATION_WAVE9_P3_2026-10-13.md` §2); перенесены в репозиторий без изменения проверок.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_css_probe", ROOT / "scripts" / "build_css.py")
bc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bc)

SELECTORS = (".bg-surface", ".md\\:grid-cols-2", ".overflow-x-auto", ".flex-wrap",
             "prefers-reduced-motion")


def _valid_css() -> str:
    return "".join(SELECTORS) + "\n" + "/* pad */\n" * 2000


def _fake_run_factory(oversized: bool):
    def fake_run(*a, **k):
        cmd = a[0]
        target = Path(cmd[cmd.index("-o") + 1])
        css = _valid_css() + ("/* pad */\n" * 3000 if oversized else "")
        target.write_text(css, encoding="utf-8")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    return fake_run


# ── C1: путь сборки обязан валидировать артефакт и не писать манифест при отказе ──
def test_build_fails_on_oversized_artifact(monkeypatch, tmp_path):
    out = tmp_path / "app.css"
    manifest = tmp_path / "app.css.inputs.json"
    monkeypatch.setattr(bc, "OUTPUT", out)
    monkeypatch.setattr(bc, "MANIFEST", manifest)
    monkeypatch.setattr(bc, "_binary", lambda: tmp_path / "fake-tailwind")
    monkeypatch.setattr(bc.subprocess, "run", _fake_run_factory(oversized=True))
    monkeypatch.setattr(bc.sys, "argv", ["build_css.py"])

    with pytest.raises(SystemExit) as exc:
        bc.main()
    assert exc.value.code not in (None, 0), f"отказ обязан быть ненулевым (S1): {exc.value.code!r}"
    assert not manifest.exists(), "манифест свежести записан для невалидного артефакта"


def test_build_ok_writes_manifest_good_artifact(monkeypatch, tmp_path):
    """Положительный контроль того же пути: годный артефакт принимается, манифест есть."""
    out = tmp_path / "app.css"
    manifest = tmp_path / "app.css.inputs.json"
    monkeypatch.setattr(bc, "ROOT", tmp_path)  # build() печатает OUTPUT.relative_to(ROOT)
    monkeypatch.setattr(bc, "OUTPUT", out)
    monkeypatch.setattr(bc, "MANIFEST", manifest)
    monkeypatch.setattr(bc, "_binary", lambda: tmp_path / "fake-tailwind")
    monkeypatch.setattr(bc.subprocess, "run", _fake_run_factory(oversized=False))
    monkeypatch.setattr(bc.sys, "argv", ["build_css.py"])

    assert bc.main() == 0
    assert manifest.is_file() and out.is_file()


# ── C2: inputs_digest обязан быть чувствителен к каждому классу входов ──
def test_inputs_digest_sensitive_to_templates(monkeypatch, tmp_path):
    """wave12 (S2): сравнения независимы (референс пересчитывается перед каждым изменением),
    покрыты все классы входов (шаблоны: изменение/добавление/удаление; tailwind.css; tokens.css),
    проверена повторяемость digest при неизменных входах."""
    tdir = tmp_path / "templates"
    tdir.mkdir()
    inp = tmp_path / "tailwind.css"
    inp.write_text("@import 'tailwindcss';", encoding="utf-8")
    tok = tmp_path / "tokens.css"
    tok.write_text(":root { --x: 1px; }", encoding="utf-8")
    monkeypatch.setattr(bc, "INPUT", inp)
    monkeypatch.setattr(bc, "TOKENS", tok)
    monkeypatch.setattr(bc, "TEMPLATES", tdir)

    f = tdir / "x.html"
    f.write_text("<div class='flex'>", encoding="utf-8")
    d0 = bc.inputs_digest()
    assert bc.inputs_digest() == d0, "digest не повторяем при неизменных входах"
    f.write_text("<div class='flex gap-2'>", encoding="utf-8")
    d1 = bc.inputs_digest()
    assert d1 != d0, "изменение шаблона не меняет digest входов"
    new = tdir / "new.html"
    new.write_text("<p class='grid'>", encoding="utf-8")
    d2 = bc.inputs_digest()
    assert d2 != d1, "новый шаблон не попадает в digest"
    new.unlink()
    d3 = bc.inputs_digest()
    assert d3 != d2, "удаление шаблона не меняет digest"
    assert d3 == d1, "digest зависит от истории изменений, а не от состояния входов"
    inp.write_text("@import 'tailwindcss/theme';", encoding="utf-8")
    d4 = bc.inputs_digest()
    assert d4 != d3, "tailwind.css не влияет на digest"
    tok.write_text(":root { --x: 2px; }", encoding="utf-8")
    d5 = bc.inputs_digest()
    assert d5 != d4, "tokens.css не влияет на digest"


# ── C3: положительный контроль закреплённого кэша (digest сверен, загрузки нет) ──
def test_binary_accepts_cached_file_with_pinned_digest(monkeypatch, tmp_path):
    blob = b"pinned-binary"
    name = bc._asset()
    digest = hashlib.sha256(blob).hexdigest()
    monkeypatch.setattr(bc, "ASSETS", {**bc.ASSETS, name: digest})
    monkeypatch.setenv("SPENDTRACK_TAILWINDCSS_DIR", str(tmp_path))
    p = tmp_path / f"{bc.VERSION}-{name}"
    p.write_bytes(blob)

    def _no_download(*a, **k):
        pytest.fail("не должно качать: закреплённый кэш валиден")

    monkeypatch.setattr(bc, "_download", _no_download)
    assert bc._binary() == p


# ── F12b: границы бюджета и «ровно один селектор» ──
def _css_with_size(n: int) -> str:
    head = "".join(SELECTORS) + "\n"
    assert n > len(head)
    return head + "a" * (n - len(head))


def test_validate_budget_boundary(tmp_path):
    assert bc.MAX_BYTES == 35_000, "бюджет 35 000 закреплён контрактом"
    over = tmp_path / "over.css"
    over.write_text(_css_with_size(35_001), encoding="utf-8")
    assert bc._validate_artifact(over) == 1, "35 001 байт должен быть отвергнут"

    under = tmp_path / "under.css"
    under.write_text(_css_with_size(34_999), encoding="utf-8")
    assert bc._validate_artifact(under) == 0, "34 999 байт должны быть приняты"


def test_validate_rejects_single_missing_selector(tmp_path):
    css = "".join(s for s in SELECTORS if s != ".flex-wrap") + "\n" + "a" * 20_000
    thin = tmp_path / "one_missing.css"
    thin.write_text(css, encoding="utf-8")
    assert bc._validate_artifact(thin) == 1, "отсутствие одного селектора обязано отвергаться"
