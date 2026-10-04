"""Обезличить банковскую выписку (CSV/XLSX) для безопасной отправки образца в issue.

Формат сохраняется (шапка/колонки/разделитель/даты/суммы/статусы) — образец остаётся валидной
фикстурой для адаптеров импорта. Заменяются потенциальные PII:
  * описания/мерчанты/назначения → ОПЕРАЦИЯ_0001, … (одинаковые значения → одинаковый псевдоним);
  * номера карт/счетов → КАРТА_0001, …;
  * номера документов/операций → 1, 2, 3, … (в порядке появления).

ВАЖНО: даты, суммы, категории и статусы НЕ обезличиваются. Issue на GitHub публичный — просмотрите
файл перед отправкой. По умолчанию оставляются первые 5 строк данных (`--rows 0` — весь файл).

CLI:  spendtrack anonymize выписка.csv|xlsx [образец] [--rows N] [--anon-column "ФИО"]
Dev:  python -m spendtrack.anonymize … / scripts/anonymize.py (тонкая обёртка; для фикстур — --rows 0)

Legacy `.xls` (BIFF) не поддерживается (NO-GO: без xlrd в core) — сконвертируйте в .xlsx/CSV.
Колонки, не распознанные как PII, скрипт не трогает и перечисляет в отчёте — если в них есть
личные данные (ФИО, адрес), обезличьте их флагом `--anon-column` или удалите колонку.
"""
from __future__ import annotations

import argparse
import csv
import sys
from io import BytesIO, StringIO
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


