from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from spendtrack import taxonomy_repo as repo
from spendtrack.main import app
from spendtrack.store import Store

TAXONOMY_MIN = """[[categories]]
name = "other"
color = "#9ca3af"

[[rules]]
pattern = "ЛЕНТА"
category = "other"
"""


@pytest.fixture()
def tax_env(tmp_path, monkeypatch):
    tax = tmp_path / "taxonomy.toml"
    tax.write_text(TAXONOMY_MIN, encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(tax))
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "t.db"))
    return tax


def test_validation(tax_env):
    assert repo.validate_color("#AABBCC") == "#aabbcc"
    with pytest.raises(repo.TaxonomyError):
        repo.validate_color("red")
    with pytest.raises(repo.TaxonomyError):
        repo.validate_name("Плохое имя")
    assert repo.validate_pattern(" лента ") == "ЛЕНТА"
    with pytest.raises(repo.TaxonomyError):
        repo.validate_pattern("a")


def test_add_category_writes_backup_and_audit(tax_env):
    repo.add_category("cafe", "#112233", repo.file_hash())
    assert any(c["name"] == "cafe" for c in repo.load_raw()["categories"])
    assert tax_env.with_suffix(".toml.bak").exists()
    audit = tax_env.with_name("taxonomy_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["action"] == "add_category"
    with pytest.raises(repo.TaxonomyError):  # дубль
        repo.add_category("cafe", "#112233", None)


def test_stale_hash_conflict(tax_env):
    with pytest.raises(repo.TaxonomyError):
        repo.add_category("cafe2", "#112233", "deadbeef")


def test_delete_guard_usage(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="manual")
    with pytest.raises(repo.TaxonomyError):
        repo.delete_category("other", s, None)
    s.close()


def test_set_color(tax_env):
    repo.set_color("other", "#FFFFFF", None)
    assert repo.load_raw()["categories"][0]["color"] == "#ffffff"


# ── переименование категории (Фаза 3) ───────────────────────────────────────


def test_rename_category_migrates_toml_db_and_rules(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    tx_id = s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                              category="other", category_source="llm", category_llm="other",
                              review_status="pending", merchant="МАГНИТ")
    s.merchant_cache_set("МАГНИТ", "other")
    s.add_example("ЛЕНТА", -100, "other")
    s.set_budget("other", 20000_00)
    res = repo.rename_category("other", "general", s, repo.file_hash())
    assert res == {"old": "other", "new": "general",
                   "counts": {"transactions": 1, "proposals": 1, "cache": 1, "examples": 1,
                              "budget": 1, "rules": 1}}

    data = repo.load_raw()  # TOML: имя категории + правило
    assert data["categories"][0]["name"] == "general"
    assert data["rules"][0]["category"] == "general"
    # БД: транзакции, предложение LLM, кэш мерчантов, примеры
    assert s.conn.execute("SELECT category FROM transactions WHERE id=?", (tx_id,)).fetchone()[0] == "general"
    assert s.conn.execute("SELECT category_llm FROM transactions WHERE id=?", (tx_id,)).fetchone()[0] == "general"
    assert s.budget_map() == {"general": 20000_00}  # бюджет едет за категорией
    assert s.conn.execute("SELECT category FROM merchant_cache").fetchone()[0] == "general"
    assert s.merchant_cache_get("МАГНИТ") == "general"  # ключ кэша не зависит от категории
    assert s.conn.execute("SELECT category FROM examples").fetchone()[0] == "general"
    audit = tax_env.with_name("taxonomy_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["action"] == "rename_category"
    s.close()


def test_rename_validation_and_stale_hash(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    repo.add_category("cafe", "#112233", None)
    with pytest.raises(repo.TaxonomyError):  # имя занято
        repo.rename_category("other", "cafe", s, None)
    with pytest.raises(repo.TaxonomyError):  # невалидное имя
        repo.rename_category("other", "плохое имя", s, None)
    with pytest.raises(repo.TaxonomyError):  # категории нет
        repo.rename_category("нет-такой", "general", s, None)
    with pytest.raises(repo.TaxonomyError):  # файл изменён снаружи
        repo.rename_category("other", "general", s, "deadbeef")
    assert repo.load_raw()["categories"][0]["name"] == "other"
    s.close()


def test_rename_rollback_db_on_toml_failure(tax_env, monkeypatch):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="manual")

    def boom(*args, **kwargs):
        raise repo.TaxonomyError("disk full")

    monkeypatch.setattr(repo, "save", boom)
    with pytest.raises(repo.TaxonomyError):
        repo.rename_category("other", "general", s, None)
    assert s.conn.execute("SELECT category FROM transactions").fetchone()[0] == "other"
    assert repo.load_raw()["categories"][0]["name"] == "other"  # TOML не тронут
    s.close()


def test_rename_preview_counts(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="manual")
    p = repo.rename_preview("Other", "general", s)  # old — case-insensitive
    assert p["old"] == "other" and p["new"] == "general"
    assert p["counts"]["transactions"] == 1 and p["counts"]["rules"] == 1
    with pytest.raises(repo.TaxonomyError):  # preview со стухшим hash
        repo.rename_preview("other", "general", s, "deadbeef")
    s.close()


def test_rename_same_name_message(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    with pytest.raises(repo.TaxonomyError, match="совпадает"):  # в т.ч. смена регистра: Other = other
        repo.rename_category("other", "Other", s, None)
    s.close()


# ── бюджеты (БД) ────────────────────────────────────────────────────────────


def test_set_budget_validation_and_clear(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    repo.set_budget("other", "20000", s)
    assert s.budget_map() == {"other": 20_000_00}
    repo.set_budget("other", "12,5", s)          # запятая как разделитель
    assert s.budget_map() == {"other": 1250}
    repo.set_budget("other", "", s)              # пусто — снять
    assert s.budget_map() == {}
    repo.set_budget("other", "0", s)             # ноль — тоже снять
    assert s.budget_map() == {}
    with pytest.raises(repo.TaxonomyError):
        repo.set_budget("нет-такой", "100", s)
    with pytest.raises(repo.TaxonomyError):
        repo.set_budget("other", "abc", s)
    with pytest.raises(repo.TaxonomyError):
        repo.set_budget("other", "-5", s)
    s.close()


def test_set_budget_excluded_category(tax_env):
    tax_env.write_text('[[categories]]\nname = "income"\ncolor = "#00ff00"\n', encoding="utf-8")
    s = Store(db_path=tax_env.parent / "t.db")
    with pytest.raises(repo.TaxonomyError, match="не бюджетируется"):
        repo.set_budget("income", "1000", s)
    s.close()


def test_delete_category_removes_budget(tax_env):
    tax_env.write_text('[[categories]]\nname = "other"\ncolor = "#9ca3af"\n', encoding="utf-8")
    s = Store(db_path=tax_env.parent / "t.db")
    repo.set_budget("other", "20000", s)
    repo.delete_category("other", s, repo.file_hash())
    assert s.budget_map() == {}
    s.close()


def test_settings_budgets_api_and_page(tax_env):
    client = TestClient(app)
    html = client.get("/settings").text
    assert "Бюджеты" in html and 'id="settings-budgets"' in html

    r = client.post("/settings/budgets", data={"category": "other", "amount": "20000"})
    assert r.status_code == 200 and 'id="settings-budgets"' in r.text
    s = Store(db_path=tax_env.parent / "t.db")
    assert s.budget_map() == {"other": 20_000_00}
    s.close()

    r2 = client.post("/settings/budgets", data={"category": "other", "amount": ""})
    assert r2.status_code == 200
    s2 = Store(db_path=tax_env.parent / "t.db")
    assert s2.budget_map() == {}
    s2.close()

    r3 = client.post("/settings/budgets", data={"category": "other", "amount": "abc"})
    assert "числом" in r3.text


def test_tester_winner_and_cache(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    res = repo.test_description("ЛЕНТА 123", s)
    assert res["winner"] == "other" and res["source"] == "rule"
    assert res["matched"][0]["pattern"] == "ЛЕНТА"

    s.merchant_cache_set("ЛЕНТА 999", "other")
    res2 = repo.test_description("ЛЕНТА 999", s)
    assert res2["source"] == "merchant_cache"
    s.close()


def test_settings_page_and_add_via_api(tax_env):
    client = TestClient(app)
    html = client.get("/settings").text
    assert "Тестер описания" in html and "other" in html

    r = client.post("/settings/categories",
                    data={"name": "cafe", "color": "#112233", "file_hash": repo.file_hash()})
    assert r.status_code == 200 and "cafe" in r.text
    assert any(c["name"] == "cafe" for c in repo.load_raw()["categories"])


def test_settings_api_validation_error(tax_env):
    client = TestClient(app)
    r = client.post("/settings/categories",
                    data={"name": "bad name", "color": "#112233", "file_hash": repo.file_hash()})
    assert "имя" in r.text


def test_category_color_and_delete_routes(tax_env):
    """Роуты смены цвета и удаления категории (аудит 23.09: repo покрыт, роуты — нет)."""
    client = TestClient(app)
    client.post("/settings/categories",
                data={"name": "cafe", "color": "#112233", "file_hash": repo.file_hash()})

    r = client.post("/settings/categories/color",
                    data={"name": "cafe", "color": "#ff0000", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    colors = {c["name"]: c["color"] for c in repo.load_raw()["categories"]}
    assert colors["cafe"] == "#ff0000"

    r = client.post("/settings/categories/delete",
                    data={"name": "cafe", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    assert "cafe" not in [c["name"] for c in repo.load_raw()["categories"]]


def test_rename_api_preview_and_execute(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="manual")
    s.close()
    client = TestClient(app)
    r = client.post("/settings/categories/rename/preview",
                    data={"name": "other", "new_name": "general", "file_hash": repo.file_hash()})
    assert r.status_code == 200 and "Подтвердить" in r.text and "транзакций 1" in r.text
    assert "бюджет: 0" in r.text  # у категории бюджета нет (счётчик в preview)

    r2 = client.post("/settings/categories/rename",
                     data={"name": "other", "new_name": "general", "file_hash": repo.file_hash()})
    assert r2.status_code == 200 and "general" in r2.text
    assert repo.load_raw()["categories"][0]["name"] == "general"


def test_rename_api_errors(tax_env):
    client = TestClient(app)
    r = client.post("/settings/categories/rename/preview",
                    data={"name": "other", "new_name": "bad name"})
    assert "имя" in r.text
    r2 = client.post("/settings/categories/rename",
                     data={"name": "other", "new_name": "general", "file_hash": "deadbeef"})
    assert "изменён снаружи" in r2.text


def test_tester_endpoint(tax_env):
    client = TestClient(app)
    r = client.post("/settings/test", data={"description": "ЛЕНТА 1"})
    assert "Итог" in r.text and "other" in r.text


# ── правила: repo ───────────────────────────────────────────────────────────


def _patterns() -> list[str]:
    return [r["pattern"] for r in repo.load_raw()["rules"]]


def test_add_rule_appends_with_audit(tax_env):
    repo.add_rule("ПЯТЁРОЧКА МАГАЗИН", "other", repo.file_hash())
    assert _patterns()[-1] == "ПЯТЁРОЧКА МАГАЗИН"
    assert _patterns()[0] == "ЛЕНТА"  # старое правило не сдвинулось
    audit = tax_env.with_name("taxonomy_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["action"] == "add_rule"
    bak = tax_env.with_suffix(".toml.bak").read_text(encoding="utf-8")
    assert "ПЯТЁРОЧКА" not in bak and "ЛЕНТА" in bak  # бэкап — предыдущая версия


def test_add_rule_limit(tax_env, monkeypatch):
    monkeypatch.setattr(repo, "MAX_RULES", 1)
    with pytest.raises(repo.TaxonomyError):
        repo.add_rule("НОВОЕ ПРАВИЛО", "other", None)


def test_lowercase_pattern_dedup_and_roundtrip(tax_env):
    tax_env.write_text(TAXONOMY_MIN.replace('pattern = "ЛЕНТА"', 'pattern = "лента"'),
                       encoding="utf-8")
    with pytest.raises(repo.TaxonomyError):  # дедуп не зависит от регистра в файле
        repo.add_rule("ЛЕНТА", "other", None)
    repo.add_rule("НОВОЕ ПРАВИЛО", "other", None)  # запись не портит файл
    assert "НОВОЕ ПРАВИЛО" in tax_env.read_text(encoding="utf-8")


def test_add_rule_validation(tax_env):
    with pytest.raises(repo.TaxonomyError):
        repo.add_rule("x", "other", None)  # короткий паттерн
    with pytest.raises(repo.TaxonomyError):
        repo.add_rule("ОК ПРАВИЛО", "нет-такой", None)  # неизвестная категория
    repo.add_rule("ОК ПРАВИЛО", "other", None)
    with pytest.raises(repo.TaxonomyError):  # дубль case-insensitive
        repo.add_rule("ок правило", "other", None)


def test_rules_stale_hash(tax_env):
    repo.add_rule("ПРАВИЛО 2", "other", None)
    with pytest.raises(repo.TaxonomyError):
        repo.add_rule("ПРАВИЛО 3", "other", "deadbeef")
    with pytest.raises(repo.TaxonomyError):
        repo.delete_rule(0, "deadbeef")
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(0, "down", "deadbeef")


def test_delete_rule(tax_env):
    repo.add_rule("УДАЛИТЬ МЕНЯ", "other", None)
    idx = len(repo.load_raw()["rules"]) - 1
    repo.delete_rule(idx, repo.file_hash())
    assert "УДАЛИТЬ МЕНЯ" not in _patterns()
    audit = tax_env.with_name("taxonomy_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["action"] == "delete_rule"
    with pytest.raises(repo.TaxonomyError):
        repo.delete_rule(99, None)


def test_move_rule_swaps_and_bounds(tax_env):
    repo.add_rule("ПЕРВОЕ", "other", None)
    repo.add_rule("ВТОРОЕ", "other", None)
    repo.move_rule(2, "up", repo.file_hash())
    assert _patterns() == ["ЛЕНТА", "ВТОРОЕ", "ПЕРВОЕ"]
    repo.move_rule(1, "down", repo.file_hash())
    assert _patterns() == ["ЛЕНТА", "ПЕРВОЕ", "ВТОРОЕ"]
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(0, "up", None)
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(2, "down", None)
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(0, "sideways", None)


def test_analyze_rules_dead_duplicate_invalid(tax_env):
    tax_env.write_text(
        """[[categories]]
name = "other"
color = "#9ca3af"

[[categories]]
name = "cafe"
color = "#112233"

[[rules]]
pattern = "ЛЕНТА"
category = "other"

[[rules]]
pattern = "ЛЕНТА 24"
category = "cafe"

[[rules]]
pattern = "лЕнТа"
category = "cafe"

[[rules]]
pattern = "МАГАЗИН"
category = "missing"
""",
        encoding="utf-8",
    )
    a = repo.analyze_rules()
    assert a[0]["dead"] is False and a[0]["shadows"] == [1, 2]
    assert a[1]["shadowed_by"] == 0 and a[1]["dead"] and a[1]["duplicate_of"] is None
    assert a[2]["duplicate_of"] == 0 and a[2]["duplicate_differs"] and a[2]["dead"]
    assert a[3]["invalid_category"] and a[3]["dead"]


def test_preview_rule(tax_env):
    repo.add_rule("ЛЕНТА ОПТ", "other", None)
    p = repo.preview_rule("ЛЕНТА ОПТ 24", "other")
    assert any("будет мёртвым" in w for w in p["warnings"])
    assert any("дубль" in w for w in repo.preview_rule("лента", "other")["warnings"])
    assert repo.preview_rule("УНИКАЛЬНЫЙ ПАТТЕРН", "other")["warnings"] == []
    with pytest.raises(repo.TaxonomyError):
        repo.preview_rule("УНИКАЛЬНЫЙ ПАТТЕРН", "нет-такой")


TAXONOMY_INVALID_BLOCKER = """[[categories]]
name = "other"
color = "#9ca3af"

[[rules]]
pattern = "ЛЕНТА"
category = "missing"

[[rules]]
pattern = "ЛЕНТА 24"
category = "other"
"""


def test_analyze_ignores_invalid_blocker(tax_env):
    """Битое правило рантайм пропускает — оно не делает следующие правила мёртвыми (ревью P1)."""
    tax_env.write_text(TAXONOMY_INVALID_BLOCKER, encoding="utf-8")
    a = repo.analyze_rules()
    assert a[0]["invalid_category"] and a[0]["dead"]
    assert a[0]["shadows"] == []      # битое правило никого не перекрывает
    assert a[1]["dead"] is False      # категория #1 валидна и сработает
    assert a[1]["shadowed_by"] is None
    # превью: битое правило не пугает «будет мёртвым», валидное — пугает
    assert repo.preview_rule("ЛЕНТА 99", "other")["warnings"] == []
    assert any("будет мёртвым" in w
               for w in repo.preview_rule("ЛЕНТА 24 ОПТ", "other")["warnings"])


def test_tester_skips_invalid_rule(tax_env):
    tax_env.write_text(TAXONOMY_INVALID_BLOCKER, encoding="utf-8")
    s = Store(db_path=tax_env.parent / "t.db")
    res = repo.test_description("ЛЕНТА 24", s)
    assert [m["index"] for m in res["matched"]] == [0, 1]
    assert res["matched"][0]["valid"] is False
    assert res["winner"] == "other" and res["source"] == "rule"
    res2 = repo.test_description("ЛЕНТА 99", s)
    assert res2["winner"] is None and res2["source"] == "llm/offline"
    s.close()


# ── правила: API ────────────────────────────────────────────────────────────


def test_rules_api_add_move_delete(tax_env):
    client = TestClient(app)
    r = client.post("/settings/rules",
                    data={"pattern": "АПТЕКА 36.6", "category": "other", "file_hash": repo.file_hash()})
    assert r.status_code == 200 and 'data-pattern="АПТЕКА 36.6"' in r.text
    assert 'id="settings-rules"' in r.text  # фрагмент владеет обёрткой (повторные операции работают)
    assert _patterns()[-1] == "АПТЕКА 36.6"

    idx = len(_patterns()) - 1
    r2 = client.post("/settings/rules/move",
                     data={"index": idx, "direction": "up", "file_hash": repo.file_hash()})
    assert r2.status_code == 200 and _patterns()[idx - 1] == "АПТЕКА 36.6"

    r3 = client.post("/settings/rules/delete",
                     data={"index": idx - 1, "file_hash": repo.file_hash()})
    assert r3.status_code == 200 and "АПТЕКА 36.6" not in _patterns()


def test_rules_api_errors(tax_env):
    client = TestClient(app)
    r = client.post("/settings/rules",
                    data={"pattern": "ЛЕНТА", "category": "other", "file_hash": repo.file_hash()})
    assert "уже существует" in r.text
    r2 = client.post("/settings/rules/delete", data={"index": "abc", "file_hash": repo.file_hash()})
    assert "индекс" in r2.text
    r3 = client.post("/settings/rules/move",
                     data={"index": 0, "direction": "up", "file_hash": repo.file_hash()})
    assert "начале" in r3.text


def test_rules_preview_endpoint(tax_env):
    client = TestClient(app)
    r = client.post("/settings/rules/preview", data={"pattern": "лента", "category": "other"})
    assert "дубль" in r.text
    r2 = client.post("/settings/rules/preview", data={"pattern": "НОВЫЙ ПАТТЕРН", "category": "other"})
    assert "конфликтов не найдено" in r2.text
    r3 = client.post("/settings/rules/preview", data={"pattern": "x", "category": "other"})
    assert "конфликт" not in r3.text and "дубль" not in r3.text


def test_settings_page_shows_dead_badge(tax_env):
    repo.add_rule("ЛЕНТА ОПТ", "other", None)
    client = TestClient(app)
    html = client.get("/settings").text
    assert "мёртвое" in html and "Мёртвых правил" in html


def test_categories_fragment_owns_wrapper(tax_env):
    client = TestClient(app)
    r = client.post("/settings/categories",
                    data={"name": "cafe", "color": "#112233", "file_hash": repo.file_hash()})
    assert 'id="settings-categories"' in r.text


def test_settings_page_pending_badge(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="llm_pending_review",
                      category_llm="groceries", review_status="pending")
    s.close()
    client = TestClient(app)
    html = client.get("/settings").text
    assert re.search(r'id="pending-count"[^>]*>\s*1\s*<', html)


def test_tester_endpoint_marks_invalid_rule(tax_env):
    tax_env.write_text(TAXONOMY_INVALID_BLOCKER, encoding="utf-8")
    client = TestClient(app)
    r = client.post("/settings/test", data={"description": "ЛЕНТА 24"})
    assert "пропускается" in r.text and "other" in r.text


# ── M-7: автосохранение цвета, тост, title у «Удалить» ───────────────────────

def test_color_autosave_form_and_toast(tax_env):
    """M-7: цвет сохраняется по change (кнопки OK нет), ответ несёт OOB-тост «Сохранено»."""
    client = TestClient(app)
    html = client.get("/settings").text
    assert 'hx-trigger="change"' in html
    assert ">OK<" not in html

    r = client.post("/settings/categories/color",
                    data={"name": "other", "color": "#123456", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    assert "Сохранено" in r.text and 'hx-swap-oob="outerHTML"' in r.text
    assert {c["name"]: c["color"] for c in repo.load_raw()["categories"]}["other"] == "#123456"


def test_delete_disabled_title_shows_usage(tax_env):
    """M-7: у занятой категории title объясняет, сколько операций мешает удалению."""
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="other", category_source="manual")
    s.close()
    html = TestClient(app).get("/settings").text
    assert re.search(r'title="Используется \(\d+\) — сначала перенесите', html)
