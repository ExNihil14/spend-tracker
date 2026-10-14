"""Структурная проба PDF-выписки: текст + маскированный скелет (PII наружу не уходит).

Зачем: анонимайзер понимает только CSV/XLSX, а сырьё не должно покидать машину или попадать в LLM.
Проба вытаскивает текстовый слой (pypdf) и пишет ДВА файла рядом (или по --out-prefix):
  * <prefix>.text.txt   — полный текст; ТОЛЬКО для глаз владельца, НЕ пересылать и не публиковать;
  * <prefix>.masked.txt — тот же текст с маскировкой: буквы → X, цифры → #; пунктуация, пробелы и
    переводы строк сохраняются. Структура таблицы/колонок видна, данные — нет; ЭТОТ файл безопасно
    показать агенту для разработки парсера.
С `--tables` дополнительно пишется <prefix>.tables.masked.txt — маскированный дамп таблиц
(pdfplumber): видны форма колонок и строки, значения — нет.

Запуск (из корня spend-tracker, сырьё — в D:\\data\\finance\\statements\\<bank>\\raw\\):
    uv run --with pypdf python scripts\\pdf_statement_probe.py "<файл>.pdf" --out-prefix "%TEMP%\\pdf_probe"
    uv run --with pypdf --with pdfplumber python scripts\\pdf_statement_probe.py "<каталог>" --tables --out-prefix ...

Коды выхода: 0 — ок; 1 — ошибка/нет текстового слоя (похоже на скан).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mask(text: str) -> str:
    """Буквы → X, цифры → #; остальное (пунктуация/пробелы/переводы строк) сохраняется.

    Длины числовых групп сохраняются осознанно: по ним виден формат сумм/дат (###,## / ##.##.####),
    который нужен парсеру; сами значения не раскрываются.
    """
    return "".join("#" if ch.isdigit() else ("X" if ch.isalpha() else ch) for ch in text)


def pick_pdf(arg: str) -> Path:
    """Путь к PDF или каталог с единственным PDF."""
    src = Path(arg)
    if src.is_dir():
        pdfs = sorted(src.glob("*.pdf"))
        if len(pdfs) != 1:
            print(f"в каталоге {src}: PDF-файлов {len(pdfs)} — укажи файл явно", file=sys.stderr, flush=True)
            for p in pdfs:
                print(f"  {p.name}", file=sys.stderr, flush=True)
            raise SystemExit(1)
        return pdfs[0]
    return src


def extract_text(src: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    return [page.extract_text() or "" for page in reader.pages]


def dump_tables(src: Path, prefix: Path) -> tuple[int, int, int]:
    """Маскированный дамп таблиц (pdfplumber). → (страниц всего, страниц с таблицами, строк)."""
    import pdfplumber

    dump: list[str] = []
    pages_with = rows = 0
    with pdfplumber.open(str(src)) as doc:
        total = len(doc.pages)
        for i, page in enumerate(doc.pages, 1):
            tables = page.extract_tables()
            if not any(tables):
                tables = page.extract_tables(
                    table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
            good = [t for t in tables if t]
            if good:
                pages_with += 1
            dump.append(f"### page {i}: tables={len(good)}")
            for t in good:
                for row in t:
                    rows += 1
                    dump.append(" | ".join(mask((c or "").replace("\n", " ")) for c in row))
    Path(str(prefix) + ".tables.masked.txt").write_text("\n".join(dump), encoding="utf-8")
    return total, pages_with, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF-выписка: текст + маскированный скелет")
    ap.add_argument("pdf", help="путь к PDF-выписке или каталог с единственным PDF")
    ap.add_argument("--out-prefix", default=None,
                    help="префикс выходных файлов (по умолчанию — рядом с PDF, без расширения)")
    ap.add_argument("--tables", action="store_true",
                    help="дополнительно: маскированный дамп таблиц (pdfplumber)")
    args = ap.parse_args()

    src = pick_pdf(args.pdf)
    if not src.is_file():
        print(f"нет файла: {src}", file=sys.stderr, flush=True)
        return 1
    try:
        pages = extract_text(src)
    except ImportError:
        print("нужен pypdf: uv run --with pypdf python scripts\\pdf_statement_probe.py ...",
              file=sys.stderr, flush=True)
        return 1
    except Exception as e:  # noqa: BLE001 — битый/зашифрованный PDF: понятная ошибка, не трейс
        print(f"не удалось прочитать PDF: {e}", file=sys.stderr, flush=True)
        return 1

    text = "\n".join(pages)
    prefix = Path(args.out_prefix) if args.out_prefix else src.with_suffix("")
    text_path = Path(str(prefix) + ".text.txt")
    masked_path = Path(str(prefix) + ".masked.txt")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    masked_path.write_text(mask(text), encoding="utf-8")

    chars = sum(1 for c in text if not c.isspace())
    print(f"страниц: {len(pages)}; непустых символов текста: {chars}")
    print(f"полный текст (НЕ пересылать): {text_path}")
    print(f"скелет для агента (безопасно): {masked_path}")

    if args.tables:
        try:
            total, pages_with, rows = dump_tables(src, prefix)
        except ImportError:
            print("нужен pdfplumber: uv run --with pypdf --with pdfplumber python ...",
                  file=sys.stderr, flush=True)
            return 1
        print(f"таблицы (маскированные): {prefix}.tables.masked.txt")
        print(f"страниц с таблицами: {pages_with} из {total}; строк всего: {rows}")

    if chars < 40 * max(1, len(pages)):
        print("ПОХОЖЕ НА СКАН: текстовый слой почти пуст — нужен OCR или машиночитаемая выписка.",
              file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
