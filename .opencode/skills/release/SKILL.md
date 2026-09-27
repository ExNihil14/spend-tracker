---
name: release
description: Релизный контур spend-tracker: тег vX.Y.Z, CHANGELOG, пиннинг URL установщиков на тег, заморозка main, Windows-CI, ручные прогоны на VM. Use when готовится релиз/тег, правится установщик или замораживается main.
---

# Релиз spend-tracker

Порядок: контур → тексты → пиннинг → тег → заморозка → ручные прогоны. Коммит, push и тег — только по явной команде юзера; тег и заморозка необратимы.

## Шаги
1. **Контур зелёный:** `uv run pytest`, `uv run pytest tests/e2e -m e2e`, `uv run ruff check .`, `uv run python scripts/contract_delta.py check`, `uv run python scripts/ratchet.py check`, `uv run python scripts/build_css.py --check`. При осознанном изменении контракта — `contract_delta.py snapshot` в том же коммите.
2. **Доки без противоречий:** `tests/test_docs_consistency.py` — гейт (машино-проверяемые каноны);
   семантический contradiction-прогон по `spec/PIPELINE.md` §Contradiction-check — рекомендательный
   (проверяет CHANGELOG/PRIVACY/SECURITY и соответствие поведению; находки — адъюдикация фактами, правки тем же коммитом).
3. **CHANGELOG** `[X.Y.Z]` — Added/Changed/Fixed/Security + дата; версия SemVer `0.x.y`; историчные разделы не переписывать.
4. **Визуальные ассеты актуальны:** после UI-правок пересняты GIF и README-скриншоты
   (`uv run python scripts/record_demo_gif.py`, `uv run python scripts/record_readme_screens.py`);
   зелёные `tests/test_demo_gif.py`, `tests/test_readme_screens.py`.
5. **Пиннинг установщиков:** команды в `install.ps1`/`install.sh`, README и лендинге — на тег/релиз-ветку (`raw.githubusercontent.com/.../vX.Y.Z/...`), не на `main`; рядом с `irm | iex` — ссылка «посмотреть скрипт».
6. **Тег:** аннотированный `git tag -a vX.Y.Z -m "..."` (push — по команде юзера).
7. **Заморозка `main`** на окно релиза (фиксация SHA, чужие merge — нет), затем снять.
8. **Windows-CI:** джоб `windows-latest` (смоук `uv tool install --from .` + `serve`) в `.github/workflows/ci.yml`.
9. **Ручные прогоны (за юзером):** чистые Windows/macOS/Linux — install → первый дайджест ≤10 мин; 0 issues «установка не удалась».
10. **Pages:** лендинг деплоится workflow при push в `main` — после релиза открыть живой URL.

## Gotchas
- Trunk-based: длинных веток нет (только `feature|fix|chore/<slug>` от `main`); merge — `--ff-only` после `rebase`.
- `git push --force` и `git reset --hard` на `main` запрещены; никаких `develop`/`release-*`.
- Прод NSSM 8766 живёт отдельно: при Python-правках — `nssm restart spendtrack`; тег сам прод не обновляет.
- Контур без e2e неполный (e2e исключён из `addopts`), без `contract_delta check` — опасен.
