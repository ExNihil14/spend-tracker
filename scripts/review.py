"""One-command ревью WIP-диффа: чек-лист + план-формат + diff (+ untracked) → OpenRouter :free ($0).

Автоматизирует наш ревью-процесс: чек-лист дисциплины данных включается в промпт, ответ требуется
«планом пунктами» (P0/P1 с фактами), галочки верифицирует оркестратор.

Использование:
    uv run python scripts/review.py --title "P0-долг" --notes facts.md [--out review.md] [--dry-run]
    # реальный прогон 2–10 минут: лучше через D:\\dev\\bootstrap\\scripts\\start-detached.ps1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_CHECKLIST = Path(r"D:\dev\docs\machine\REVIEW_CHECKLIST.md")
EMBEDDED_CHECKLIST = """1. Границы: репозитории возвращают immutable (tuple/frozen)?
2. Мутации: функции не меняют аргументы; обновления — new-state?
3. Общие ссылки: нет shared mutable между слоями; связь через API/события?
4. Контракты: валидация на границе; публичные сигнатуры не менялись без тикета?
5. Тесты: на публичный интерфейс; переживут смену реализации?
6. Структуры/очереди: семантика через интерфейс, не Array-жонглирование?
7. Инфраструктура: in-memory там, где нет персистентности; без лишних MQ?
8. AI-код: вычитан человеком (не «принято на веру»)?
9. История/undo: откат к консистентному состоянию, не посимвольно?
10. Контракт-дельта: публичные сигнатуры/поля БД до/после совпадают?"""
EXTRAS_LIMIT = 120_000
# Дефолт 1500 строк ≈ 40–60K символов диффа: комфортно для бесплатных каналов (nemotron-3-ultra, 1M ctx, 20 RPM)
# с запасом на чек-лист и untracked-файлы; переопределяется --max-diff-lines или REVIEW_MAX_DIFF_LINES.
MAX_DIFF_LINES = 1500


def _utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_checklist(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or EMBEDDED_CHECKLIST
    except OSError:
        print(f"review: чек-лист не найден ({path}) — использую встроенный", file=sys.stderr, flush=True)
        return EMBEDDED_CHECKLIST


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                              encoding="utf-8", check=False).stdout
    except OSError:
        return ""


def collect_artifacts(repo: Path) -> tuple[str, str, dict[str, str], list[str]]:
    """→ (diff_stat, diff, extras, skipped). Дифф — против HEAD (ловит и staged, и unstaged)."""
    diff_stat = _git(repo, "diff", "HEAD", "--stat")
    diff = _git(repo, "diff", "HEAD")
    untracked = [p for p in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    extras: dict[str, str] = {}
    skipped: list[str] = []
    total = 0
    for rel in untracked:
        path = repo / rel
        if path.suffix not in (".py", ".md", ".toml", ".yml", ".yaml", ".json",
                               ".js", ".mjs", ".html", ".css", ".sql", ".ps1"):
            continue
        if _is_sensitive(rel):
            skipped.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if total + len(text) > EXTRAS_LIMIT:
            skipped.append(rel)
            continue
        extras[rel] = text
        total += len(text)
    return diff_stat, diff, extras, skipped


SENSITIVE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pous]_[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
# Кандидат в номер карты: 12–19 цифр подряд или с одиночными пробелами/дефисами.
# Решение — `_card_like`: SVG-path («4 4 0 1 1-8…») — россыпь одиночных цифр, картой не считается.
CARD_CANDIDATE = re.compile(r"(?<!\d)(\d(?:[ -]?\d){11,18})(?!\d)")


def _card_like(raw: str) -> bool:
    """Печатная форма карты: 13–19 цифр — сплошняком либо группами по ≥3 (4/4/4/4, 4/6/5).

    Жадный захват может прихватить хвост («…1111 12/26» → группа «12»), поэтому короткие
    крайние группы (1–2 цифры) отбрасываем до проверки, а не отвергаем кандидата целиком
    (ревью Sonnet 5.5, 30.09: иначе карта с датой/CVV уходила наружу).
    """
    groups = re.split(r"[ -]", raw)
    while len(groups) > 1 and len(groups[0]) < 3:
        groups.pop(0)
    while len(groups) > 1 and len(groups[-1]) < 3:
        groups.pop()
    digits = sum(len(g) for g in groups)
    if not 13 <= digits <= 19:
        return False
    return len(groups) == 1 or (len(groups) >= 3 and min(len(g) for g in groups) >= 3)


def _is_sensitive(rel: str) -> bool:
    """Пути, которые не отправляем наружу (реальные выписки/фикстуры/локальные конфиги/секреты)."""
    name = rel.lower()
    return (
        name.startswith((".env", "data/"))
        or "/.env" in name
        or "fixtures/real" in name
        or "tests/fixtures/" in name
        or ".local." in name
        or name.endswith((".pem", ".key", ".pfx", ".csv", ".sqlite", ".db"))
    )


def _is_generated(rel: str) -> bool:
    """Сгенерированное/вендорное — не считаем в лимит диффа (но секрет-скан остаётся)."""
    name = rel.lower()
    return (
        name == "uv.lock"
        or name.endswith(".min.js")
        or Path(name).name == "app.css"  # prebuilt Tailwind (имя файла, не путь — устойчиво к переносу)
        or (name.startswith("spec/") and name.endswith("_baseline.json"))
    )


def summarize_numstat(text: str) -> tuple[int, list[tuple[int, str]]]:
    """`git diff --numstat` → (всего строк без сгенерированного, [(строк, путь)] по убыванию)."""
    rows: list[tuple[int, str]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-":  # бинарный файл
            continue
        if _is_generated(path):
            continue
        rows.append((int(added) + int(deleted), path))
    rows.sort(reverse=True)
    return sum(n for n, _ in rows), rows


def secret_hits(text: str) -> list[str]:
    """Совпадения секрет-паттернов (маскированные) — для abort перед отправкой во внешний канал."""
    hits: list[str] = []
    for pat in SENSITIVE_PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0)
            hits.append(f"{val[:8]}…({len(val)} симв)")
    for m in CARD_CANDIDATE.finditer(text):
        val = m.group(1)
        if _card_like(val):
            hits.append(f"{val[:8]}…({len(val)} симв)")
    return hits


def render_prompt(title: str, checklist: str, notes: str, diff_stat: str,
                  diff: str, extras: dict[str, str], skipped: list[str] | None = None) -> str:
    parts = [
        ("# Роль\nТы — строгий ревьюер Python/SQLite/FastAPI-кода (соло-проект). Оцениваешь по фактам,"
         " без теории и похвал. Не выдумывай; при нехватке данных пиши «недостаточно данных».\n"),
        f"# Что ревьюится: {title}\n",
        "# Чек-лист (пройди по каждому пункту)\n" + checklist + "\n",
        ("# Формат ответа (жёстко)\n"
         "1. Вердикт GO/NO-GO.\n"
         "2. Находки — **только блокирующие мерж**, планом пунктами (P0/P1): файл:строка, почему неверно,"
         " как показать, что падает, минимальная правка. Без P2 и похвал, ≤700 слов. Русский.\n"
         "3. Отдельно: что не удалось подтвердить (и где смотрел); что заведомо проверено"
         " (не считать багом).\n"),
    ]
    if notes.strip():
        parts.append("# Факты от оркестратора (не считать багами)\n" + notes.strip() + "\n")
    parts.append("# Артефакт: git diff --stat\n```\n" + (diff_stat or "(пусто)") + "\n```\n")
    parts.append("# Артефакт: git diff\n```diff\n" + (diff or "(пусто)") + "\n```\n")
    if extras:
        parts.append("# Артефакт: untracked-файлы (полный текст)\n")
        for rel, text in extras.items():
            parts.append(f"## {rel}\n```\n{text}\n```\n")
    if skipped:
        parts.append("# ВНИМАНИЕ: не включены файлы (лимит размера или чувствительные пути)\n"
                     + "\n".join(f"- {s}" for s in skipped) + "\n")
    return "".join(parts)


def openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key and sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "OPENROUTER_API_KEY")[0]
        except (OSError, ImportError):
            pass
    if not key:
        raise SystemExit("OPENROUTER_API_KEY не найден (env/User-env)")
    return key


def call_openrouter(prompt: str, model: str, max_tokens: int) -> tuple[str, dict]:
    import httpx

    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.3}
    headers = {"Authorization": f"Bearer {openrouter_key()}", "Content-Type": "application/json",
               "HTTP-Referer": "https://localhost/spend-tracker", "X-Title": "spend-tracker-review"}
    last: Exception | None = None
    for attempt in (1, 2):
        try:
            with httpx.Client(    timeout=httpx.Timeout(float(os.environ.get("REVIEW_TIMEOUT", "900")), connect=15.0)) as c:
                r = c.post("https://openrouter.ai/api/v1/chat/completions",
                           headers=headers, json=payload)
            if r.status_code == 200:
                body = r.json()
                content = body["choices"][0]["message"].get("content") or ""
                if content.strip():
                    return content, body.get("usage", {})
                last = RuntimeError("пустой ответ провайдера")
            else:
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(15 * attempt)
    raise SystemExit(f"OpenRouter не ответил: {last}")


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(prog="review", description="Ревью WIP-диффа через OpenRouter :free")
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--title", default="WIP-дифф")
    ap.add_argument("--notes", type=Path, help="файл с фактами/проверенным (не считать багами)")
    ap.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="только собрать промпт, без вызова модели")
    ap.add_argument("--max-diff-lines", type=int,
                    default=int(os.environ.get("REVIEW_MAX_DIFF_LINES", MAX_DIFF_LINES)),
                    help="лимит строк диффа (без сгенерированного) для одного ревью; выше — отказ (rc=4)")
    args = ap.parse_args(argv)

    notes = args.notes.read_text(encoding="utf-8") if args.notes and args.notes.exists() else ""
    diff_stat, diff, extras, skipped = collect_artifacts(args.repo)
    total_lines, rows = summarize_numstat(_git(args.repo, "diff", "HEAD", "--numstat"))
    if total_lines > args.max_diff_lines:
        top = ", ".join(f"{path} ({n})" for n, path in rows[:5]) or "(нет текстовых файлов)"
        print(f"review: дифф слишком большой для одного ревью — {total_lines} строк > "
              f"{args.max_diff_lines} (сгенерированное не считаем). Крупнейшие: {top}. "
              "Режьте по модулям (отдельные прогоны/ветки), иначе модель увидит часть диффа и выдаст «OK».",
              file=sys.stderr, flush=True)
        if not args.dry_run:
            return 4
    prompt = render_prompt(args.title, load_checklist(args.checklist), notes, diff_stat, diff,
                           extras, skipped)
    out = args.out or Path(tempfile.gettempdir()) / f"spendtrack-review-{int(time.time())}.md"
    base_sha = _git(args.repo, "rev-parse", "--short", "HEAD").strip() or "?"
    diff_sha = hashlib.sha1(diff.encode("utf-8", "replace")).hexdigest()[:12]

    if not diff.strip() and not extras:
        print("review: нечего ревьюить (пустой дифф против HEAD и нет untracked-файлов) — "
              "сначала изменения, затем ревью", file=sys.stderr, flush=True)
        return 2
    hits = secret_hits(prompt)
    if hits:
        print("review: СТОП — в промпте похожие на секреты строки (наружу не отправляю): "
              + ", ".join(hits[:5]), file=sys.stderr, flush=True)
        return 3
    if skipped:
        print(f"review: не включены файлы: {', '.join(skipped)}", flush=True)

    if args.dry_run:
        out.write_text(prompt, encoding="utf-8")
        print(f"dry-run: промпт {len(prompt)} символов → {out} (base_sha={base_sha}, diff_sha={diff_sha})")
        return 0

    t0 = time.time()
    content, usage = call_openrouter(prompt, args.model, args.max_tokens)
    header = (f"# Ревью: {args.title} — {args.model} (OpenRouter :free)\n"
              f"- base_sha: {base_sha}; diff_sha: {diff_sha}\n"
              f"- время: {time.time() - t0:.0f}s; usage: {json.dumps(usage, ensure_ascii=False)}\n\n---\n\n")
    out.write_text(header + content + "\n", encoding="utf-8")
    print(f"DONE {time.time() - t0:.0f}s → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