def anonymize_csv(  # noqa: C901 — см. cc_ratchet.py
    raw: str | bytes,
    extra_columns: set[str] | None = None,
    max_rows: int | None = None,
) -> tuple[str, dict]:
    """→ (обезличенный CSV, отчёт). `extra_columns` — имена колонок, которые тоже обезличить.

    Формат сохраняется ПОЗИЦИОННО (csv.reader/writer по индексам, §J-2): пустые и дублирующиеся
    заголовки, хвостовой разделитель и лишние поля строк не теряются — образец остаётся валидной
    фикстурой для адаптеров. Неизвестная колонка из `extra_columns` → ValueError (нельзя молча
    опубликовать PII). `max_rows` — оставить первые N строк данных (0/None — все).
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
        return "", {"anonymized": {}, "untouched": [], "empty_headers": [], "unique": {},
                    "rows_total": 0, "rows_written": 0}

    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    if header is None:
        return "", {"anonymized": {}, "untouched": [], "empty_headers": [], "unique": {},
                    "rows_total": 0, "rows_written": 0}
    extra = {c.strip().lower() for c in (extra_columns or set())}
    known = {h.strip().lower() for h in header}
    missing = sorted(extra - known)
    if missing:
        raise ValueError("колонка не найдена: " + ", ".join(missing))
    kinds = [_classify(name, extra) for name in header]
    pseudonyms = _Pseudonyms()
    limit = max_rows if max_rows and max_rows > 0 else None

    out_rows: list[list[str]] = []
    total = 0
    for row in reader:
        total += 1
        if limit is not None and total > limit:
            continue
        new_row = list(row)
        for i, kind in enumerate(kinds):
            if kind is None or i >= len(new_row):
                continue  # короткая строка/лишние поля — сохраняем как есть, не выдумываем колонки
            value = _strip(new_row[i])
            if value:
                new_row[i] = pseudonyms.get(kind, value)
        out_rows.append(new_row)

    terminator = "\r\n" if crlf else "\n"
    buf = StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator=terminator)
    writer.writerow(header)
    writer.writerows(out_rows)

    report = {
        "anonymized": {name: kind for name, kind in zip(header, kinds) if kind},
        "untouched": [name for name, kind in zip(header, kinds) if not kind and name.strip()],
        "empty_headers": [i for i, name in enumerate(header) if not name.strip()],
        "unique": pseudonyms.unique,
        "rows_total": total,
        "rows_written": len(out_rows),
    }
    return buf.getvalue(), report


def _find_header(ws, scan: int = 10) -> tuple[int | None, list]:
    """Первая «шапкоподобная» строка (≥2 непустых ячеек); приоритет — строка с известными колонками."""
    best: tuple[int, list] | None = None
    for r_idx in range(1, min(ws.max_row, scan) + 1):
        values = [ws.cell(r_idx, c).value for c in range(1, ws.max_column + 1)]
        nonempty = [v for v in values if _strip(v)]
        if len(nonempty) < 2:
            continue
        if any(_classify(_strip(v), set()) for v in values):
            return r_idx, values
        if best is None:
            best = (r_idx, values)
    return best if best else (None, None)


def _label_columns(header: list, kinds: list, anonymized: dict, untouched: list) -> None:
    for name, kind in zip(header, kinds):
        label = _strip(name)
        if not label:
            continue
        if kind:
            anonymized.setdefault(label, kind)
        else:
            untouched.append(label)


def _anonymize_sheet_rows(ws, header_row: int, kinds: list, keep: list, pseudonyms: _Pseudonyms) -> int:
    """Заменить PII в перечисленных строках листа; → сколько строк записано."""
    written = 0
    for r_idx in keep:
        for c_idx, kind in enumerate(kinds, start=1):
            if kind is None:
                continue
            cell = ws.cell(r_idx, c_idx)
            value = _strip(cell.value)
            if value:
                cell.value = pseudonyms.get(kind, value)
        written += 1
    return written


def anonymize_xlsx(
    raw: bytes,
    extra_columns: set[str] | None = None,
    max_rows: int | None = None,
) -> tuple[bytes, dict]:
    """→ (обезличенный XLSX, отчёт). Контракт — как у `anonymize_csv`.

    Книга правится in-place (openpyxl): листы/форматирование сохраняются, заменяются только значения
    PII-колонок. Шапка ищется в первых 10 строках (у банков бывает титульная строка). Строки данных
    сверх `max_rows` УДАЛЯЮТСЯ — PII не остаётся за лимитом (в отличие от «оставить как есть»).
    """
    from openpyxl import load_workbook

    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows не может быть отрицательным (0 — все строки)")
    wb = load_workbook(BytesIO(raw))
    extra = {c.strip().lower() for c in (extra_columns or set())}
    pseudonyms = _Pseudonyms()
    anonymized: dict[str, str] = {}
    untouched: list[str] = []
    empty_headers: list[int] = []
    total = written = outside = 0
    remaining = max_rows if max_rows and max_rows > 0 else None

    for ws in wb.worksheets:
        header_row, header = _find_header(ws)
        if header_row is None:
            continue
        # строки ВЫШЕ шапки (титул банка — часто с ФИО) не обезличиваются: считаем и предупреждаем (C3)
        for r in range(1, header_row):
            if any(_strip(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)):
                outside += 1
        kinds = [_classify(_strip(name), extra) for name in header]
        empty_headers.extend(i for i, name in enumerate(header) if not _strip(name))
        _label_columns(header, kinds, anonymized, untouched)
        rows_all = list(range(header_row + 1, ws.max_row + 1))
        keep = rows_all if remaining is None else rows_all[:remaining]
        total += len(rows_all)
        written += _anonymize_sheet_rows(ws, header_row, kinds, keep, pseudonyms)
        if remaining is not None:
            remaining -= len(keep)
        cut = len(rows_all) - len(keep)
        if cut > 0:
            ws.delete_rows(header_row + len(keep) + 1, cut)

    # метаданные книги — PII-канал (автор/последний редактор/заголовок): чистим ДО сохранения (ревью wave5, C3/S2)
    props = wb.properties
    props.creator = ""
    props.lastModifiedBy = ""
    props.title = ""
    props.description = ""
    props.keywords = ""
    props.category = ""
    buf = BytesIO()
    wb.save(buf)
    report = {
        "anonymized": anonymized,
        "untouched": untouched,
        "empty_headers": empty_headers,
        "unique": pseudonyms.unique,
        "rows_total": total,
        "rows_written": written,
        "outside_rows": outside,
        "xlsx": True,
    }
    return buf.getvalue(), report


def _anonymize_payload(raw: bytes, suffix: str, extra: set[str], max_rows: int) -> tuple[bytes, dict]:
    """Выбор CSV/XLSX-пути (по расширению и магии ZIP); legacy .xls — понятная ошибка."""
    if suffix in (".xls", ".xlsm"):
        # NO-GO адъюдикации 03.10 + ревью wave5 S6: legacy BIFF и макрос-книги не тянем
        raise ValueError(
            "legacy/macro .xls/.xlsm не поддерживается — сконвертируйте выписку в .xlsx "
            "(Excel/LibreOffice) или CSV")
    if suffix == ".xlsx" or (suffix != ".csv" and raw[:4] == b"PK\x03\x04"):
        return anonymize_xlsx(raw, extra, max_rows=max_rows)
    text, report = anonymize_csv(raw, extra, max_rows=max_rows)
    # bytes, а не write_text: терминатор строк выписки (CRLF в cp1251-файлах) сохраняется
    # как есть — text-mode на Windows превратил бы «\r\n» в «\r\r\n».
    return text.encode("utf-8"), report


def _read_source(src: Path) -> bytes | None:
    try:
        return src.read_bytes()
    except OSError as e:
        print(f"не удалось прочитать файл: {e}", file=sys.stderr, flush=True)
        return None


def _write_anonymized(data: bytes, dst: Path) -> bool:
    try:
        dst.write_bytes(data)
    except OSError as e:
        print(f"не удалось записать файл: {e}", file=sys.stderr, flush=True)
        return False
    return True


def _print_report(report: dict, dst: Path) -> None:
    """Отчёт и предупреждения (stdout/stderr) — вынесено ради cc-лимита run_anonymize."""
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
    if not report["anonymized"]:
        warn.append("ВНИМАНИЕ: НИЧЕГО не обезличено — колонки не распознаны. Проверьте заголовки или "
                    "укажите --anon-column; НЕ отправляйте файл как есть (ревью wave5, C1).")
    if report.get("outside_rows"):
        warn.append(f"ВНИМАНИЕ: {report['outside_rows']} строк(и) ВНЕ таблицы (титул/шапка отчёта) "
                    "не обезличиваются — проверьте вручную (часто там ФИО).")
    if report.get("xlsx"):
        warn.append("ВНИМАНИЕ: имена листов и метаданные книги не обезличиваются (свойства книги очищены) — "
                    "просмотрите файл перед отправкой.")
    if report.get("empty_headers"):
        warn.append("ВНИМАНИЕ: есть колонки без заголовка — проверьте их вручную (могут содержать PII).")
    print("\n".join(warn), file=sys.stderr, flush=True)


def run_anonymize(
    src: Path | str,
    dst: Path | str | None = None,
    *,
    max_rows: int = DEFAULT_ROWS,
    extra_columns: tuple[str, ...] | set[str] = (),
) -> int:
    """Обезличить файл (CSV/XLSX) и предупредить о неудаляемых датах/суммах. 0 — успех, 1 — ошибка."""
    utf8_stdout()
    if max_rows < 0:
        print("--rows не может быть отрицательным (0 — все строки)", file=sys.stderr, flush=True)
        return 1
    src = Path(src)
    raw = _read_source(src)
    if raw is None:
        return 1
    dst = Path(dst) if dst else src.with_name(src.stem + ".anon" + src.suffix)
    if dst.resolve() == src.resolve():
        print("исходный и выходной файл совпадают — перезапись выписки запрещена; укажите другой путь",
              file=sys.stderr, flush=True)
        return 1
    try:
        data, report = _anonymize_payload(raw, src.suffix.lower(), set(extra_columns), max_rows)
    except (ValueError, OSError) as e:
        print(f"ошибка обезличивания: {e}", file=sys.stderr, flush=True)
        return 1
    except Exception as e:  # noqa: BLE001 — битый XLSX (не zip) — понятная ошибка, а не трейс
        print(f"не удалось разобрать файл: {e}", file=sys.stderr, flush=True)
        return 1
    if not _write_anonymized(data, dst):
        return 1
    _print_report(report, dst)
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description="Обезличить выписку CSV/XLSX для отправки образца")
    parser.add_argument("file", help="исходная выписка банка (CSV или XLSX)")
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
