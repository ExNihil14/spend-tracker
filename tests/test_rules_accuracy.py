from __future__ import annotations

from merchants import MERCHANTS

from spendtrack.categorize import categorize_rules_only
from spendtrack.config import ROOT
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy


def test_rules_accuracy_on_merchant_dictionary(tmp_path):
    """Keyword-правила должны покрывать ≥90% реалистичного словаря мерчантов (оффлайн)."""
    taxonomy = load_taxonomy(ROOT / "config")
    store = Store(db_path=tmp_path / "t.db")

    hits, misses = [], []
    for merchant, expected in MERCHANTS.items():
        got = categorize_rules_only({"description": merchant, "merchant": merchant}, taxonomy, store)
        if got == expected:
            hits.append(merchant)
        else:
            misses.append(f"{merchant}: ожидали {expected}, получили {got!r}")

    accuracy = len(hits) / len(MERCHANTS)
    store.close()
    assert accuracy >= 0.9, f"accuracy={accuracy:.0%}; промахи: {misses}"
