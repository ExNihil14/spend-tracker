"""Контракт-дельта: снапшот публичных контрактов и автоматическая проверка дрейфа.

Снапшот:
* schema — user_version + таблицы/колонки (из свежей tmp-БД Store);
* api — публичные сигнатуры модулей `src/spendtrack` (AST, без импорта кода);
* routes — публичные HTTP-маршруты FastAPI.

Использование:
    uv run python scripts/contract_delta.py snapshot [--out spec/contract_baseline.json]
    uv run python scripts/contract_delta.py check [--baseline spec/contract_baseline.json]

`check` возвращает 1 при расхождении — гейт для CI и для после-AI-рефакторинга.
Обновление baseline — осознанное действие в том же коммите, что и изменение контракта.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "spec" / "contract_baseline.json"
SRC = ROOT / "src" / "spendtrack"


def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    return {
        "args": ast.unparse(fn.args),
        "returns": ast.unparse(fn.returns) if fn.returns is not None else "",
    }


def api_snapshot(src_dir: Path = SRC) -> dict:
    """Публичные функции/классы (без ведущего `_`) из пакета, по AST (без импорта)."""
    out: dict[str, dict] = {}
    for path in sorted(src_dir.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mod = path.relative_to(src_dir.parent).as_posix().removesuffix(".py").replace("/", ".")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                out[f"{mod}:{node.name}"] = _sig(node)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
                        out[f"{mod}:{node.name}.{item.name}"] = _sig(item)
    return dict(sorted(out.items()))


def schema_snapshot() -> dict:
    """user_version + колонки всех таблиц из свежей временной БД."""
    from spendtrack.store import Store

    with tempfile.TemporaryDirectory(prefix="contract-") as tmp:
        store = Store(db_path=Path(tmp) / "contract.db")
        try:
            conn = store.conn
            out: dict[str, str] = {
                "user_version": str(conn.execute("PRAGMA user_version").fetchone()[0])}
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for table in tables:
                for col in conn.execute(f"PRAGMA table_info({table})"):
                    out[f"{table}.{col['name']}"] = (
                        f"{col['type']}|notnull={col['notnull']}|pk={col['pk']}")
        finally:
            store.close()
    return dict(sorted(out.items()))


def routes_snapshot() -> dict:
    """Публичные HTTP-маршруты из OpenAPI-схемы (app.routes отдаёт ленивые _IncludedRouter)."""
    from spendtrack.main import app

    out: dict[str, str] = {}
    for path, methods in app.openapi().get("paths", {}).items():
        for method in methods:
            upper = method.upper()
            if upper in ("HEAD", "OPTIONS", "PARAMETERS"):
                continue
            out[f"{upper} {path}"] = ""
    return dict(sorted(out.items()))


def build_snapshot() -> dict:
    return {"schema": schema_snapshot(), "api": api_snapshot(), "routes": routes_snapshot()}


def diff_section(before: dict, after: dict) -> dict:
    return {
        "added": {k: after[k] for k in sorted(after.keys() - before.keys())},
        "removed": {k: before[k] for k in sorted(before.keys() - after.keys())},
        "changed": {k: {"before": before[k], "after": after[k]}
                    for k in sorted(before.keys() & after.keys()) if before[k] != after[k]},
    }


def diff_snapshots(before: dict, after: dict) -> dict:
    return {s: diff_section(before.get(s, {}), after.get(s, {}))
            for s in ("schema", "api", "routes")}


def has_drift(diff: dict) -> bool:
    return any(d["added"] or d["removed"] or d["changed"] for d in diff.values())


def render_diff(diff: dict) -> str:
    lines: list[str] = []
    for section in ("schema", "api", "routes"):
        d = diff[section]
        if not (d["added"] or d["removed"] or d["changed"]):
            continue
        lines.append(f"== {section} ==")
        for k, v in d["added"].items():
            lines.append(f"  + {k} = {v}")
        for k, v in d["removed"].items():
            lines.append(f"  - {k} = {v}")
        for k, v in d["changed"].items():
            lines.append(f"  ~ {k}: {v['before']} -> {v['after']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contract_delta", description="Контракт-дельта")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_snap = sub.add_parser("snapshot", help="записать базовый снапшот контрактов")
    p_snap.add_argument("--out", type=Path, default=DEFAULT_BASELINE)
    p_check = sub.add_parser("check", help="проверить дрейф контрактов (exit 1 при расхождении)")
    p_check.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    if args.cmd == "snapshot":
        snap = build_snapshot()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"snapshot: {args.out} | schema={len(snap['schema'])} api={len(snap['api'])}"
              f" routes={len(snap['routes'])}")
        return 0

    if not args.baseline.exists():
        print(f"baseline не найден: {args.baseline} (сначала snapshot)")
        return 2
    before = json.loads(args.baseline.read_text(encoding="utf-8"))
    diff = diff_snapshots(before, build_snapshot())
    if not has_drift(diff):
        print("contract: ok (schema/api/routes совпадают с baseline)")
        return 0
    print(render_diff(diff))
    print("contract: DRIFT — контракт изменился. Осознанно обнови baseline"
          " (snapshot) в том же коммите или откати изменение контракта.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
