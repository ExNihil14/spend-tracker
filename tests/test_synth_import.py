from __future__ import annotations

import csv
import io

from synth_bank import gen_sber, gen_tinkoff, gen_yandex

from spendtrack.csv_import import import_csv
from spendtrack.store import Store


def _drop_column(raw: str, name: str) -> str:
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    idx = rows[0].index(name)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    for row in rows:
        writer.writerow([cell for i, cell in enumerate(row) if i != idx])
    return out.getvalue()


def _stub(tx, store, taxonomy):
    return {"category": "other", "confidence": 0.5, "merchant": None, "source": "llm_pending_review"}


def test_synth_sber_roundtrip(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    raw = gen_sber(n=20, seed=42)
    res = import_csv(raw, s, classify=_stub)
    assert res["bank"] == "sber"
    assert res["added"] >= 20

    rows = s.list_transactions(limit=1000)
    assert all(len(t["date"]) == 10 and t["date"][4] == "-" for t in rows)  # ISO-даты
    assert all(t["amount_kopecks"] != -77700 for t in rows)  # «В обработке» пропущена

    res2 = import_csv(raw, s, classify=_stub)
    assert res2["added"] == 0 and res2["dupes"] == res["added"]
    s.close()


def test_synth_sber_cp1251_equivalent(tmp_path):
    a = Store(db_path=tmp_path / "a.db")
    import_csv(gen_sber(seed=7), a, classify=_stub)
    b = Store(db_path=tmp_path / "b.db")
    import_csv(gen_sber(seed=7, encoding="cp1251"), b, classify=_stub)

    def key(t):
        return (t["date"], t["amount_kopecks"], t["description"])

    assert sorted(map(key, a.list_transactions(limit=1000))) == sorted(map(key, b.list_transactions(limit=1000)))
    a.close()
    b.close()


def test_synth_same_day_duplicate_kept(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    import_csv(gen_sber(n=3, seed=5), s, classify=_stub)
    groups: dict[tuple, int] = {}
    for t in s.list_transactions(limit=100):
        k = (t["date"], t["description"], t["amount_kopecks"])
        groups[k] = groups.get(k, 0) + 1
    assert max(groups.values()) >= 2  # дубль в один день сохранён
    s.close()


def test_synth_tinkoff_and_yandex(tmp_path):
    s = Store(db_path=tmp_path / "t.db")
    assert import_csv(gen_tinkoff(seed=3), s, classify=_stub)["bank"] == "tinkoff"
    assert import_csv(gen_yandex(seed=4), s, classify=_stub)["bank"] == "yandex"
    assert all("T" not in t["date"] for t in s.list_transactions(limit=100))
    s.close()


def test_synth_sber_renamed_column_reports_format_error(tmp_path):
    """Дрейф формата: переименование колонки → format_error, БД не тронута (P1 #1)."""
    raw = gen_sber(n=5, seed=1).replace("Дата операции", "Дата проводки")
    s = Store(db_path=tmp_path / "t.db")
    res = import_csv(raw, s, classify=_stub)
    assert res["status"] == "format_error"
    assert res["added"] == 0
    assert any("Дата операции" in label for label in res["missing_columns"])
    assert "Дата проводки" in res["found_columns"]
    assert s.list_transactions(limit=100) == []
    s.close()


def test_synth_sber_removed_column_reports_format_error(tmp_path):
    """Дрейф формата: пропавшая колонка суммы → format_error (P1 #1)."""
    raw = _drop_column(gen_sber(n=5, seed=2), "Сумма операции")
    s = Store(db_path=tmp_path / "t.db")
    res = import_csv(raw, s, classify=_stub)
    assert res["status"] == "format_error"
    assert any("Сумма операции" in label for label in res["missing_columns"])
    assert s.list_transactions(limit=100) == []
    s.close()
