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

[[categories]]
name = "cafe"
color = "#112233"

[[rules]]
pattern = "ЛЕНТА"
category = "other"

[[rules]]
pattern = "КОФЕ"
category = "cafe"
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
    repo.add_category("cafe2", "#112233", repo.file_hash())
    assert any(c["name"] == "cafe2" for c in repo.load_raw()["categories"])
    assert tax_env.with_suffix(".toml.bak").exists()
    audit = tax_env.with_name("taxonomy_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit[-1])["action"] == "add_category"
    with pytest.raises(repo.TaxonomyError):  # дубль
        repo.add_category("cafe2", "#112233", None)


def test_stale_hash_conflict(tax_env):
    with pytest.raises(repo.TaxonomyError):
        repo.add_category("cafe2", "#112233", "deadbeef")


def test_delete_guard_usage(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="cafe", category_source="manual")
    with pytest.raises(repo.TaxonomyError):
        repo.delete_category("cafe", s, None)
    s.close()


def test_delete_category_refuses_last_one(tmp_path, monkeypatch):
    """C2 (ревью LLM-шва, 28.09): удаление последней категории запрещено — иначе конфиг без
    [[categories]] роняет load_taxonomy и все страницы."""
    tax = tmp_path / "taxonomy.toml"
    tax.write_text('[[categories]]\nname = "cafe"\ncolor = "#9ca3af"\n', encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(tax))
    s = Store(db_path=tmp_path / "t.db")
    with pytest.raises(repo.TaxonomyError, match="последнюю"):
        repo.delete_category("cafe", s, None)
    s.close()


def test_load_taxonomy_tolerates_ui_made_configs(tmp_path):
    """C2: конфиг без [[rules]], без color и совсем пустой не должен ронять приложение."""
    from spendtrack.taxonomy import load_taxonomy

    only_cats = tmp_path / "a" / "taxonomy.toml"
    only_cats.parent.mkdir()
    only_cats.write_text('[[categories]]\nname = "other"\ncolor = "#9ca3af"\n', encoding="utf-8")
    tax = load_taxonomy(only_cats.parent)
    assert [c.name for c in tax.categories] == ["other"]
    assert tax.rules == []

    no_color = tmp_path / "b" / "taxonomy.toml"
    no_color.parent.mkdir()
    no_color.write_text('[[categories]]\nname = "other"\n', encoding="utf-8")
    assert load_taxonomy(no_color.parent).categories[0].color == "#9ca3af"

    empty = tmp_path / "c" / "taxonomy.toml"
    empty.parent.mkdir()
    empty.write_text("", encoding="utf-8")
    tax = load_taxonomy(empty.parent)
    assert tax.categories == [] and tax.rules == []


def test_prompt_categories_follow_taxonomy(tax_env):
    """C1: после переименования категории промпт берёт список из taxonomy, а не из константы."""
    from spendtrack.prompts import build_system_prompt
    from spendtrack.taxonomy import load_taxonomy

    s = Store(db_path=tax_env.parent / "t.db")
    repo.rename_category("cafe", "general", s, repo.file_hash())
    prompt = build_system_prompt([], load_taxonomy(tax_env.parent))
    line = next(l for l in prompt.splitlines() if l.startswith("Категории:"))
    assert "general" in line
    assert "cafe" not in line
    s.close()


def test_set_color(tax_env):
    repo.set_color("other", "#FFFFFF", None)
    assert repo.load_raw()["categories"][0]["color"] == "#ffffff"


# ── переименование категории (Фаза 3) ───────────────────────────────────────


def test_rename_category_migrates_toml_db_and_rules(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    tx_id = s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                              category="cafe", category_source="llm", category_llm="cafe",
                              review_status="pending", merchant="МАГНИТ")
    s.merchant_cache_set("МАГНИТ", "cafe")
    s.add_example("ЛЕНТА", -100, "cafe")
    s.set_budget("cafe", 20000_00)
    res = repo.rename_category("cafe", "general", s, repo.file_hash())
    assert res == {"old": "cafe", "new": "general",
                   "counts": {"transactions": 1, "proposals": 1, "cache": 1, "examples": 1,
                              "budget": 1, "rules": 1}}

    data = repo.load_raw()  # TOML: имя категории + правило
    assert any(c["name"] == "general" for c in data["categories"])
    assert any(r["category"] == "general" for r in data["rules"])
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
    with pytest.raises(repo.TaxonomyError):  # имя занято
        repo.rename_category("cafe", "other", s, None)
    with pytest.raises(repo.TaxonomyError):  # невалидное имя
        repo.rename_category("cafe", "плохое имя", s, None)
    with pytest.raises(repo.TaxonomyError):  # категории нет
        repo.rename_category("нет-такой", "general", s, None)
    with pytest.raises(repo.TaxonomyError):  # файл изменён снаружи
        repo.rename_category("cafe", "general", s, "deadbeef")
    assert any(c["name"] == "cafe" for c in repo.load_raw()["categories"])
    s.close()


def test_rename_rollback_db_on_toml_failure(tax_env, monkeypatch):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="cafe", category_source="manual")

    def boom(*args, **kwargs):
        raise repo.TaxonomyError("disk full")

    monkeypatch.setattr(repo, "save", boom)
    with pytest.raises(repo.TaxonomyError):
        repo.rename_category("cafe", "general", s, None)
    assert s.conn.execute("SELECT category FROM transactions").fetchone()[0] == "cafe"
    assert any(c["name"] == "cafe" for c in repo.load_raw()["categories"])  # TOML не тронут
    s.close()


