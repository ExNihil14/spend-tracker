from __future__ import annotations

import json

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


def test_tester_endpoint(tax_env):
    client = TestClient(app)
    r = client.post("/settings/test", data={"description": "ЛЕНТА 1"})
    assert "Итог" in r.text and "other" in r.text
