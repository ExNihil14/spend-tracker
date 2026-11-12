# Spendtrack — AGENTS.md

## Что это
Трекер расходов с LLM-категоризацией. FastAPI + SQLite + htmx, offline-first детерминированное ядро, LLM-шов только для остатка (~30-40% транзакций).

## Старт сессии
- **Всегда:** `continue.md` — активный срез (состояние, шаги, блокеры).
- **По триггеру:** архитектура/контракты → `spec/ARCHITECTURE.md`; команды/верификация → `spec/PIPELINE.md` + `spec/stack.md`; очередь `/approve`/категоризация → `spec/QA_APPROVE_SMOKE.md`; термины → `CONTEXT.md`; практики/промпты → `D:\dev\docs\vibecoding\out_analysis\MASTER_PLAN.md` (spec-раздел при изменениях).

## Команды
- Тест: `uv run pytest`
- Тяжёлые прогоны (pytest/e2e/логи) — через токен-раннер: `python D:\dev\bootstrap\scripts\compact_run.py -- uv run pytest -q`
  (полный вывод в `.logs/`, в контекст — только ошибки/хвост; playbook `D:\dev\docs\machine\TOKEN_OPTIMIZATION_PLAYBOOK.md`)
- Линт: `uv run ruff check .` (как в CI — покрывает и `scripts/`)
- Запуск: `uv run spendtrack serve` / `uv run uvicorn spendtrack.main:app --port 8766` (или `.\run.ps1`);
  remote capture — только отдельный `spendtrack capture-serve --port 8767 --token-file <file>`
  (Tailscale Serve → 8767, не 8766; текущий деплой — user Startup + 5-мин watchdog, admin task/NSSM optional)
- CLI: `uv run python -m spendtrack.cli add -23.45 "milk"` / `report` / `import file.csv --bank auto` / `count` / `confidence` (калибровка порога 0.9) / `budget` (прогресс по бюджетам) / `doctor` (целостность) / `recurring` (рекурринги/подписки) / `suggest-rules` (подсказки правил из правок) / `digest` (дайджест недели + аномалии) / `llm-status` (режим LLM: off/byo/ollama/free) / `export` (CSV/XLSX) / `backup` (снимок + offsite-копия) / `anonymize` (обезличить образец для issue) / `capture-serve` (capture-only listener)
- Верификация (правило из MASTER_PLAN.md): после изменений проверять факт (diff/запуск/UI в браузере), а не только отчёт

## Layout
- `config/settings.toml` — порт, LLM-эндпоинты (primary/fallback/offline), авто-приём confidence (0.9)
- `config/taxonomy.toml` — 18 категорий + keyword-правила (править БЕЗ кода)
- `src/spendtrack/` — `store.py` (SQLite, копейки INTEGER), `categorize.py` (rule→llm→validation→queue), `csv_import.py` (BANKS-адаптеры), `reports.py`, `export.py` (CSV/XLSX), `llm.py`+`prompts.py`, `routers/`, `cli.py`
- `data/spend.db` — автосоздаётся (WAL)
- `.opencode/skills/` — проектные скиллы (`bank-adapter` / `release` / `verify-spendtrack`); структура и живые
  указатели — `tests/test_skills.py`
- `tests/` — все оффлайн, LLM стабится (injectable classify/llm_getter), не трогать контракты тестов без причины

## Ключевые решения (не менять без ревью)
- Суммы = `amount_kopecks INTEGER` (копейки), НЕ REAL
- Валюта: `transactions.currency` ISO 4217 (миграция v5); fingerprint включает код ТОЛЬКО для не-RUB
  (рублёвые отпечатки неизменны); не-RUB исключён из ₽-агрегаций (отчёты/бюджеты/дайджест/рекурринги)
- Fingerprint-дедуп `sha1(date|amount|desc|account_anon|export_rowid)` — для валюты ≠ RUB в отпечаток добавляется суффикс `|CUR` (base-независимо); повторный импорт = no-op
- account псевдонимизируется (`account_pseudonyms`), сырые номера карт не хранятся
- Remote capture: единственная публикуемая поверхность — отдельный `capture-serve` (8767);
  главный UI 8766 в `tailscale serve` не указывать. `CaptureOnlyApp` решает path/token независимо
  от `Host`; `Host: 127.0.0.1` через Serve не должен открывать `/`/`/approve` (CAP-01 regression)
- Авто-приём категории от LLM при confidence ≥ 0.9, иначе → очередь «на подтверждение» (`review_status='pending'`, `category_llm` = предложение LLM)
- Правила детерминированные и тестируются на РЕАЛЬНЫХ описаниях (урок: «ЗАРПЛАТА» не ловит «ЗАРАБОТНАЯ»)
- Правка юзера → merchant_cache (выигрывает над LLM) + пример в few-shot
- LLM-маршрут (канон — `spec/ARCHITECTURE.md` §LLM-маршрут): BYO/Ollama (явный выбор, без фолбэков) → free-цепочка (OpenRouter :free → FreeLLMAPI → abacus-web shim; шимы — `SPENDTRACK_ALLOW_LOCAL_LLM=1`) → офлайн-правила (работают и без LLM вообще); статус — `spendtrack llm-status`

