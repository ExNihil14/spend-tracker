"""One-command ревью WIP-диффа: чек-лист + план-формат + diff (+ untracked) → OpenRouter :free ($0).

Автоматизирует наш ревью-процесс: чек-лист дисциплины данных включается в промпт, ответ требуется
«планом пунктами» (P0/P1 с фактами), галочки верифицирует оркестратор.

Использование:
    uv run python scripts/review.py --title "P0-долг" --notes facts.md [--out review.md] [--dry-run]
    # реальный прогон 2–10 минут: лучше через D:\\dev\\bootstrap\\scripts\\start-detached.ps1
"""
from __future__ import annotations

import argparse
import json
import os
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


def _utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_checklist(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or EMBEDDED_CHECKLIST
    except OSError:
        return EMBEDDED_CHECKLIST


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                              encoding="utf-8", check=False).stdout
    except OSError:
        return ""


def collect_artifacts(repo: Path) -> tuple[str, str, dict[str, str]]:
    diff_stat = _git(repo, "diff", "--stat")
    diff = _git(repo, "diff")
    untracked = [p for p in _git(repo, "ls-files", "--others", "--exclude-standard").split() if p]
    extras: dict[str, str] = {}
    total = 0
    for rel in untracked:
        path = repo / rel
        if path.suffix not in (".py", ".md", ".toml", ".yml", ".yaml", ".json"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if total + len(text) > EXTRAS_LIMIT:
            break
        extras[rel] = text
        total += len(text)
    return diff_stat, diff, extras


def render_prompt(title: str, checklist: str, notes: str, diff_stat: str,
                  diff: str, extras: dict[str, str]) -> str:
    parts = [
        ("# Роль\nТы — строгий ревьюер Python/SQLite/FastAPI-кода (соло-проект). Оцениваешь по фактам,"
         " без теории и похвал. Не выдумывай; при нехватке данных пиши «недостаточно данных».\n"),
        f"# Что ревьюится: {title}\n",
        "# Чек-лист (пройди по каждому пункту)\n" + checklist + "\n",
        ("# Формат ответа (жёстко)\n"
         "1. Вердикт GO/NO-GO.\n"
         "2. P0/P1 **планом пунктами**: файл:строка, конкретный сценарий, ожидание vs факт, минимальная правка.\n"
         "3. Кратко: что НЕ покрыто тестами; отдельно — что заведомо проверено (не считать багом).\n"
         "Без P2, без похвал, ≤700 слов. Русский.\n"),
    ]
    if notes.strip():
        parts.append("# Факты от оркестратора (не считать багами)\n" + notes.strip() + "\n")
    parts.append("# Артефакт: git diff --stat\n```\n" + (diff_stat or "(пусто)") + "\n```\n")
    parts.append("# Артефакт: git diff\n```diff\n" + (diff or "(пусто)") + "\n```\n")
    if extras:
        parts.append("# Артефакт: untracked-файлы (полный текст)\n")
        for rel, text in extras.items():
            parts.append(f"## {rel}\n```\n{text}\n```\n")
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
    args = ap.parse_args(argv)

    notes = args.notes.read_text(encoding="utf-8") if args.notes and args.notes.exists() else ""
    diff_stat, diff, extras = collect_artifacts(args.repo)
    prompt = render_prompt(args.title, load_checklist(args.checklist), notes, diff_stat, diff, extras)
    out = args.out or Path(tempfile.gettempdir()) / f"spendtrack-review-{int(time.time())}.md"

    if args.dry_run:
        out.write_text(prompt, encoding="utf-8")
        print(f"dry-run: промпт {len(prompt)} символов → {out}")
        return 0

    t0 = time.time()
    content, usage = call_openrouter(prompt, args.model, args.max_tokens)
    header = (f"# Ревью: {args.title} — {args.model} (OpenRouter :free)\n"
              f"- время: {time.time() - t0:.0f}s; usage: {json.dumps(usage, ensure_ascii=False)}\n\n---\n\n")
    out.write_text(header + content + "\n", encoding="utf-8")
    print(f"DONE {time.time() - t0:.0f}s → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
