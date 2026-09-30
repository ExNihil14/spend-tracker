from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "review_script", ROOT / "scripts" / "review.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_load_checklist_falls_back_to_embedded(tmp_path):
    text = _mod().load_checklist(tmp_path / "missing.md")

    assert "Контракт-дельта" in text
    assert "10." in text


def test_render_prompt_contains_checklist_plan_and_artifacts():
    m = _mod()
    prompt = m.render_prompt(
        title="Тестовая задача",
        checklist="1. Проверить границы",
        notes="проверено фактом: 275 unit зелёные",
        diff_stat=" a.py | 2 +-",
        diff="diff --git a/a.py b/a.py\n+new line",
        extras={"new_module.py": "def f() -> int:\n    return 1\n"},
        skipped=["secret.env"],
    )

    assert "# Что ревьюится: Тестовая задача" in prompt
    assert "1. Проверить границы" in prompt
    assert "P0/P1" in prompt
    assert "только блокирующие мерж" in prompt
    assert "не удалось подтвердить" in prompt
    assert "проверено фактом: 275 unit зелёные" in prompt
    assert "+new line" in prompt
    assert "new_module.py" in prompt
    assert "не включены файлы" in prompt and "secret.env" in prompt


def test_secret_hits_masked_and_clean():
    """§C4/S7: перед отправкой наружу промпт сканируется на секрет-паттерны."""
    m = _mod()
    assert m.secret_hits("обычный текст без секретов") == []
    hits = m.secret_hits("token sk-" + "a" * 24 + " конец")
    assert hits and hits[0].startswith("sk-") and "…" in hits[0]
    assert m._is_sensitive(".env")
    assert m._is_sensitive("tests/fixtures/real_statement.csv")
    assert m._is_sensitive("settings.local.toml")
    assert not m._is_sensitive("src/spendtrack/store.py")


def test_sensitive_paths_cover_data_and_financial_files():
    """Ревью Opus 5.5: data/**, tests/fixtures/**, *.csv/*.sqlite/*.db не уходят в бесплатные каналы."""
    m = _mod()
    for path in ("data/spend.db", "tests/fixtures/statement.csv", "statement.csv",
                 "backup.sqlite", "x.db"):
        assert m._is_sensitive(path), path
    assert not m._is_sensitive("src/spendtrack/csv_import.py")


def test_card_like_pii_is_blocked():
    m = _mod()
    # номер собираем в рантайме: сам файл теста не должен ловиться сканом, когда попадает в дифф
    sample = " ".join(map(str, (4276, 3800, 1234, 5678)))
    hits = m.secret_hits(f"карта {sample} до востребования")
    assert hits, "номер карты должен ловиться"
    short = " ".join(map(str, (4276, 3800, 123, 456)))  # 13 цифр — тоже карта
    assert m.secret_hits(f"карта {short} до востребования"), "13-значный номер должен ловиться"


def test_card_with_trailing_digits_is_blocked():
    """Ревью Sonnet 5.5 (30.09): карта + хвостовые цифры («12/26», CVV) не должна проскакивать.

    Регресс фикса ложного SVG-срабатывания: жадный захват съедал « 12», у кандидата получалось
    2 группы → валидация отвергала. Короткие крайние группы отбрасываются до проверки.
    """
    m = _mod()
    long_plus = " ".join(map(str, (4111, 1111, 1111, 1111))) + " 12"  # 16 цифр + «12/26»
    assert m.secret_hits(f"карта {long_plus}/26 до востребования"), "карта с датой не поймана"
    tail1 = " ".join(map(str, (4111, 1111, 1111, 1111))) + " 1"
    assert m.secret_hits(f"карта {tail1} до востребования"), "карта + 1 цифра не поймана"


def test_svg_path_digits_do_not_trip_card_scan():
    """Live 30.09: SVG path иконок («4 4 0 1 1-8…») — не карта; ложный STOP блокировал ревью UI-диффов.

    Реальная карта — группы по ≥3 цифр (4/4/4/4, 4/6/5) или 13–19 цифр подряд; россыпь одиночных
    цифр с пробелами (координаты path) картой не является.
    """
    m = _mod()
    svg = 'd="M10 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1Zm4 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z"'
    assert m.secret_hits(svg) == []


def test_generated_paths_excluded_from_diff_size():
    m = _mod()
    assert m._is_generated("uv.lock")
    assert m._is_generated("src/spendtrack/static/app.css")
    assert m._is_generated("build/static/app.css")  # имя файла, не путь — устойчиво к переносу
    assert m._is_generated("src/spendtrack/static/htmx.min.js")
    assert m._is_generated("spec/ratchet_baseline.json")
    assert not m._is_generated("src/spendtrack/store.py")


def test_summarize_numstat_ignores_binary_and_generated():
    m = _mod()
    text = ("10\t2\tsrc/spendtrack/store.py\n"
            "500\t0\tuv.lock\n"
            "-\t-\tassets/x.png\n"
            "3\t1\tspec/cc_baseline.json\n"
            "мусорная строка\n")
    total, rows = m.summarize_numstat(text)

    assert total == 12
    assert rows == [(12, "src/spendtrack/store.py")]