## Запросы решений owner
- Любой выбор/одобрение/приоритет — **отдельным сообщением с inline-кнопками**
  (single-choice; multi — только после v1.1). Не просить «напиши 1/2/3» текстом.
- В меню: действие + объект + эффект/риск/время; опасное — `⚠️`.
- Один запрос — один канонический menu ID; не дублировать меню и не повторять
  вопрос без новой вводной.
- Если решение требует laptop-действия, телефон передаёт выбор owner ноутбуку
  как `OC-CHOICE`/owner-go; push/live остаются отдельными точными командами.

## Не делать
- Не читать и не печатать значения из `.env*`/секретов без явного разрешения (наружу/в отчёты — только имена
  ключей; гейт `safety-gate` блокирует правки, это правило — про чтение и вывод).
- Не кидать сырые суммы REAL/DECIMAL в БД; деньги — только копейки INTEGER.
- Не тестировать через сеть: LLM всегда через стаб в тестах.
- Не добавлять pandas/embeddings в этом проекте (для RAG — отдельная вилка).
- Новые границы — иммутабельные: `tuple`/frozen, изменение — new-state (унаследованные `list[dict]` не расширять).
- Пользовательские строки/форматы — через хелперы (`fmt_amount` и т.п.), не склеивать в шаблонах/CLI;
  i18n — через `t()` и `config/locales/` (см. `DESIGN_I18N_LEGAL_A11Y.md`).
- UI готов только с базовой a11y: accessible-имя у полей, видимый `:focus-visible`.
- Новые тесты — на публичный интерфейс (CLI/роутер/Store), не на внутренние структуры; usage-first.
- Не фиксить баг без падающего регресс-теста: сначала красный тест, затем фикс «не трогая тест» (TDD; см. `D:\dev\docs\machine\MATTPOCOCK_SKILLS_AUDIT.md`).
- Не менять сигнатуры ядра (`store.py`/`categorize.py`, копейки/fingerprint/очереди) без тикета и ревью;
  после AI-рефакторинга — `uv run python scripts/contract_delta.py check` (CI-блокер); при осознанном
  изменении — `snapshot` и baseline в том же коммите (дисциплина данных — `D:\dev\docs\machine\REVIEW_CHECKLIST.md`).
- **Protected paths:** `spec/contract_baseline.json` (только `contract_delta.py snapshot`),
  `spec/ratchet_baseline.json` (только `scripts/ratchet.py snapshot`), `spec/cc_baseline.json`
  (только `scripts/cc_ratchet.py update`), `data/**`, `.env` — прямые правки блокирует `safety-gate.js`;
  деструктив (force-push/`reset --hard`/`rm -rf`/NSSM remove) — только после `/careful`.
- Не гонять итерации «вхолостую»: новая итерация — только с новой вводной (лог/замечание/новый тест);
  сигнатура падений не меняется — стоп и эскалация (см. `spec/PIPELINE.md` §AI-контур).
- Не отправлять в каналы ревью реальные выписки/фикстуры: наружу не уходят `data/**`, `tests/fixtures/**`,
  `*.csv/*.sqlite/*.db`; фикстуры — только синтетические; `done` — только после verify с `base_sha`/`diff_sha`.

## Git-процесс (из GIT_WORKFLOW_RECOMMENDATIONS.md)
- Trunk-based + короткие ветки: `feature/<slug>` (1-3 дня), `fix/<slug>`, `chore/<slug>`; `main` — единственная долгоживущая и всегда зелёная; develop/release/*/hotfix/* не создавать; после merge — `git branch -d`.
- НЕ коммитить без явной команды пользователя. НЕ пушить без отдельной явной команды.
- Перед коммитом: `uv run pytest && uv run ruff check`. Красные тесты — не коммитить.
- Один коммит = один смысловой блок (Conventional Commits). Не смешивать рефакторинг и фичу.
- Merge в main: `git rebase main` → `git switch main && git merge --ff-only`; merge-коммиты не делать. Squash — только для wip/опечаток.
- НИКОГДА `git push --force` и `git reset --hard` на main; только на своей ветке и с подтверждения.
- НЕ коммитить: `.env`, `data/`, `*.sqlite`, ключи, токены.
- Версии: SemVer `0.x.y` + аннотированные теги; CHANGELOG — из Conventional Commits.
- Перед отчётом о готовности: показать `git status` и `git diff --stat` (факт, не слова).
