"""Обезличить банковскую выписку (CSV) для безопасной отправки образца в issue.

Формат сохраняется (шапка/колонки/разделитель/даты/суммы/статусы) — образец остаётся валидной
фикстурой для адаптеров импорта. Заменяются потенциальные PII:
  * описания/мерчанты/назначения → ОПЕРАЦИЯ_0001, … (одинаковые значения → одинаковый псевдоним);
  * номера карт/счетов → КАРТА_0001, …;
  * номера документов/операций → 1, 2, 3, … (в порядке появления).

Использование:
    python scripts/anonymize.py выписка.csv              # → выписка.anon.csv
    python scripts/anonymize.py выписка.csv -o sample.csv
    python scripts/anonymize.py выписка.csv --anon-column "ФИО"   # доп. колонка (можно повторять)

Колонки, не распознанные как PII, скрипт не трогает и перечисляет в отчёте — если в них есть
личные данные (ФИО, адрес), обезличьте их флагом `--anon-column` или удалите колонку.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
from pathlib import Path

DESC_ALIASES = {"описание", "назначение", "комментарий", "description", "title", "merchant"}
ACCOUNT_ALIASES = {"номер карты", "номер счёта", "номер счета", "карта", "счёт", "счет", "account"}
DOC_ALIASES = {"номер документа", "номер операции", "номер", "document", "doc", "id"}

DESC_PREFIX = "ОПЕРАЦИЯ"
ACCOUNT_PREFIX = "КАРТА"
KIND_DESC, KIND_ACCOUNT, KIND_DOC = "desc", "account", "doc"


def _strip(value: object) -> str:
    return "" if value is None else str(value).strip()


class _Pseudonyms:
    """Стабильные псевдонимы: одинаковое значение → одинаковый псевдоним (дедуп-фикстуры)."""

    def __init__(self) -> None:
        self._map: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}

    def get(self, kind: str, value: str) -> str:
        key = (kind, value)
        if key not in self._map:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            n = self._counters[kind]
            if kind == KIND_DOC:
                self._map[key] = str(n)
            else:
                prefix = DESC_PREFIX if kind == KIND_DESC else ACCOUNT_PREFIX
                self._map[key] = f"{prefix}_{n:04d}"
        return self._map[key]

    @property
    def unique(self) -> dict[str, int]:
        """Сколько уникальных значений заменено по каждому типу."""
        return {kind: sum(1 for k in self._map if k[0] == kind)
                for kind in sorted({k[0] for k in self._map})}


def _classify(header: str, extra: set[str]) -> str | None:
    name = header.strip().lower()
    if name in extra:
        return KIND_DESC
    if name in DESC_ALIASES:
        return KIND_DESC
    if name in ACCOUNT_ALIASES:
        return KIND_ACCOUNT
    if name in DOC_ALIASES:
        return KIND_DOC
    return None


def anonymize_csv(raw: str | bytes, extra_columns: set[str] | None = None) -> tuple[str, dict]:
    """→ (обезличенный CSV, отчёт). `extra_columns` — имена колонок, которые тоже обезличить."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251", errors="replace")
    else:
        text = raw.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines:
        return "", {"anonymized": {}, "untouched": [], "unique": {}}

    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    extra = {c.strip().lower() for c in (extra_columns or set())}
    kinds = {name: _classify(name, extra) for name in fieldnames}
    pseudonyms = _Pseudonyms()

    out_rows: list[dict[str, str]] = []
    for row in reader:
        out_rows.append({
            name: (pseudonyms.get(kinds[name], _strip(row.get(name)))
                   if kinds[name] and _strip(row.get(name)) else _strip(row.get(name)))
            for name in fieldnames
        })

    terminator = "\r\n" if "\r\n" in text else "\n"
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=delimiter,
                            lineterminator=terminator)
    writer.writeheader()
    writer.writerows(out_rows)

    report = {
        "anonymized": {name: kind for name, kind in kinds.items() if kind},
        "untouched": [name for name in fieldnames if not kinds[name]],
        "unique": pseudonyms.unique,
    }
    return buf.getvalue(), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Обезличить выписку CSV для отправки образца")
    parser.add_argument("file", help="исходный CSV банка")
    parser.add_argument("-o", "--out", default=None,
                        help="куда записать (по умолчанию рядом: <имя>.anon.csv)")
    parser.add_argument("--anon-column", action="append", default=[],
                        help="доп. колонка для обезличивания (можно повторять)")
    args = parser.parse_args(argv)

    src = Path(args.file)
    text, report = anonymize_csv(src.read_bytes(), set(args.anon_column))
    dst = Path(args.out) if args.out else src.with_name(src.stem + ".anon" + src.suffix)
    dst.write_text(text, encoding="utf-8")

    print(f"Записано: {dst}")
    if report["anonymized"]:
        print("Обезличено: " + ", ".join(report["anonymized"]))
    if report["untouched"]:
        print("Без изменений (проверьте, нет ли личных данных): " + ", ".join(report["untouched"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
