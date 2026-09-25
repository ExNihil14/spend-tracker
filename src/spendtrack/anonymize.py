"""Обезличить банковскую выписку (CSV) для безопасной отправки образца в issue.

Формат сохраняется (шапка/колонки/разделитель/даты/суммы/статусы) — образец остаётся валидной
фикстурой для адаптеров импорта. Заменяются потенциальные PII:
  * описания/мерчанты/назначения → ОПЕРАЦИЯ_0001, … (одинаковые значения → одинаковый псевдоним);
  * номера карт/счетов → КАРТА_0001, …;
  * номера документов/операций → 1, 2, 3, … (в порядке появления).

ВАЖНО: даты, суммы, категории и статусы НЕ обезличиваются. Issue на GitHub публичный — просмотрите
файл перед отправкой. По умолчанию оставляются первые 5 строк данных (`--rows 0` — весь файл).

CLI:  spendtrack anonymize выписка.csv [образец.csv] [--rows N] [--anon-column "ФИО"]
Dev:  python -m spendtrack.anonymize … / scripts/anonymize.py (тонкая обёртка; для фикстур — --rows 0)

Колонки, не распознанные как PII, скрипт не трогает и перечисляет в отчёте — если в них есть
личные данные (ФИО, адрес), обезличьте их флагом `--anon-column` или удалите колонку.
"""
from __future__ import annotations

import argparse
import csv
import sys
from io import StringIO
from pathlib import Path

from spendtrack.console import utf8_stdout

DESC_ALIASES = {"описание", "назначение", "комментарий", "description", "title", "merchant"}
ACCOUNT_ALIASES = {"номер карты", "номер счёта", "номер счета", "карта", "счёт", "счет", "account"}
DOC_ALIASES = {"номер документа", "номер операции", "номер", "document", "doc", "id"}

DESC_PREFIX = "ОПЕРАЦИЯ"
ACCOUNT_PREFIX = "КАРТА"
KIND_DESC, KIND_ACCOUNT, KIND_DOC = "desc", "account", "doc"
DEFAULT_ROWS = 5


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


def anonymize_csv(
    raw: str | bytes,
    extra_columns: set[str] | None = None,
    max_rows: int | None = None,
) -> tuple[str, dict]:
    """→ (обезличенный CSV, отчёт). `extra_columns` — имена колонок, которые тоже обезличить.

    `max_rows` — оставить первые N строк данных (0/None — все). Даты и суммы не меняются.
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251", errors="replace")
    else:
        text = raw.lstrip("\ufeff")
    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows не может быть отрицательным (0 — все строки)")
    # csv-парсер падает на одиночном `\r` в незакавыченном поле — нормализуем перевод строки
    # (см. csv_import.import_csv; property-тест §G ловил падение на CR-выгрузках).
    # Терминатор вывода фиксируем ДО нормализации, чтобы CRLF-выписки остались CRLF.
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    if not lines:
        return "", {"anonymized": {}, "untouched": [], "unique": {},
                    "rows_total": 0, "rows_written": 0}

    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    extra = {c.strip().lower() for c in (extra_columns or set())}
    kinds = {name: _classify(name, extra) for name in fieldnames}
    pseudonyms = _Pseudonyms()
    limit = max_rows if max_rows and max_rows > 0 else None

    out_rows: list[dict[str, str]] = []
    total = 0
    for row in reader:
        total += 1
        if limit is not None and total > limit:
            continue
        out_rows.append({
            name: (pseudonyms.get(kinds[name], _strip(row.get(name)))
                   if kinds[name] and _strip(row.get(name)) else _strip(row.get(name)))
            for name in fieldnames
        })

    terminator = "\r\n" if crlf else "\n"
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=delimiter,
                            lineterminator=terminator)
    writer.writeheader()
    writer.writerows(out_rows)

    report = {
        "anonymized": {name: kind for name, kind in kinds.items() if kind},
        "untouched": [name for name in fieldnames if not kinds[name]],
        "unique": pseudonyms.unique,
        "rows_total": total,
        "rows_written": len(out_rows),
    }
    return buf.getvalue(), report


def run_anonymize(
    src: Path | str,
    dst: Path | str | None = None,
    *,
    max_rows: int = DEFAULT_ROWS,
    extra_columns: tuple[str, ...] | set[str] = (),
) -> int:
    """Обезличить файл и предупредить о неудаляемых датах/суммах. 0 — успех, 1 — ошибка чтения/записи."""
    utf8_stdout()
    if max_rows < 0:
        print("--rows не может быть отрицательным (0 — все строки)", file=sys.stderr, flush=True)
        return 1
    src = Path(src)
    try:
        raw = src.read_bytes()
    except OSError as e:
        print(f"не удалось прочитать файл: {e}", file=sys.stderr, flush=True)
        return 1
    text, report = anonymize_csv(raw, set(extra_columns), max_rows=max_rows)
    dst = Path(dst) if dst else src.with_name(src.stem + ".anon" + src.suffix)
    try:
        # bytes, а не write_text: терминатор строк выписки (CRLF в cp1251-файлах) сохраняется
        # как есть — text-mode на Windows превратил бы «\r\n» в «\r\r\n».
        dst.write_bytes(text.encode("utf-8"))
    except OSError as e:
        print(f"не удалось записать файл: {e}", file=sys.stderr, flush=True)
        return 1

    total, written = report["rows_total"], report["rows_written"]
    print(f"Записано: {dst} (строк {written} из {total})")
    if report["anonymized"]:
        print("Обезличено: " + ", ".join(report["anonymized"]))
    if report["untouched"]:
        print("Без изменений (проверьте, нет ли личных данных): " + ", ".join(report["untouched"]))

    warn = [
        ("ВНИМАНИЕ: даты, суммы, категории и статусы не обезличиваются — просмотрите файл "
         "перед отправкой в публичный issue."),
    ]
    if written < total:
        warn.append(f"Строк в файле: {total}, оставлено: {written} (--rows 0 — все).")
    print("\n".join(warn), file=sys.stderr, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Обезличить выписку CSV для отправки образца")
    parser.add_argument("file", help="исходный CSV банка")
    parser.add_argument("output", nargs="?", default=None,
                        help="куда записать (по умолчанию <имя>.anon.csv рядом)")
    parser.add_argument("-o", "--out", dest="output_flag", default=None, metavar="ФАЙЛ",
                        help="то же, что позиционный аргумент (для скриптов)")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help=f"оставить первых N строк данных (0 — все; по умолчанию {DEFAULT_ROWS})")
    parser.add_argument("--anon-column", action="append", default=[],
                        help="доп. колонка для обезличивания (можно повторять)")
    args = parser.parse_args(argv)
    if args.rows < 0:
        parser.error("--rows не может быть отрицательным")
    if args.output and args.output_flag:
        parser.error("укажите выходной файл один раз: позиционным аргументом или -o/--out")
    return run_anonymize(args.file, args.output_flag or args.output,
                         max_rows=args.rows, extra_columns=args.anon_column)


if __name__ == "__main__":
    raise SystemExit(main())
