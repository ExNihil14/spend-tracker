from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "contract_delta", ROOT / "scripts" / "contract_delta.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_api_snapshot_public_only(tmp_path):
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "sample.py").write_text(
        'def public(a: int, b: str = "x") -> bool:\n'
        "    return True\n\n"
        "def _private():\n"
        "    pass\n\n"
        "class Widget:\n"
        '    def render(self) -> str:\n'
        '        return ""\n\n'
        "    def _hidden(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    snap = _mod().api_snapshot(pkg)

    assert "pkg.sample:public" in snap
    assert "pkg.sample:Widget.render" in snap
    assert snap["pkg.sample:public"]["returns"] == "bool"
    assert all("_private" not in k and "_hidden" not in k for k in snap)


def test_schema_snapshot_core_tables():
    snap = _mod().schema_snapshot()

    assert "user_version" in snap
    assert "transactions.id" in snap
    assert "transactions.amount_kopecks" in snap
    assert "budgets.category" in snap


def test_routes_snapshot_has_health_and_api():
    snap = _mod().routes_snapshot()

    assert "GET /health" in snap
    assert "GET /dashboard" in snap
    assert any(key.startswith("POST /api/") for key in snap)
    assert all(" " in key for key in snap)


def test_diff_detects_added_removed_changed():
    m = _mod()
    before = {"schema": {"a": "1", "gone": "x"}, "api": {}, "routes": {}}
    after = {"schema": {"a": "2", "new": "3"}, "api": {"k": {"args": "", "returns": ""}}, "routes": {}}

    diff = m.diff_snapshots(before, after)

    assert m.has_drift(diff)
    assert diff["schema"]["changed"]["a"] == {"before": "1", "after": "2"}
    assert "new" in diff["schema"]["added"]
    assert "gone" in diff["schema"]["removed"]
    assert "k" in diff["api"]["added"]
    assert not m.has_drift(m.diff_snapshots(before, before))


def test_cli_snapshot_then_check_and_drift(tmp_path, capsys):
    m = _mod()
    baseline = tmp_path / "base.json"

    assert m.main(["snapshot", "--out", str(baseline)]) == 0
    assert m.main(["check", "--baseline", str(baseline)]) == 0
    assert "contract: ok" in capsys.readouterr().out

    data = json.loads(baseline.read_text(encoding="utf-8"))
    data["schema"].pop("transactions.id")
    baseline.write_text(json.dumps(data), encoding="utf-8")

    assert m.main(["check", "--baseline", str(baseline)]) == 1
    assert "DRIFT" in capsys.readouterr().out


def test_cli_check_missing_baseline(tmp_path, capsys):
    m = _mod()

    assert m.main(["check", "--baseline", str(tmp_path / "nope.json")]) == 2
    assert "baseline не найден" in capsys.readouterr().out
