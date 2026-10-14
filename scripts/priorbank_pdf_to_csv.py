"""Приорбанк: PDF-выписка → CSV (СТРОГО локально; сырьё не покидает машину).

Зачем: анонимайзер понимает CSV/XLSX, а выписка Приорбанка — PDF. Конвертер вытаскивает таблицу
(pdfplumber), собирает шапку (строки до первой строки с датой) и пишет CSV для `spendtrack anonymize`.
В stdout — только счётчики и пути; содержимое ячеек не печатается и никуда не отправляется.

Запуск (из корня spend-tracker):
    uv run --with pdfplumber python scripts\\priorbank_pdf_to_csv.py "<PDF или каталог>" [--out CSV]

Дальше — обезличить образец:
    uv run spendtrack anonymize "<CSV>" "C:\\...\\образец.csv" --rows 0
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
DELIM = ";"


def extract_rows(src: Path) -> list[list[str]]:
    """Все непустые строки таблиц PDF (значения как есть; переносы внутри ячейки → пробел)."""
    import pdfplumber

    rows: list[list[str]] = []
    with pdfplumber.open(str(src)) as doc:
        for page in doc.pages:
            tables = page.extract_tables()
            if not any(tables):
                tables = page.extract_tables(
                    table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            for t in tables:
                for row in t or []:
                    if row and any((c or "").strip() for c in row):
                        rows.append([(c or "").replace("\n", " ").strip() for c in row])
    return rows


def split_header(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Шапка — ведущие строки до первой строки с датой; строки с числами (напр., «Входящий остаток»)
    считаются данными, а не шапкой (иначе суммы попадают в имена колонок)."""
    first = next((i for i, r in enumerate(rows) if r and DATE_RE.match(r[0])), None)
    if first is None:
        raise ValueError("не нашёл строк с датой (dd.mm.yyyy) — это точно выписка Приорбанка?")
    head: list[list[str]] = []
    pre_data: list[list[str]] = []
    for r in rows[:first]:
        if any(c and re.match(r"^\d", c) for c in r):
            pre_data.append(r)
        else:
            head.append(r)
    width = max(len(r) for r in rows)
    header = [" ".join(p for p in ((r[c] if c < len(r) else "") for r in head) if p).strip()
              for c in range(width)]
    return header, pre_data + rows[first:]


def drop_empty_columns(header: list[str], data: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    keep = [c for c in range(len(header))
            if header[c] or any(c < len(r) and r[c] for r in data)]
    return ([header[c] for c in keep],
            [[(r[c] if c < len(r) else "") for c in keep] for r in data])


def write_csv(out: Path, header: list[str], data: list[list[str]]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=DELIM)
        writer.writerow(header)
        writer.writerows(data)


def pick_pdf(arg: str) -> Path:
    src = Path(arg)
    if src.is_dir():
        pdfs = sorted(src.glob("*.pdf"))
        if len(pdfs) != 1:
            print(f"в каталоге {src}: PDF-файлов {len(pdfs)} — укажи файл явно", file=sys.stderr, flush=True)
            raise SystemExit(1)
        return pdfs[0]
    return src


def main() -> int:
    ap = argparse.ArgumentParser(description="Приорбанк: PDF-выписка → CSV (локально)")
    ap.add_argument("pdf", help="PDF или каталог с единственным PDF")
    ap.add_argument("--out", default=None, help="куда записать CSV (по умолчанию рядом с PDF)")
    args = ap.parse_args()

    src = pick_pdf(args.pdf)
    if not src.is_file():
        print(f"нет файла: {src}", file=sys.stderr, flush=True)
        return 1
    try:
        rows = extract_rows(src)
        header, data = split_header(rows)
        header, data = drop_empty_columns(header, data)
    except ImportError:
        print("нужен pdfplumber: uv run --with pdfplumber python scripts\\priorbank_pdf_to_csv.py ...",
              file=sys.stderr, flush=True)
        return 1
    except Exception as e:  # noqa: BLE001 — понятная ошибка без трейса (битый PDF/чужая форма)
        print(f"не удалось сконвертировать: {e}", file=sys.stderr, flush=True)
        return 1

    out = Path(args.out) if args.out else src.with_suffix(".converted.csv")
    write_csv(out, header, data)
    print(f"строк данных: {len(data)}; колонок: {len(header)}")
    print(f"CSV (PII — не пересылать; только для anonymize): {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
