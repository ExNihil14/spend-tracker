from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "review_script", ROOT / "scripts" / "review.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _git_repo(tmp_path: Path) -> Path:
    """Мини-репо с одним коммитом (app.py) — для проверок collect_artifacts/main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


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


def test_money_amount_with_kopecks_does_not_trip_card_scan():
    """01.10: денежная сумма с копейками («10000000000000.00») — не PAN, ложный STOP блокировал ревью.

    Строку собираем в рантайме (файл теста сам попадает в дифф и не должен ловиться сканом).
    """
    m = _mod()
    amount = f"{10**13}.00"
    assert m.secret_hits(f"- расход {amount}") == []
    assert m.secret_hits(f"amount={amount}") == []
    spaced = amount.replace(".", " .")  # «…000 .00» — редкий, но допустимый денежный формат
    assert m.secret_hits(f"- расход {spaced}") == []


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


# ---- Astra-ревью 01.10: sensitive tracked-пути, -z-разбор, prompt_sha256 ----

def test_sensitive_tracked_paths_are_blocked(tmp_path):
    """C1: изменение чувствительного tracked-файла (data/*.csv) блокирует отправку промпта."""
    m = _mod()
    repo = _git_repo(tmp_path)
    (repo / "data").mkdir()
    secret = repo / "data" / "probe.csv"
    secret.write_text("a,b\n1,2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "csv"], cwd=repo, check=True)

    secret.write_text("a,b\n3,4\n", encoding="utf-8")  # tracked-изменение чувствительного файла
    _, _, _, _, blocked = m.collect_artifacts(repo)
    assert any("probe.csv" in p for p in blocked), blocked


def test_sensitive_tracked_paths_stop_rc3(tmp_path, capsys):
    """C1: main отказывает (rc=3), а не отправляет выписку наружу."""
    m = _mod()
    repo = _git_repo(tmp_path)
    (repo / "data").mkdir()
    secret = repo / "data" / "probe.csv"
    secret.write_text("a,b\n1,2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "csv"], cwd=repo, check=True)
    secret.write_text("a,b\n3,4\n", encoding="utf-8")

    rc = m.main(["--repo", str(repo), "--dry-run", "--title", "t"])
    assert rc == 3
    assert "СТОП" in capsys.readouterr().err


def test_untracked_cyrillic_path_is_included(tmp_path):
    """O1: не-ASCII имя untracked-файла не теряется (git ls-files -z)."""
    m = _mod()
    repo = _git_repo(tmp_path)
    (repo / "проверка.py").write_text("y = 2\n", encoding="utf-8")

    _, _, extras, _, _ = m.collect_artifacts(repo)
    assert "проверка.py" in extras


def test_dry_run_reports_prompt_sha(tmp_path, capsys):
    """S7: prompt_sha256 идентифицирует ровно отправленное содержимое (включая untracked)."""
    m = _mod()
    repo = _git_repo(tmp_path)
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "новый.py").write_text("z = 3\n", encoding="utf-8")

    rc = m.main(["--repo", str(repo), "--dry-run", "--title", "t"])
    assert rc == 0
    assert "prompt_sha256=" in capsys.readouterr().out
