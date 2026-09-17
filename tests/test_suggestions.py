from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from spendtrack import cli
from spendtrack.suggestions import suggest_rules

TAXONOMY = """
[[categories]]
name = "groceries"
color = "#22c55e"

[[categories]]
name = "fuel"
color = "#ef4444"

[[categories]]
name = "restaurants"
color = "#f97316"

[[categories]]
name = "subscriptions"
color = "#ec4899"

[[categories]]
name = "other"
color = "#9ca3af"

[[rules]]
pattern = "ПЯТЁРОЧКА"
category = "groceries"
"""


def _use_taxonomy(monkeypatch, tmp_path, body: str = TAXONOMY) -> None:
    path = tmp_path / "taxonomy.toml"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(path))


def _add(store, description: str, category: str, *, n: int = 1, start_day: int = 1,
         merchant: str | None = None, source: str = "correction",
         category_llm: str | None = None, review_status: str = "approved") -> None:
    base = datetime(2026, 5, 1, tzinfo=UTC)
    for i in range(n):
        store.add_transaction(
            date=(base + timedelta(days=start_day + i)).strftime("%Y-%m-%d"),
            description=description, amount_kopecks=-10000, category=category,
            category_source=source, merchant=merchant, category_llm=category_llm,
            review_status=review_status,
        )


def _patterns(report: dict) -> dict[str, dict]:
    return {c["pattern"]: c for c in report["candidates"]}


def test_ngram_candidates_from_corrections(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "МАГАЗИН РОМАШКА 123", "groceries", n=4)

    report = suggest_rules(store)
    cands = _patterns(report)

    assert report["decided_rows"] == 4
    assert cands["РОМАШКА"]["type"] == "ngram"
    assert cands["РОМАШКА"]["category"] == "groceries"
    assert cands["РОМАШКА"]["confirmations"] == 4
    assert cands["РОМАШКА"]["purity"] == 1.0
    assert cands["РОМАШКА"]["status"] == "новое"
    assert "МАГАЗИН РОМАШКА" in cands  # биграмма тоже кандидат
    assert "123" not in " ".join(cands)  # цифры вычищены


def test_thresholds_filter_and_override(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "ЛАВКА СОК", "groceries", n=2)  # ниже n>=3

    assert suggest_rules(store)["candidates"] == []
    relaxed = suggest_rules(store, min_confirmations=2, min_purity=0.5)
    assert _patterns(relaxed)["ЛАВКА"]["confirmations"] == 2


def test_purity_flag_and_filter(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "КОФЕ ДОМ", "restaurants", n=4, start_day=1)
    _add(store, "КОФЕ ДОМ", "groceries", n=1, start_day=10)
    _add(store, "БАР УГОЛ", "restaurants", n=3, start_day=20)
    _add(store, "БАР УГОЛ", "groceries", n=2, start_day=30)

    cands = _patterns(suggest_rules(store))

    assert cands["КОФЕ"]["purity"] == 0.8  # 4/5 — на пороге, показываем
    assert cands["КОФЕ"]["conflicts"] == {"groceries": 1}
    assert "БАР" not in cands  # 3/5 = 0.6 — ниже порога
    assert "БАР УГОЛ" not in cands


def test_override_counted_pending_and_skipped_excluded(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "ЗАПРАВКА НЕФТЬ", "fuel", n=3, source="rule",
         category_llm="other", review_status="approved")  # человек переопределил LLM
    _add(store, "СТРОЙКА НОВАЯ", "other", n=3, source="llm_pending_review",
         category_llm="fuel", review_status="pending")  # ещё не решение
    _add(store, "ПРОПУСК ТОЖЕ", "other", n=3, source="llm_pending_review",
         category_llm="fuel", review_status="skipped")  # skip — не решение о категории

    report = suggest_rules(store)
    cands = _patterns(report)

    assert report["decided_rows"] == 3  # только overrides
    assert cands["ЗАПРАВКА"]["category"] == "fuel"
    assert "СТРОЙКА" not in cands
    assert "ПРОПУСК" not in cands


