from __future__ import annotations

import pytest

from spendtrack.config import ROOT
from spendtrack.store import Store, parse_amount
from spendtrack.taxonomy import load_taxonomy


@pytest.fixture()
def store(tmp_path):
    s = Store(db_path=tmp_path / "test.db")
    print(f"\nDB={s.path}")
    yield s
    s.close()


@pytest.fixture()
def taxonomy():
    return load_taxonomy(ROOT / "config")


@pytest.fixture()
def sample_txs() -> list[dict]:
    return [
        {"date": "2026-09-01", "description": "ЛЕНТА", "amount_kopecks": parse_amount("-1234.50")},
        {"date": "2026-09-02", "description": "UBER MUNCHEN", "amount_kopecks": parse_amount("-1200")},
        {"date": "2026-09-03", "description": "ЗАРАБОТНАЯ ПЛАТА", "amount_kopecks": parse_amount("250000")},
        {"date": "2026-09-04", "description": "NETFLIX.COM", "amount_kopecks": parse_amount("-1549")},
        {"date": "2026-09-05", "description": "СТРАННЫЙ МАГАЗИН", "amount_kopecks": parse_amount("-500")},
    ]


class StubLLM:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, tx: dict, store: Store, taxonomy) -> dict:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {"category": "other", "confidence": 0.1, "merchant": None, "reason": "stub_default"}