def test_rename_preview_counts(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="cafe", category_source="manual")
    p = repo.rename_preview("Cafe", "general", s)  # old — case-insensitive
    assert p["old"] == "cafe" and p["new"] == "general"
    assert p["counts"]["transactions"] == 1 and p["counts"]["rules"] == 1
    with pytest.raises(repo.TaxonomyError):  # preview со стухшим hash
        repo.rename_preview("cafe", "general", s, "deadbeef")
    s.close()


def test_rename_same_name_message(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    with pytest.raises(repo.TaxonomyError, match="совпадает"):  # в т.ч. смена регистра: Cafe = cafe
        repo.rename_category("cafe", "Cafe", s, None)
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
    # C2 (ревью 28.09): последнюю категорию удалять нельзя — удаляем одну из двух
    tax_env.write_text('[[categories]]\nname = "other"\ncolor = "#9ca3af"\n\n'
                       '[[categories]]\nname = "cafe"\ncolor = "#112233"\n', encoding="utf-8")
    s = Store(db_path=tax_env.parent / "t.db")
    repo.set_budget("cafe", "20000", s)
    repo.delete_category("cafe", s, repo.file_hash())
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


def test_mutations_return_settings_root_contract(tax_env):
    """Wave5 settings №1/№3: мутации возвращают фрагмент #settings-root; ошибки — role=alert."""
    client = TestClient(app)
    ok = client.post("/settings/budgets", data={"category": "other", "amount": "1000"})
    assert ok.status_code == 200 and 'id="settings-root"' in ok.text

    err = client.post("/settings/budgets", data={"category": "other", "amount": "abc"})
    assert 'id="settings-root"' in err.text and "числом" in err.text
    assert 'role="alert"' in err.text

    rules_err = client.post("/settings/rules",
                            data={"pattern": "", "category": "other",
                                  "file_hash": repo.file_hash()})
    assert 'id="settings-root"' in rules_err.text and "паттерн" in rules_err.text


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


def test_mutation_response_is_full_root_with_fresh_hash(tax_env):
    """S2 (Astra 02.10): мутация любой секции возвращает весь #settings-root — соседние формы
    получают свежий file_hash (раньше после правки правил формы категорий несли старый хеш)."""
    client = TestClient(app)
    r = client.post("/settings/rules",
                    data={"pattern": "X ПАТТЕРН", "category": "cafe", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    for sec in ('id="settings-root"', 'id="settings-categories"', 'id="settings-rules"',
                'id="settings-budgets"'):
        assert sec in r.text, sec
    fresh = repo.file_hash()
    assert r.text.count(f'value="{fresh}"') >= 5  # хеш во всех формах категорий/правил


def test_settings_controls_have_stable_ids_and_aria(tax_env):
    """S3/S4/S5 (Astra 02.10): id у полей — htmx возвращает фокус после свопа партиала;
    ошибки — role=alert (скринридер слышит); у ↑/↓ — aria-label (иначе имя — символ «↑»)."""
    client = TestClient(app)
    html = client.get("/settings").text
    assert re.search(r'id="cat-color-[^"]+"', html), "нет id у color-инпута категории"
    assert re.search(r'id="cat-icon-[^"]+"', html), "нет id у select иконки"
    assert re.search(r'id="budget-[^"]+"', html), "нет id у поля бюджета"
    assert re.search(r'id="rule-up-[^"]+"', html), "нет id у кнопки ↑"
    assert re.search(r'id="rule-down-[^"]+"', html), "нет id у кнопки ↓"
    assert re.search(r'aria-label="Переместить правило #\d+ выше"', html)
    assert re.search(r'aria-label="Переместить правило #\d+ ниже"', html)
    assert 'aria-label="Приоритет"' in html  # O11: колонка «#» больше не читается как «решётка»

    err = client.post("/settings/categories",
                      data={"name": "bad name", "color": "#112233", "file_hash": repo.file_hash()})
    assert 'role="alert"' in err.text


def test_category_color_and_delete_routes(tax_env):
    """Роуты смены цвета и удаления категории (аудит 23.09: repo покрыт, роуты — нет)."""
    client = TestClient(app)
    client.post("/settings/categories",
                data={"name": "cafe2", "color": "#112233", "file_hash": repo.file_hash()})

    r = client.post("/settings/categories/color",
                    data={"name": "cafe2", "color": "#ff0000", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    colors = {c["name"]: c["color"] for c in repo.load_raw()["categories"]}
    assert colors["cafe2"] == "#ff0000"

    r = client.post("/settings/categories/delete",
                    data={"name": "cafe2", "file_hash": repo.file_hash()})
    assert r.status_code == 200
    assert "cafe2" not in [c["name"] for c in repo.load_raw()["categories"]]


def test_rename_api_preview_and_execute(tax_env):
    s = Store(db_path=tax_env.parent / "t.db")
    s.add_transaction(date="2026-09-01", description="X", amount_kopecks=-100,
                      category="cafe", category_source="manual")
    s.close()
    client = TestClient(app)
    r = client.post("/settings/categories/rename/preview",
                    data={"name": "cafe", "new_name": "general", "file_hash": repo.file_hash()})
    assert r.status_code == 200 and "Подтвердить" in r.text and "транзакций 1" in r.text
    assert "бюджет: 0" in r.text  # у категории бюджета нет (счётчик в preview)

    r2 = client.post("/settings/categories/rename",
                     data={"name": "cafe", "new_name": "general", "file_hash": repo.file_hash()})
    assert r2.status_code == 200 and "general" in r2.text
    assert any(c["name"] == "general" for c in repo.load_raw()["categories"])


def test_rename_api_errors(tax_env):
    client = TestClient(app)
    r = client.post("/settings/categories/rename/preview",
                    data={"name": "cafe", "new_name": "bad name"})
    assert "имя" in r.text
    r2 = client.post("/settings/categories/rename",
                     data={"name": "cafe", "new_name": "general", "file_hash": "deadbeef"})
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
    repo.move_rule(3, "up", repo.file_hash())
    assert _patterns() == ["ЛЕНТА", "КОФЕ", "ВТОРОЕ", "ПЕРВОЕ"]
    repo.move_rule(2, "down", repo.file_hash())
    assert _patterns() == ["ЛЕНТА", "КОФЕ", "ПЕРВОЕ", "ВТОРОЕ"]
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(0, "up", None)
    with pytest.raises(repo.TaxonomyError):
        repo.move_rule(3, "down", None)
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


def test_settings_edit_keeps_display_name(tmp_path, monkeypatch):
    """Аудит 24.09: правка из /settings не стирает display_name из taxonomy.toml."""
    tax = tmp_path / "taxonomy.toml"
    tax.write_text('[[categories]]\nname = "other"\ndisplay_name = "Прочее"\ncolor = "#9ca3af"\n\n'
                   '[[rules]]\npattern = "ЛЕНТА"\ncategory = "other"\n', encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(tax))
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "t.db"))
    repo.set_color("other", "#112233", repo.file_hash())
    cats = repo.load_raw()["categories"]
    assert cats[0]["display_name"] == "Прочее" and cats[0]["color"] == "#112233"


def test_delete_category_cleans_merchant_cache(tmp_path, monkeypatch):
    """Аудит 24.09: удаление категории чистит кэш мерчантов (иначе doctor refs_invalid навсегда)."""
    tax = tmp_path / "taxonomy.toml"
    tax.write_text('[[categories]]\nname = "other"\ncolor = "#9ca3af"\n\n'
                   '[[categories]]\nname = "cafe"\ncolor = "#111111"\n\n'
                   '[[rules]]\npattern = "ЛЕНТА"\ncategory = "other"\n', encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(tax))
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "t.db"))
    s = Store(db_path=tmp_path / "t.db")
    try:
        s.merchant_cache_set("КАФЕ", "cafe")
        repo.delete_category("cafe", s, repo.file_hash())
        assert s.merchant_cache_get("КАФЕ") is None
    finally:
        s.close()


def test_delete_system_category_refused(tax_env):
    """C5 (Astra 01.10): системные other/income/transfers удалять нельзя (семантика шва)."""
    s = Store(db_path=tax_env.parent / "t.db")
    with pytest.raises(repo.TaxonomyError, match="системную"):
        repo.delete_category("other", s, None)
    s.close()


def test_rename_system_category_refused(tax_env):
    """C5: системный slug нельзя переименовать — меняется только отображаемое имя."""
    s = Store(db_path=tax_env.parent / "t.db")
    with pytest.raises(repo.TaxonomyError, match="системную"):
        repo.rename_category("other", "misc", s, None)
    s.close()
