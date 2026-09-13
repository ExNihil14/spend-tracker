from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from spendtrack.config import ROOT
from spendtrack.store import Store, parse_amount
from spendtrack.taxonomy import load_taxonomy

_PERF: dict[str, dict] = {}


def _perf_dir() -> Path:
    return ROOT / "reports"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and item.get_closest_marker("perf"):
        _PERF[item.nodeid] = {
            "seconds": round(rep.duration, 4),
            "outcome": rep.outcome,
        }


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if not _PERF:
        return
    out_dir = _perf_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(_PERF.items(), key=lambda kv: -kv[1]["seconds"])
    data = {
        "generated": int(time.time()),
        "python": "3.13",
        "results": [
            {"test": name, "seconds": m["seconds"], "outcome": m["outcome"]}
            for name, m in ordered
        ],
        "total_seconds": round(sum(m["seconds"] for m in _PERF.values()), 4),
    }
    target = out_dir / "perf.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[perf] JSON report -> {target} ({len(_PERF)} cases)")


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