def test_examples_are_source(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    for i in range(3):
        store.add_example(f"КОФЕЙНЯ УТРО {i}", -20000, "restaurants")

    cands = _patterns(suggest_rules(store))

    assert cands["КОФЕЙНЯ"]["category"] == "restaurants"
    assert cands["КОФЕЙНЯ"]["confirmations"] == 3


def test_status_duplicate_and_dead(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "ПЯТЁРОЧКА", "groceries", n=3, start_day=1)
    _add(store, "ПЯТЁРОЧКА МОЛОКО", "groceries", n=3, start_day=10)

    cands = _patterns(suggest_rules(store))

    assert cands["ПЯТЁРОЧКА"]["status"] == "дубль"
    assert "уже есть #0" in cands["ПЯТЁРОЧКА"]["status_detail"]
    assert cands["ПЯТЁРОЧКА МОЛОКО"]["status"] == "будет мёртвым"
    assert "перехватит #0" in cands["ПЯТЁРОЧКА МОЛОКО"]["status_detail"]


def test_merchant_candidate_wins_over_ngram(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "NETFLIX.COM", "subscriptions", n=3, merchant="NETFLIX")

    cands = _patterns(suggest_rules(store))

    assert cands["NETFLIX"]["type"] == "merchant"
    assert cands["NETFLIX"]["confirmations"] == 3
    assert cands["NETFLIX"]["examples"] == []  # у merchant-кандидатов примеры не собираем


def test_cli_suggest_rules_json_and_table(monkeypatch, tmp_path, capsys, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "МАГАЗИН РОМАШКА", "groceries", n=3)
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["suggest-rules"]) == 0
    out = capsys.readouterr().out
    assert "Предложения правил" in out
    assert "РОМАШКА" in out and "новое" in out

    assert cli.main(["suggest-rules", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decided_rows"] == 3
    assert payload["min_confirmations"] == 3
    assert {c["pattern"] for c in payload["candidates"]} >= {"РОМАШКА"}


def test_patterns_longer_than_64_are_dropped(monkeypatch, tmp_path, store):
    """Контракт taxonomy: паттерн 2–64 символа — длинные биграммы отбрасываем."""
    _use_taxonomy(monkeypatch, tmp_path)
    long_a, long_b = "А" * 40, "Б" * 40  # биграмма = 81 символ
    _add(store, f"{long_a} {long_b}", "groceries", n=3)

    patterns = _patterns(suggest_rules(store))

    assert long_a in patterns and long_b in patterns  # униграммы по 40 — ок
    assert f"{long_a} {long_b}" not in patterns  # 81 > 64 — отброшено
    assert all(len(p) <= 64 for p in patterns)


def test_overlap_message_marks_existing_rule_narrower(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path, TAXONOMY.replace(
        'pattern = "ПЯТЁРОЧКА"', 'pattern = "ПЯТЁРОЧКА МОЛОКО"'))
    _add(store, "ПЯТЁРОЧКА", "groceries", n=3)

    cands = _patterns(suggest_rules(store))

    assert cands["ПЯТЁРОЧКА"]["status"] == "пересечение"
    assert "существующее правило уже" in cands["ПЯТЁРОЧКА"]["status_detail"]


def test_invalid_category_rules_do_not_shadow(monkeypatch, tmp_path, store):
    """Битое правило (категории нет в таксономии) в рантайме не срабатывает — не «дубль»."""
    body = TAXONOMY.replace('category = "groceries"', 'category = "nope"')
    _use_taxonomy(monkeypatch, tmp_path, body)
    _add(store, "ПЯТЁРОЧКА", "groceries", n=3)

    assert _patterns(suggest_rules(store))["ПЯТЁРОЧКА"]["status"] == "новое"


def test_stopword_or_digit_only_descriptions_produce_nothing(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "ООО 12345", "groceries", n=3)

    assert suggest_rules(store)["candidates"] == []


def test_merchant_conflicts_flag_and_filter(monkeypatch, tmp_path, store):
    _use_taxonomy(monkeypatch, tmp_path)
    _add(store, "АЗС ЗАПРАВКА", "fuel", n=4, merchant="АЗС")
    _add(store, "АЗС МАГАЗИН", "other", n=1, start_day=10, merchant="АЗС")

    cands = _patterns(suggest_rules(store))

    assert cands["АЗС"]["type"] == "merchant"
    assert cands["АЗС"]["purity"] == 0.8
    assert cands["АЗС"]["conflicts"] == {"other": 1}


def test_cli_suggest_rules_empty(monkeypatch, capsys, store):
    monkeypatch.setattr(cli, "make_store", lambda: store)

    assert cli.main(["suggest-rules"]) == 0
    assert "предложений нет" in capsys.readouterr().out
