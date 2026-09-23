# Continue.md — состояние проекта Spendtrack

Обновляй ПОСЛЕ каждого крупного решения (правило из 20 стримов Вайбкодинга:
состояние живёт в файле, а не в истории диалога). Резюмируй короче pre-commit.

## Статус
- Проект: трекер расходов с LLM-категоризацией. FastAPI + htmx + SQLite + Tailwind.
- Репозиторий: `D:\dev\personal\spend-tracker` (public, https://github.com/ExNihil14/spend-tracker).
- Стек: uv/Python 3.13, pytest (+Playwright e2e), ruff.
- IDE: VS Code 1.137 + 13 расширений (Ruff, Pylance, официальный FastAPI, Playwright, Jinja2, htmx-toolkit, SQLite viewer, TOML, GitLens, Tailwind, EditorConfig, dotenv, Error Lens). Настройки в `.vscode/` (в репо): Ruff-форматтер Python, Pylance `standard`, pytest Test Explorer.
- Готово: Фаза B, импорт банка (Work 2, `422a56f`), circuit breaker+E2E (`833c48c`),
  очередь подтверждения (Work 3, `0b746d6` + e2e-хвост `511b630`), /settings Фазы 1-3 (категории `c9c42c4`,
  правила `973d280`, переименование `2e12d6c`), README/фиксы (`6d01458`), Codespaces (`1c684e4`), пикеры (`efe7cc7`),
  калибровка (`7f2ed66`), бюджеты (`73cc5fa`), фикс дашборда (`3076473`), CI e2e-джоб (`e5b13ac`).
  **331 unit + 19 e2e зелёные** (см. «АКТУАЛЬНО»).
- ✅ **README под практики 2026 + фиксы** (`2872bae`, `c58dcf0`, `6d01458`, запушены): структура-«шлюз», 3 скриншота
  `assets/`, `.env` теперь читается (`env_file` в `config.py` + `tests/test_config.py`), бейдж «Подтвердить» на
  `/settings` (был 0), `LICENSE` (MIT). Ресёрч-дайджест: `D:\dev\docs\machine\README_BEST_PRACTICES_2026.md`.
- ✅ **Codespaces-стенд работает** (запущен юзером, записи через `review_demo.py seed` / импорт синтетики). Фикс авто-старта
  `1c684e4` (start-app.sh + postAttach; требует Rebuild Container). Ресёрч: `D:\dev\docs\machine\RESEARCH_HOSTING_SPENDTRACKER.md`
  (① Codespaces; ② Render/Tailscale — компромиссы).
- ✅ **UI-пикеры** (`efe7cc7`): `cursor:pointer` + тёмная схема popup (`color-scheme: dark`), accent-color, индикатор
  календаря; e2e расширен (cursor + colorScheme). Ресёрч date-picker: `D:\dev\docs\machine\RESEARCH_DATEPICKER_SPENDTRACKER.md`
  (вердикт — нативный; кастом №1 Air Datepicker, №2 Vanilla Calendar Pro — если после смоука захочется).
- ✅ **Бюджеты по категориям** (`73cc5fa`, запушено; дизайн `EXPERT_BUDGETS_DESIGN.md`): миграция v4 `budgets`,
  редактор в `/settings`, бары «Бюджеты месяца» на `/dashboard`, `GET /api/budgets`, CLI `spendtrack budget`;
  rename/delete мигрируют бюджет. Отклонено: rollover, месячные переопределения, уведомления.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO — приняты клэмп `max(0, spent)`, hardening clear_budget,
  граничные тесты; часть P0/P1 отклонена фактами** (`EXPERT_REVIEW_BUDGETS_OR.md`).
  **Прод-NSSM актуален с 16.09 13:08** (`nssm restart spendtrack`; v4 применена, `/api/budgets` 200, стрелки дашборда абсолютные).
- ✅ **Anti-freeze фикс (15.09):** `D:\dev\bootstrap\scripts\start-detached.ps1` — запуск долгоживущих процессов
  через WMI (`Win32_Process.Create`) ВНЕ job-объекта bash-тула: лаунчер возвращается за 1с (Start-Process висел
  до таймаута 60-120с). Правило обновлено в глобальном `AGENTS.md` + `ANTI_FREEZE_RUNBOOK.md`; проверено dummy-процессом.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — по P0.1 скрипт переписан на temp-`.ps1`
  (нет интерполяции CommandLine, кавычки/пробелы ок) + логи UTF-8; остальные P0/P1 ревьюера — false positives
  (entry point/`.gitignore`/ссылки проверены фактами).** Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_README_OR.md`.
- ✅ **Калибровка порога 0.9 — инструмент готов** (`reports.confidence_calibration` +
  CLI `uv run python -m spendtrack.cli confidence`): бакеты conf с согласием/исправлениями человека + кандидатные
  пороги 0.4–0.9 (покрытие и % ошибок). Live по проду: LLM-предложений 8, решено 2 (1 исправлен), в очереди 6 →
  «данных мало (<20), оценка ориентировочная». Гонять по мере накопления; решение по порогу — когда решённых ≥20.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — приняты guard `category_llm != ''` и
  числовая сортировка бакетов (+2 теста); P0 про NULL/CI-тест отклонены фактами** (NOT NULL-колонка; тест видит ту же БД).
  Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_CONFIDENCE_OR.md`.
- ✅ **/settings Фаза 3 — переименование категории** (`2e12d6c`, ждёт push): preview с числом затронутых строк →
  подтверждение → миграция TOML (имя + правила) + БД (transactions.category/category_llm, merchant_cache, examples)
  одной транзакцией; откат БД при сбое TOML; аудит-сбой больше не роняет операцию.
  **Ревью OpenRouter (nemotron-3-ultra-550b:free, $0): GO с правками — P1.4 (same-name) и P1.6 (preview hash) применены;
  P0-замечания отклонены как false positives после верификации** (мёртвые SQLite-таблицы; ключ merchant_cache не зависит
  от категории). Артефакт: `D:\dev\docs\machine\EXPERT_REVIEW_SETTINGS_PHASE3_OR.md`.

## Что сделано
- Ядро детерминированное оффлайн: `store.py` (SQLite, WAL, копейки INTEGER),
  `categorize.py` (rule → LLM → validation → queue), `csv_import.py` (BANKS-адаптеры),
  `reports.py`, `llm.py` + `prompts.py` (free models), `routers/`, `cli.py`.
- Тесты: **96 unit + 10 e2e** (Playwright), все оффлайн (LLM инжектируемый стаб).
- 18 категорий + keyword-правила в `config/taxonomy.toml` (правятся без кода).
- Fingerprint-дедуп `sha1(date|amount|desc|account_anon|export_rowid)` — повторный импорт no-op.
- LLM-фолбэк (канон — `spec/ARCHITECTURE.md` §LLM-маршрут): OpenRouter :free → FreeLLMAPI (резерв, WSL на паузе) → **DeepSeek V4.1 Flash (abacus-web shim, порт 3201)** → оффлайн (правила работают и без LLM).
- Авто-приём категории при confidence ≥ 0.9, иначе `llm_pending_review` → очередь.
- Лог бакетов confidence (для калибровки порога).
- UI: Tailwind v4 vendored (static/tailwind.js), card-summary, stripes, responsive grid.

## Архитектурные решения (зафиксировано, менять только через spec/review)
- Суммы = `amount_kopecks INTEGER` (копейки), НЕ REAL/DECIMAL.
- Проект без pandas/embeddings — для RAG отдельная вилка.
- тесты не ходят в сеть: LLM всегда стаб.

## Git-процесс (принято 13.09, из GIT_WORKFLOW_RECOMMENDATIONS.md — DeepSeek v4.1 Flash)
- Trunk-based + короткие feature-ветки: `main` (всегда зелёная) + `feature/<slug>` / `fix/<slug>` / `chore/<slug>`.
- НИКАКИХ develop/release/hotfix для solo. Merge: `git rebase main` → `--ff-only`. Squash только wip.
- Один публичный репо; `data/` (SQLite с расходами) + `.env` полностью вне git (gitignore расширен).
- SemVer `0.x.y` + аннотированные теги; CHANGELOG.md из Conventional Commits (когда понадобится).
- Правила для агента — в AGENTS.md (не коммитить/пушить без явной команды, pytest+ruff перед коммитом).
- Полный отчёт: `D:\dev\docs\machine\GIT_WORKFLOW_RECOMMENDATIONS.md`.
- ✅ **ОПУБЛИКОВАНО 13.09**: remote origin = https://github.com/ExNihil14/spend-tracker (public), ветка `master`→`main` переименована, первый push сделан, vanity: gh CLI установлен (v2.100.0, PATH: C:\Program Files\GitHub CLI\gh.exe), авторизация ExNihil14 (OAuth, repo scope).
- ✅ **Защита main на GitHub**: force-push запрещён, deletions запрещены, required_linear_history (только --ff-only), enforce_admins=true. PR-ритуал не обязателен для solo (см. отчёт, п.9).

## Что активно / в работе
> **АКТУАЛЬНО (23.09, вечер-2, сессия «cooldown/очередь в плагине AgentRouter» — dev-tooling; репо-код не менялся).**
> Deliverable: WAF-защита в плагине `~/.config/opencode/plugins/agentrouter-ua.js` (после бана IP 23.09):
> ① FIFO-сериализация запросов к AgentRouter (в полёте ≤1); ② `AGENTROUTER_MIN_INTERVAL_MS`=1500 мс между
> стартами; ③ cooldown после WAF-ответа (405/429; 403 + HTML «not allowed/blocked/potential threats») с
> эскалацией 60с→120с→…→30 мин и сбросом на успехе; ④ fast-fail: ожидание дольше `AGENTROUTER_WAIT_MAX_MS`
> =120с → мгновенный 503 `error.type=agentrouter_cooldown` (без молчаливого зависания); ⑤ ожидание
> abort-совместимо (AbortError; отменённый запрос не уходит на сервер). Образец — npm-референс
> `opencode-agentrouter@1.3.0` (`withClaudeQueue`), но мягче (без 30-кратных ретраев).
> **Канон:** `D:\dev\bootstrap\config\plugins\agentrouter-ua.js` (bootstrap README обновлён: config/plugins +
> строки скриптов; правило «живой конфиг = копия канона»); **тест:**
> `D:\dev\bootstrap\scripts\agentrouter_plugin_test.mjs` — 7 сценариев / **38 проверок** на мок-сервере
> (база/санитизация/SSE, FIFO+min-интервал, cooldown+эскалация+403, изоляция чужих хостов, abort×2,
> fast-fail, sync канона) — зелёные (портативный Node 24); temp-копия теста заменена делегатором.
> Ревью $0 (kilo/nemotron-3-ultra:free, 214 с, $0): GO; принят 1 реальный P1 (abort при нулевом ожидании
> мог отправить запрос) + расширены тест-запасы; артефакт `EXPERT_REVIEW_AGENTROUTER_COOLDOWN_KILO_2026-09-23.md`.
> AgentRouter не трогали (IP под баном). Плагин вступит в силу после рестарта opencode. **Факт от юзера:**
> в Abacus появилась модель **Opus-5.5** (кандидат в тяжёлые ревью). Следующее: рестарт opencode (юзер) →
> проверка плагина живой сессией AgentRouter (1 редкий запрос, после разбана/смены IP); задачи из стартера.
> **Бонус-задача («продолжи по приоритету»): ② Habr-RSS дайджест — эксперимент выполнен.** Инструмент
> `D:\dev\bootstrap\scripts\habr_digest.py` (stdlib): discovery — внутренний JSON-API Habr `/kek/v2/articles/`
> (perPage≤20; периоды daily/weekly/alltime; score/плюсы/комментарии/закладки/теги/лид), фолбэк — RSS
> (articles/hub-AI/top, без статистики); фильтр тем по тегам+заголовку (лид исключён — «агент разведки» давал
> ложные срабатывания); секции «Топ окна» и «Свежее»; `--json` (items+matched) для будущего LLM-скрининга.
> Первый дайджест: `D:\dev\docs\habr\digest-2026-09-23.md` (60 статей, 16 релевантных); вердикт и факты API —
> `D:\dev\docs\habr\README.md`. Следующее (по желанию): LLM-скрининг free-каналом + еженедельный запуск.
> **Доп. задача (по запросу; канал разблокирован 23.09 ~17:20): WAF-безопасная стратегия запросов к AgentRouter.**
> Ресёрч primary sources — `RESEARCH_AGENTROUTER_WAF_STRATEGY.md` (AWS full jitter, RFC 9110/6585,
> Stripe/Anthropic token bucket, Google SRE retry budget, RFC 5681 AIMD, Cloudflare/AWS WAF; ToS agentrouter:
> запрещены «prolonged uninterrupted automated polling» и обход лимитов). Плагин v3: джиттер интервала
> (`AGENTROUTER_JITTER`=0.3, база 2000 мс), token bucket (`RATE_PER_MIN`=20, `BURST`=2), AIMD (WAF ×2 → до 60 с;
> серия успехов ×0.8 до базы), `Retry-After` (обе формы RFC 9110) с довеском, ретраев нет (один слой —
> вызывающий). `agentrouter_chat.py` — full-jitter backoff, Retry-After, no-retry 403/405 и прочих 4xx;
> `agentrouter_probe.py` — пауза 3 с. Тест: **12 сценариев / 52 проверки** зелёные; ревью $0 (kilo/nemotron) —
> направление GO, приняты клэмп джиттера и +3 теста (`EXPERT_REVIEW_AGENTROUTER_WAF_KILO_2026-09-23.md`).
> Live: `/v1/models` 200 (разблокирован); крошечный чат → 402 «Budget pool quota exhausted» (окно батча
> закрыто, не бан; скрипт не ретраил). **Регламент:** редкие one-shot; не параллелить плагин/скрипты; при
> 403/405 — пауза часы; батч-окна Claude/GPT 11:00/23:00 UTC; плагин вступит в силу после рестарта opencode.
> **Тяжёлое ре-ревью Opus-5.5 (Abacus `claude-opus-5-5-thinking`, по предложению юзера; ≈$0.84 / 2 прогона):**
> готовность к монетизации на срезе 23.09 — `EXPERT_REVIEW_HEAVY_OPUS55_2026-09-23.md` (+адъюдикация, все
> ключевые пункты проверены фактами). **Вердикт: платный Supporter — NO-GO сохраняется** (P0-1 #15, P0-4
> оферта-плейсхолдеры, P0-5 МНС; + 3.3 возврат/3.5 донат-перк/3.8 ранний доступ); **донаты — условный GO**
> после Boosty/KYC/карты и формата «без перков». Подтверждено: P0-2 закрыт; P0-3 частично (Сбер без оговорки
> в meta/OG/hero/EN); P1-9 закрыт; P1-7/8/10 частично. Новые находки: живой `FUNDING.yml →
> boosty.to/REPLACE_ME` (кнопка Sponsor; риск захвата ника — [сверить]), LLM-карточка занижает утечку
> (few-shot + псевдоним счёта), og/hero «данные не покидают» безусловно, EN-README без оговорки, донат-перк
> «заметки» = фактически подписка, mailto уже собирает e-mail, BP §7/§9 (РФ-НПД «~15–17%» vs BY «20–22%»)
> + «466+25» устарело, внутренние хвосты «разовая лицензия»/managed-прокси. Предложен один S-коммит
> «гигиена-2» (публичные тексты + BP + хвосты) — по команде юзера; юр-правки оферты/МНС и #15 — за юзером.
> Урок: для тяжёлых ревью `--max-tokens` ≥20–24K (прогон 1 обрезан на 12K → доп. прогон ≈ удвоил цену).
> **«Гигиена-2» по ревью Opus-5.5 (по команде юзера) — сделана, ждёт коммита.** Публичные тексты:
> `FUNDING.yml` (custom закомментирован, кнопка Sponsor выключена), Boosty-кнопка выключена (disabled +
> «к запуску») в landing/README, донат-перк «заметки» убран («чистый донат»), Сбер-оговорка в meta/OG/hero/EN,
> LLM-карточка и FAQ раскрывают состав данных (псевдоним счёта + few-shot) и «по умолчанию» вместо
> безусловного «данные не покидают», EN-README без «via Boosty», «ранний доступ» смягчён, README FAQ —
> «публичный issue». Плановые доки: BP §7/§9 (BY-цифры ≈20–22%, чистыми ≈$18.5–20, managed-прокси убран) и §15,
> оферта-статус, чек-лист 1.2/§6, payouts (хвосты «разовой лицензии»), PIPELINE/CONTEXT. Тесты лендинга
> обновлены (нет `REPLACE_ME`/`boosty.to`, «Boosty — к запуску», «псевдоним счёта», донат без перков).
> Контур: **482 unit** + ruff + contract + build_css + визуальный смоук лендинга (0 ошибок консоли).
> За юзером: §3.6 оферты, mailto (1.8), горизонт (1.5), вопросы в МНС, включить Boosty-кнопку после URL.
> **Дизайн-ревью Opus-5.5 (Abacus + 6 скриншотов; ≈$0.60; 253 с, 31 879 in / 23 846 out):** ресёрч
> primary sources → `RESEARCH_DESIGN_BRAND_SPENDTRACKER.md` (372 стр.) → досье (лендинг HTML+CSS + выжимка)
> → vision-probe → one-shot → `EXPERT_REVIEW_DESIGN_OPUS55_2026-09-23.md` (+адъюдикация; все P0 проверены
> расчётом/фактами). **Вердикт:** лендинг ~7/10, приложение ~5/10 («developer UI на дефолтах Tailwind»).
> P0: контрасты лендинга (white/#3b82f6 = 3.68:1; --faint 3.75:1), hero-CTA ведёт на якорь, «Перетащите CSV»
> vs textarea, расходы всё красные (сигнал обесценен), EN-слаги/CONF/«Яндекс.Деньги», disabled Boosty на
> проде, «ПРОВЕРКА CSP» в демо-данных скриншотов. **План:** волна S (7 пунктов: контрасты, hero/CTA-текст,
> support, демо-данные+кропы, синхронизация заявлений, микро-тексты, fetchpriority/lazy) + волна M
> (`tokens.css` 2 слоя + `@theme`; `fmt_money`/`fmt_month`/RU-названия категорий; цвет-семантика; /approve
> bulk-порог+клавиатура; /dashboard аномалии/темп; /transactions таблица выше форм + file input; nav/settings;
> порядок секций лендинга + финальный CTA). Имя не менять (проверка ФИПС/RuStore — вручную). Инструмент:
> `D:\dev\bootstrap\scripts\abacus_chat.py` (дублирует temp-версию + `--image`, usage-лог). Следующее:
> волна S — по команде юзера.
> **АКТУАЛЬНО (23.09, сессия «AgentRouter→opencode + Ollama Cloud» — dev-tooling; репо-код не менялся).**
> Deliverable: интеграция AgentRouter в opencode + пилот Opus-5 на окне квоты; бонусом — тест Ollama Cloud
> на важном ревью. ① **Плагин** `~/.config/opencode/plugins/agentrouter-ua.js` (авто-загрузка подтверждена):
> кодовый UA/x-app для agentrouter.org, подстраховка токена (env→реестр; `{env:...}` резолвится раньше
> плагина — проверено фактом «no token» → «402»), санитизация тела (`metadata`/`stream_options`/
> `reasoning_effort` — Bedrock-мост иначе даёт `metadata.session_id: Extra inputs are not permitted`),
> фильтр SSE (`data: null` роняет AI SDK). ② **Провайдер** `agentrouter` в opencode.json (3 модели,
> OpenAI-совместимый; models.dev добавляет 3 недоступные нашему токену — выбирать только свои).
> Оффлайн-тест плагина 12/12; `opencode run` доходит до Bedrock-моста, но WAF режет серию быстрых запросов
> (`405 Not Allowed`) → **next: cooldown/очередь в плагине** (как в npm-референсе). ③ **Пилот**: батч-окно
> 11:00 UTC поймано поллером (14:11), Anthropic-протокол, 250 с, 63 034 in / 14 326 out (8 863 thinking)
> ≈ **$0.27** → `EXPERT_REVIEW_HEAVY_AGENTROUTER_OPUS5_2026-09-23.md` (+raw, судья): 17 принято, 0 отклонено;
> новое: личный e-mail с коннотацией «1488» в публичном контакте (заменён на `exnihil88@gmail.com`,
> решение юзера 23.09), механика акцепта/идентификации покупателя,
> `FUNDING.yml` REPLACE_ME («битая кнопка Sponsor»); CSRF-находка модели реальна (закрыта нами 22.09
> независимо); adaptive thinking ест max_tokens (8K → текст обрезан; для ревью ≥16–24K).
> ④ **Ollama Cloud** (ключ заведён в User-env `OLLAMA_CLOUD_API_KEY`): free-usage 6 моделей
> (nemotron-3-ultra/super/nano, gpt-oss:120b/20b, gemma4:31b), `deepseek-v4-pro`/`kimi-k3`/`glm-5.3` — 402;
> важное ревью на nemotron-3-ultra ($0, 226 с) + судья gpt-oss:120b → `EXPERT_REVIEW_HEAVY_OLLAMA_NEMOTRON_2026-09-23.md`;
> ограничение: промпт режется на ~49K токенов (полное досье судье не подать). Инструменты:
> `free_llm_chat.py --provider ollama-cloud`, `ollama_cloud_probe.py`, `agentrouter_chat.py --protocol`.
> ⑤ Продукт не менялся: 482 unit + ruff + contract + build_css — зелёные (факт). Репо-изменение: только
> continue.md. ⑥ **AgentRouter: WAF забанил IP** после серии запросов (браузер тоже; пилот успел до бана) —
> канал для редких one-shot; не долбить (ждать/сменить IP). ⑦ **Чистка архивного e-mail из git-истории
> (вариант B, решение юзера):** закрыты 5 Dependabot-PR; `git-filter-repo` (mailmap + replace-text) —
> 130 коммитов и тег `v0.1.0` перезаписаны (новые SHA; автор `exnihil88@gmail.com`); защита main снята
> и возвращена 1:1; force-push — юзером; Pages передеплоен (живой сайт без старого адреса); свежий клон
> чист (0 вхождений). **Остаток:** старые коммиты (cadea35/c52ce82/961345a/279d969) ещё отдаются по SHA —
> их держат закрытые PR-refs (dereference — только через Support; тикет опционален). Бэкап-зеркало
> со старым адресом: `temp\opencode\spend-tracker-backup-2026-09-23.git` (удалить после решения).
> Следующее: cooldown/очередь в плагине (для агентных сессий); решения юзера по адъюдикации (акцепт,
> FUNDING.yml); прочее — по SESSION_START_PROMPT.
> **АКТУАЛЬНО (23.09, сессия «AgentRouter и бесплатные AI-роутеры» — docs/скрипты; репо-код не менялся).**
> Разобран пост Habr (6 бесплатных роутеров, https://habr.com/ru/articles/1070906/): AgentRouter ($125
> кредитов, Opus-5 $2/$10, Opus-4-8, gpt-6-astra), OrcaRouter/TeamoRouter (free DeepSeek), Token Harbor
> (7-дневное окно, запросы сохраняются), NaraRouter (7 млн токенов/день + Telegram), FreeRouter (qwen3.8-max).
> **Проба ключа AgentRouter (23.09):** WAF принимает только «кодовые» клиенты — с `claude-cli`/`QwenCode` UA
> `/v1/models` = 200, с дефолтным = 401; аккаунт видит 3 модели; **любая генерация → 402 «Budget pool quota
> has been exhausted»** (пул/Unlimited quota — настройка консоли; блокер на стороне аккаунта).
> `co.agentrouter.org` — другой сервис (ключ там 401). Протоколы: Claude → `/v1/messages` (x-api-key, base без
> `/v1`), GPT → `/v1/chat/completions`. Инструменты (bootstrap): `agentrouter_probe.py`, `agentrouter_chat.py`
> (one-shot ревью, оба протокола, кодовый UA, ретраи, лог `agentrouter_usage.jsonl` без ключа); ключ —
> User-env `AGENTROUTER_API_KEY`. Артефакт: `RESEARCH_AGENTROUTER_FREE_ROUTERS.md` (экономика: $125 ≈
> 700–900 наших ревью vs Abacus ≈ $0.35–0.55/ревью и 20K кредитов/мес). **Действие юзера:** в консоли
> agentrouter.org включить Unlimited quota/выбрать пул с балансом (+check-in, перелогин) — после этого пилот
> Opus-5 vs Abacus и opencode-интеграция (провайдер + наш локальный fetch-плагин с UA-инъекцией, рестарт).
> В продуктовый `llm.py` ключ не заводим (dev-tooling).
> **АКТУАЛЬНО (23.09, сессия «оптимизация+безопасность, фаза 2» — закоммичено `961345a`, запушено).**
> ① **Chart.js только на дашборде:** из `base.html` убран глобальный `chart.umd.min.js` (205 КБ);
> `base.html` получил блок `{% block scripts %}`; `dashboard.html` подключает `dashboard.js`, который
> динамически загружает Chart (URL — из `data-chart-src`, с версией) и рисует графики; e2e
> `test_chart_js_loads_only_on_dashboard` (на `/` ресурса нет, на дашборде — есть и Chart.getChart != null).
> ② **Версия статики + Cache-Control:** `assets.static_url()` → `/static/<файл>?v=<sha8>` (Jinja-хелпер
> `static` в трёх роутерах), middleware: `immutable` для `?v=`, `no-cache` без версии, `no-store` для HTML/API;
> тесты `tests/test_static_cache.py` (4) + обновлённые static-тесты. Контур: unit **481 (+4)**, e2e **45 (+1)**,
> cross-engine **40**, ruff, contract ok (baseline аддитивно: `static_url`), `build_css --check` ok.
> Live (NSSM рестартнут): HTML отдаёт версии (`app.css?v=30be5b6c`, `app.js?v=4a0fef40`), `/` без chart.umd,
> дашборд грузит `chart.umd.min.js?v=…` и рисует (консоль 0 ошибок), заголовки кэша корректны.
> Фазы 1–2 оптимизации/безопасности закрыты. Осталось по сигналу: строгий `style-src` (nonce), mmap_size
> (по замеру), стриминг экспорта (>100k строк), CORS/прокси (remote-доступ), BitLocker (за юзером).
> **АКТУАЛЬНО (22.09, сессия «оптимизация+безопасность, фаза 1» — закоммичено `c52ce82`, запушено).**
> ① **Периметр:** `src/spendtrack/security.py` (`origin_allowed`) + middleware в main.py: POST/PUT/PATCH/DELETE
> с чужим `Origin`/`Sec-Fetch-Site` → 403; без заголовков (CLI/тесты) — пропуск; `TrustedHostMiddleware`
> (127.0.0.1/localhost/testserver) → 400 на чужой Host; тесты `tests/test_security_perimeter.py` (7);
> live: evil-origin POST=403, same-origin POST=422 (валидация), чужой Host=400. ② **Lifecycle SQLite:**
> `deps.get_store()` — dependency с `yield` (close гарантирован + `PRAGMA optimize`), `cache_size=-8000`,
> `temp_store=MEMORY`, `check_same_thread=False`; все 29 роутов переведены на
> `store: Annotated[Store, Depends(get_store)]`; bench без регресса (месячные агрегаты 4.7→0.8 мс,
> `/dashboard` 50K 388→344 мс, импорт в шуме). ③ **Строгий CSP `script-src 'self'`:** `/static/app.js`
> (тост + обработчики форм), `/static/dashboard.js` (графики; данные — `#dashboard-data` data-атрибутами),
> `htmx.config.allowEval=false`, `hx-on::*` удалены; e2e-тест `test_add_form_works_under_strict_csp` +
> живой смоук демо-стенда (форма/сброс/счётчик/графики, консоль 0 ошибок). ④ **Supply chain (A03:2025):**
> `pip-audit` dev-зависимостью + шаг CI («No known vulnerabilities»), `uv lock --check`, Dependabot
> (pip+github-actions), все actions пиннуты по commit SHA, `permissions: contents: read`.
> Контур: unit **476 (+5)**, e2e **44 (+1)**, cross-engine **38**, ruff, contract ok (baseline осознанно:
> +2 функции `origin_allowed`/`get_store` и dependency в сигнатурах роутов), `build_css --check` ok.
> Прод NSSM рестартнут (8 tx — не тронуты), демо-стенд 8767 проверен и остановлен.
> Доки: SECURITY (периметр/CSP/lifecycle/supply chain/BitLocker-чек), PIPELINE (раздел «Периметр, lifecycle
> и supply chain»), CONTEXT (термины), README (команды). **Факт для юзера:** BitLocker на C:/D: выключен —
> включить том + ACL на `data/`; offsite-копия — plaintext, при выносе шифровать.
> **Осталось (фаза 2, S):** Chart.js только на дашборде (Jinja-блок) + версия/Cache-Control статики.
> **АКТУАЛЬНО (22.09, сессия «ресёрч оптимизации/безопасности» — docs вне репо; войдёт в коммит фазы 1).**
> Два research-файла (первоисточники): `RESEARCH_SECURITY_SPENDTRACKER.md` (26 источников: для no-auth
> localhost классический CSRF неприменим, но кросс-сайтовые state-changing POST — да → «золотой минимум»
> Origin/Sec-Fetch + TrustedHost (токены избыточны, PNA — draft, полагаться нельзя); ASVS 5.0 L1: единственный
> gap — `unsafe-eval` для htmx `hx-on`; A03:2025 supply chain; uvicorn access-log пишет query, но у нас
> подавлен; BitLocker покрывает WAL/shm; SQLCipher — вне модели) и `RESEARCH_OPTIMIZATION_SPENDTRACKER.md`
> (19: `PRAGMA optimize` перед close; per-request соединение через dependency yield; StaticFiles без
> Cache-Control; workers=1; Chart.js по страницам; измерение без APM; анти-over-engineering).
> Тяжёлый синтез opus-5 (138 с, ≈$0.35): «база выше среднего; две реальные дыры — периметр браузера и
> supply chain». План P0: Origin/TrustedHost; per-request store + `PRAGMA optimize`/cache_size/temp_store;
> pip-audit + Dependabot + SHA-pin + `permissions: read` + `uv lock --check`. P1: Chart.js только на дашборде;
> Cache-Control+версия статики; **строгий `script-src`** (наш аудит: всего 2 `hx-on::*` + 1 inline-скрипт →
> перенос в `/static/app.js`, `allowEval=false` — S/M вместо «отложить»); доки (SECURITY/PRIVACY/PIPELINE).
> Адъюдикация 14 пунктов: принято 10, скорректирован 1 (strict script-src), уточнено фактом 1 (access-логи
> уже подавлены: 0 записей), отклонено 2 (XXE — XLSX-импорта ещё нет; 500-трейсбеки — debug выключен).
> **Факт для юзера:** BitLocker на C:/D: выключен (`ProtectionStatus=Off`) — шифрование тома + ACL на `data/`
> в чек-лист; offsite-копия — plaintext, если покидает машину, шифровать архив.
> Артефакты: `EXPERT_ANALYSIS_OPTSEC_OPUS5.md` (+raw). **Следующий deliverable: «оптимизация+безопасность,
> фаза 1» (M)** — Origin/TrustedHost + strict script-src + supply chain CI + store-lifecycle/PRAGMA
> (bench до/после); фаза 2 (S) — фронт-гигиена и доки.
> **АКТУАЛЬНО (22.09, сессия «кроссбраузерность-пасс, фаза 2» — закоммичено `999812e`).**
> Добита фаза 2: ① **контрасты** (axe serious → 0): muted-текст `slate-500→400` по шаблонам, кнопки
> `emerald-600→700` (3), «Одобрить все» `amber-600→700`, пустой бюджет `slate-600→400`; disabled-состояния
> оставлены тёмными (WCAG 1.4.3 исключает inactive-компоненты); ② **ссылки в тексте** — `p a, li a`
> подчёркнуты (1.4.1); ③ **date-хинт** «ГГГГ-ММ-ДД» с `aria-describedby` (Safari без календаря);
> ④ **кнопка «Показать ещё»** у sentinel догрузки (`hx-trigger="revealed, click"`; в UI дремлет — страница =
> месяц, активируется в многомесячном режиме; роут-тест обновлён regex-проверкой); ⑤ **CSP + nosniff +
> Referrer-Policy** (middleware `_security_headers`; `unsafe-inline/eval` осознанно — htmx `hx-on` через
> `new Function`, факт grep; документировано в `SECURITY.md`); ⑥ axe-гейт в e2e усилен до **critical+serious=0**,
> сид смоука включает pending-строки (нашлись и закрыты `select-name` в review-строках и контраст кнопки).
> Контур: unit **471 (+2 security-headers)**, e2e chromium **43**, cross-engine **36**, ruff, contract ok,
> `build_css --check` ok; live: CSP/nosniff/referrer на `/`, API и статике, все страницы 200, консоль
> playwright 0 ошибок, хинт рендерится. Ревью $0 (157 с): NO-GO → принят 1 P1 (устойчивый regex-ассерт),
> **8 пунктов отклонены фактами** (htmx eval — проверено; русский UI — роадмап i18n; disabled — WCAG-исключение;
> CSP-поломки ловит консольный смоук; app.css — билд-артефакт v4; кнопка в `<td>` валидна; даты сида—
> детерминированы от MAX(date)) — `EXPERT_REVIEW_CROSSBROWSER_F2_OR.md`.
> Осталось (фаза 3, при hosted): строгий CSP (nonce/hash, вынос hx-on в `/static/app.js`); компонентные
> классы при росте повторений; реальный Safari/iOS — best effort.
> **АКТУАЛЬНО (21.09, сессия «кроссбраузерность-пасс, фаза 1» — закоммичено `763ad0a`, запушено).**
> По плану research+opus-5 закрыты все 3 «мягких блокера»: ① **prebuilt CSS** вместо browser build — вход
> `src/spendtrack/tailwind.css`, выход `static/app.css` (~25 КБ); сборка `scripts/build_css.py` (официальный
> standalone CLI Tailwind v4.3.3, **без Node**; sha256 всех платформ-ассетов из GitHub API; кэш в
> `%LOCALAPPDATA%/spendtrack/tailwindcss`, env `SPENDTRACK_TAILWINDCSS_DIR`; `--check` в CI-lint);
> `static/tailwind.js` (282 КБ, dev-only) удалён; ② **кросс-движковый смоук**
> `tests/e2e/test_crossbrowser_smoke.py` (18: рендер/консоль 5 страниц, отсутствие h-скролла на 320 старт+resize,
> axe critical=0, фокус скролл-области) + CI-джоб `cross-browser-smoke` (firefox+webkit; полный e2e — chromium);
> ③ **a11y/reflow**: 17 aria-label (axe label/select-name criticals), `.table-scroll`
> (role=region/tabindex/sticky thead/edge-тени/focus-visible), nav `flex-wrap`; попутно найден и закрыт
> **реальный баг**: карточки графиков не сжимались при сужении окна (`min-w-0`) — на живом стенде было
> +180px overflow (регресс-тест `test_no_horizontal_scroll_after_resize`, красный до фикса).
> Контур: unit **469**, e2e chromium **43**, cross-engine (FF+WebKit) **36**, ruff, contract ok;
> live-смоук: `/static/app.css` 200, скриншот 1280 — стили на месте, 320 после resize = 0. Ревью $0
> (nemotron-ultra:free, 155 с): NO-GO → **все 2 P0 и 4 P1 приняты и закрыты** (кросс-путь CLI, хэши всех
> платформ, детерминированный wait, seed через Store, семантические ассерты CSS, ретраи/UA, тест фокуса) —
> `EXPERT_REVIEW_CROSSBROWSER_F1_OR.md`. Новая dev-зависимость: `axe-playwright-python` (axe оффлайн).
> **Фаза 2 (по плану opus-5):** axe-serious (контрасты `text-slate-500`/emerald-кнопок/link-in-text-block),
> date-хинт для Safari, кнопка «Загрузить ещё», CSP после prebuild.
> **АКТУАЛЬНО (21.09, сессия «ресёрч адаптивности/кроссбраузерности» — закоммичено `4aa8d74`).**
> ① Два research-файла (фоновые агенты, первоисточники, метки verified/secondary): `RESEARCH_ADAPTIVITY_MATRIX.md`
> (порог Tailwind v4 = Chrome 111+/Safari 16.4+/Firefox 128+; РФ/BY авг-2026 — Chromium ~80% десктопа
> (Chrome+Yandex+Opera+Edge); Safari desktop без календаря у `<input type=date>` (WebKit #119175); Clipboard
> только secure context; `-webkit-calendar-picker-indicator` не чтится с FF109; StatCounter desktop/mobile:
> РФ 75/25, BY 81/19) и `RESEARCH_CROSSBROWSER_TESTING.md` (Playwright 3 движка на Windows, CI публичных репо
> бесплатен; WebKit≠Safari; iOS без Mac недостижим; YandexDriver; WCAG 1.4.10 reflow 320px / 1.4.4 200% /
> 2.5.8 24px; overflow-паттерн таблиц + sticky шапка, карточки не нужны). ② Тяжёлый синтез opus-5
> (2 прогона, ≈$0.5): «запускать можно, 3 мягких блокера» — Tailwind v4 browser build в проде (dev-only:
> без JS нет стилей, FOUC, 282 КБ, CSP), reflow 320px/zoom (нав без wrap; таблицы уже `overflow-x-auto`,
> но нет фокуса/sticky/индикатора), CI только Chromium. Адъюдикация: принято 9, отклонено 2 фактами
> (кнопки ↑↓ 28×28 ≥24 — 2.5.8 ок; clipboard в приложении не используется), исправлена research-ошибка
> (Yandex «10+»). Артефакты: `EXPERT_ANALYSIS_ADAPTIVITY_OPUS5.md` (+raw ×2). ③ Следующий deliverable-кандидат:
> **«кроссбраузерность-пасс, фаза 1» (S–M)** — prebuilt CSS через Tailwind standalone CLI (без Node),
> projects firefox/webkit в CI + assert 320px no-h-scroll + axe, nav wrap + a11y-обёртки таблиц
> (role=region/tabindex/sticky/edge-индикатор), README-матрица поддержки + known-issues.
> **АКТУАЛЬНО (21.09, сессия «инструменты #15 + одностраничник МНС» — закоммичено `a6dd830`).**
> ① `SCENARIO_10MIN_OBSERVER_CARD.md` — карточка наблюдателя: preflight 5 мин, хронометраж t0–t6 с критериями,
> правила фиксации (застрял >60 с, дословные цитаты, обезличивание образцов), «чего не делать»;
> ② `SCENARIO_10MIN_RESULTS.md` — шаблон результатов: 3 таблицы прогонов, сводка с легендой успеха
> (t6 ≤ 600 с И установка без помощи), решение по протоколу, реестр образцов (вход в #4) и багов;
> ③ `MNS_SUPPORTER_PACKAGE_DESCRIPTION.md` — одностраничник-приложение к запросу в МНС (услуги: поддержка/
> приоритет/ранний доступ/список; AGPLv3-права сохраняются; Boosty 11.7% и нетто-поступление; статус и горизонт;
> фаза B оговорена «на момент подачи»); протокол и письмо синхронизированы. Ревью $0 (nemotron-ultra:free, 81 с):
> 5 P0/6 P1 — принято 9, отклонено 3 фактами (№457 проверен по первоисточнику 21.09; пороги t1–t5 необоснованны;
> плейсхолдер Boosty явный) — `EXPERT_REVIEW_PREP_15_MNS_OR.md`. Репо-код не менялся.
> **Осталось за вами:** провести 3 прогона по карточке → заполнить RESULTS; отправить запрос в МНС с одностраничником;
> собрать образцы выписок (Сбер-XLS) → после образца сессия #4.
> **АКТУАЛЬНО (21.09, сессия «гигиена репо» после тяжёлого ревью — закоммичено `31380d0`, запушено).**
> Решения юзера (все рекомендованные): фрейм «спонсорство» + юр-природа «услуги»; честная оговорка Сбера;
> убрать managed-LLM-прокси и «разовую лицензию». Правки: `landing/index.html` (карточка «разовая поддержка»:
> имя в списке/анонимно, приоритет внимания к issue, ранний доступ; Sber-оговорка в fact и FAQ; lead),
> `README.md` (импорт-строка с оговоркой, §Лицензия и поддержка, EN-блок), `.github/ISSUE_TEMPLATE/supporter.yml`,
> `PRIVACY.md` («issue публичный» у `doctor --share`), `SECURITY.md` (11→13 проверок), `spec/ARCHITECTURE.md`
> (убран дрейф чисел), `spec/PIPELINE.md` (заметка о фрейме), `BUSINESS_PLAN_SPENDTRACKER.md` (машина: 466+25,
> §7 — новый состав); мёртвый код: `llm.get_client`, `Store.MerchantCacheEntry`, отступ `categorize_rules_only`.
> Контур: **467 unit (+1)**, ruff чист, contract ok (baseline: удаление мёртвого `get_client` — осознанно);
> новый тест `test_no_misleading_supporter_claims` держит landing+README+supporter.yml. Live: NSSM рестартнут
> (`/`, `/help`, `/health`, `/health/data` 13/13), лендинг на http.server — 200 и новые тексты (сервер остановлен).
> Ревью $0 (nemotron-ultra:free, 52 с): **GO** — P0 про CHANGELOG отклонён (не ведётся с v0.1.0, релизов нет),
> принят тест-гэп (README/supporter.yml) — `EXPERT_REVIEW_HYGIENE_OR.md`. Закоммичено `31380d0`, запушено.
> **Осталось по плану:** #15 «10-мин сценарий» (процесс автора), #4 Сбер-XLS (data-gated — образец из #15),
> монетизационные решения §1 чек-листа (юр-форма/реквизиты/горизонт поддержки/анонимность списка/mailto/Boosty URL).
> **АКТУАЛЬНО (21.09, сессия «тяжёлое ревью» — Abacus claude-opus-5, one-shot ≈$0.55; P1 #6 до неё закоммичен `b472274`).**
> Промежуточное ревью всего продукта перед монетизацией (по протоколу: разведка канала → досье 45K ток. →
> 1 запрос 114 с, 78.8K in / 6.3K out → адъюдикация). **Вердикт: NO-GO на платный запуск сейчас**; донаты —
> после фикса P0-текстов; платный Supporter — после #15 и юр-гейта МНС. Принято 12 пунктов, отклонён 1 фактом
> (`_env_key_for` — внутренний `endpoint_override`, один тест; `get_client` без вызовов). Ключевое:
> ① **#15 первым** (нулевая внешняя валидация, прод 8 tx); ② публичные мисрепрезентации — managed-LLM-прокси,
> «разовая лицензия», «CSV Сбера» (у физлиц CSV нет — по нашему же ресёрчу; landing:55/README:17); ③ доккрифт,
> проверено: `SECURITY.md:22` «11 проверок», `spec/ARCHITECTURE.md:69` «79+10», `BUSINESS_PLAN:70` «354+21»
> при факте 466+25/13; ④ поддержка «≤5 р.д.» без горизонта + ПДн публичного списка + «публично» в `doctor --share`
> + возврат «14 дней безусловно»; ⑤ рекомендации — фрейм «спонсорство» вместо «пакета», первичный оффер —
> Сбер-XLS, НПД включать только в активные месяцы. Артефакт: `EXPERT_REVIEW_HEAVY_OPUS5_2026-09-21.md` (+raw);
> лог расхода — `abacus_usage.jsonl`. **Предлагаемый следующий deliverable — «гигиена репо» (S, агент, без кнопки
> оплаты):** правки публичных текстов (прокси/лицензия/Сбер), синхронизация цифр, «публично» в share-выводе,
> мёртвый код (`MerchantCacheEntry`, `get_client`, отступ `categorize_rules_only`) — нужны 2–3 микродесижена
> юзера (фрейм «спонсорство», убрать прокси, формулировка Сбера). #15 — процесс автора; #4 — data-gated (образец).
> **АКТУАЛЬНО (21.09, сессия P1 #6 «Doctor P2» — закоммичено `b472274`, push — по команде).**
> По POLISH_PLAN P1 #6 (S, P2-ценность): ① `doctor.check_examples_dupes` — дубли `examples` по
> (description, amount, category), **info**, count = «лишние» строки; ② `doctor.check_merchant_cache_dead` —
> записи кэша, чей мерчант не встречается в транзакциях (**info**); сверка через Python `.upper()`,
> потому что SQLite `UPPER()` не берёт кириллицу — вариант на SQL давал ложные «мёртвые» для русских
> мерчантов (пойман тестом). Оба чека в `run_checks` (теперь **13**), PIPELINE обновлён.
> Контур: **466 unit (+5)**, ruff чист, contract ok (baseline аддитивно: +2 функции). Live:
> `spendtrack doctor` = OK 13/13; NSSM рестартнут, `/health/data` = ok (13 чеков). Ревью $0
> (nemotron-ultra:free, 169 с): **GO**; единственный P1 (NULL/пустой merchant) отклонён фактом
> (NOT NULL-схема; пустая строка действительно мёртвая) и закреплён тестом —
> `EXPERT_REVIEW_DOCTOR_P2_6_OR.md` (+raw). Коммит/push — по явной команде юзера. Дальше:
> #15 «10-мин сценарий» (процесс автора) / #4 Сбер-XLS (data-gated) / монетизация — по решению юзера.
> **АКТУАЛЬНО (21.09, сессия perf-pass — замеры «до/после»; закоммичено `2dc5ddb`, запушено).**
> Deliverable: бенч-инструмент + точечные оптимизации по фактам (монетизация — пауза по решению юзера).
> ① `scripts/bench.py` — синтетика 36 мес в temp-БД (seed), median×3, HTTP через TestClient, JSON
> `reports/bench.json` (+ `bench_after.json`); артефакт — `D:\dev\docs\machine\PERF_BENCH_SPENDTRACKER.md`.
> ② Факты 50K строк (до → после): `/dashboard` 2.75 с → 388 мс, `/` 521 → 73 мс, очередь 245 → 2 мс,
> месячные агрегаты ≈93 → 5 мс, `build_digest` 1.17 с → 365 мс, импорт 5K строк 1.67 с → 0.40 с
> (3.0K → 12.5K строк/с). ③ Причины/правки: `substr(date,1,7)` → `month_bounds()`-диапазон (индекс);
> partial-индекс `idx_tx_pending` (создаётся после миграций — колонка из v2); O(1)-медиана кластеров
> в `detect_recurring`; один `detect_recurring` на `/dashboard` (`subscriptions=`); `has_transactions()`
> (EXISTS) для флагов страниц; `add_transaction(commit=False)` в `import_csv` — одна транзакция на партию
> (+ `rollback` при сбое). ④ Ревью $0 (nemotron-ultra:free, 377 с): NO-GO → все 2 P0 и 3 P1 приняты и
> закрыты (`EXPERT_REVIEW_PERF_OR.md` + raw; отклонено: глобальные assert'ы на чтениях, валидация month).
> ⑤ Контур: **461 unit (+10)**, ruff чист, contract ok (baseline осознанно аддитивный: `month_bounds`,
> `has_transactions`, 3 опц. параметра); perf-смок `test_digest_20k_synthetic` (20K, порог 2 с; длительности
> в `reports/perf.json`). ⑥ Live: NSSM рестартнут (дважды), `/`, `/dashboard`, `/approve`, `/health*` 200,
> playwright — 0 ошибок консоли; прод-БД получила `idx_tx_pending`. Commit/push — по явной команде юзера.
> Дальше по плану: #15 «10-мин сценарий» (процесс) / P1 #6 / #4 (data-gated).
> **АКТУАЛЬНО (21.09, сессия монетизации, фаза 1 — ЧЕРНОВИКИ; вне репо, ждёт решений юзера).**
> Deliverable: три документа в `D:\dev\docs\machine\`: ① `MONETIZATION_SUPPORTER_OFFER_DRAFT.md` — оферта/
> состав/прайс ($25 / 1900 ₽; юр-рамка «услуги, не лицензия»; AGPLv3-совместимость; возврат 14 дней);
> ② `MONETIZATION_PAYOUTS_BY.md` — Boosty → карта USD/EUR (11.7% + вывод + FX; мин $10), НПД-runbook
> (10%, минимум 45 BYN/мес, чек/22-е/снятие в простое), юнит-экономика (Boosty ≈ $18.5–20 чистыми,
> эффективно 20–23%; эквайринг 12–14%), фаза B (WebPay/bePaid, DonationAlerts); ③ `MONETIZATION_CHECKLIST_AUTHOR.md` —
> решения (10), шаги Boosty/KYC/карта, шаблон письменного запроса в МНС (классификация п.16/63, включая
> передачу бета-сборок), фаза B, точные правки репо (3 ссылки + PIPELINE/CONTEXT — по команде), публикация
> оферты как `landing/offer.html`.
> **Ревью $0:** `EXPERT_REVIEW_MONETIZATION_F1_OR.md` (+ `_raw`; nemotron-ultra-550b:free, 269 с, cost 0):
> 11 P0 / 13 P1 / 7 P2 — принято 26, отклонено 3 (эквайринг «самозанятый» — в ресёрче `[verified]`;
> дубль managed-прокси; «нет CONTEXT/PIPELINE» — есть в таблице), 2 частично; правки внесены в тот же день.
> Ключевые из адъюдикации: акцепт = подтверждённая оплата Boosty; возврат — фактически полученная сумма;
> `mailto:` → убрать до запуска (99-З); бета-сборки явно в запросе МНС; гейт «не публиковать до ответа МНС
> или решения на риске»; managed-LLM-прокси убрать из лендинга/README до реализации.
> Репо не менялся (только continue.md); тесты/live не применимы (Python/UI не трогались). Следующее:
> решения юзера (§1 чек-листа) → Boosty URL → правки заглушек по явной команде; альтернатива — #15.
> **✅ СДЕЛАНО (21.09, сессия P2 #11 — Wilson-CI калибровки; закоммичено `08a6457`+`0f851cd`).**
> Предыдущий #10 закоммичен (`5819365` feat + `23ed57f` docs) — push ждёт команды.
> ① `reports.wilson_interval()` — 95% интервал Wilson (табличные значения в тестах; n=0 → (0,1));
> ② у каждого кандидатного порога в `confidence_calibration` — `wrong_high` (верхняя граница доли ошибок);
> ③ `recommendation`: минимальный порог с ошибками ≤10% (95% уверенность) при ≥20 принятых; статусы
> ok/low_data/no_candidate; ④ CLI `confidence` печатает верхние границы + строку рекомендации.
> **Контур: 451 unit (+4: Wilson-значения+guard-и, параметры рекомендации, рекомендация ok/no_candidate;
> low_data — в существующем тесте), ruff, contract ok** (baseline snapshot: +1 функция `wilson_interval`,
> +2 дефолтных параметра). Live CLI на прод-БД: решённых 2/20 → «набрано меньше 20 принятых решений» —
> data-gated норма (порог меняем, когда решённых ≥20). UI не менялся (e2e/смоук не требовались).
> Ревью $0: GO; приняты guard-и (`ValueError` на невалидные счётчики) и параметры `target_error/min_sample`;
> TypedDict отклонён (аннотация уже есть, конвенция — dict) — `EXPERT_REVIEW_WILSON_11_OR.md`.
> Следующая по плану — **P3 #15 «10-минутный сценарий»** (процесс, 3 внешних) / монетизационные документы.
> **✅ СДЕЛАНО (21.09, сессия P2 #10 — чек-лист первого запуска; закоммичено `5819365`+`23ed57f`, push ждёт команды).**
> ① Главная при `first_run` (нет транзакций И нет партий импорта) показывает `#start-checklist`
> (`partials/start_checklist.html`): 4 шага со ссылками #import/#add, /approve, /settings, /dashboard
> + `/help#quick-start`; состояние серверное (без localStorage), после первых данных чек-лист исчезает
> (скрытие после импорта — надмножество требования: не навязываем активному пользователю).
> ② `Store.batch_count()` (read-only; contract snapshot аддитивно +1 сигнатура). ③ Попутно e2e-`clean_db`
> чистит `import_batches` — состояние партий текло между session-scoped e2e-тестами (нашёл новый тест).
> **Контур: 447 unit (+3) + 25 e2e (+1), ruff, contract ok.** Live-смоук (playwright MCP, свежая temp-БД 8799):
> чек-лист виден (4 li), после `spendtrack add` — исчез, консоль 0 ошибок; стенд убит, прод 8766 не трогали
> (Python менялся: `batch_count` — но прод-страницы чек-лист не используют на данных; рестарт не требуется
> до коммита — при коммите рестартнуть). Ревью $0: NO-GO → адъюдикация (оба P0 и P1 «таблица отсутствует» —
> ложные по фактам: client и Store делят env-БД, SCHEMA создаёт `import_batches` в `__init__`; принят P1 —
> `counts()` теперь один вызов на страницу) — `EXPERT_REVIEW_FIRST_RUN_10_OR.md`.
> Следующая по плану — **#11 Wilson-CI калибровки** (S, data-gated) / P2 #10–#11 закрыты, дальше монетизация.
> **✅ СДЕЛАНО (21.09, сессия P1 #5 — мультивалютность; закоммичено `a2e0edc`+`a37ad80`, push ждёт команды).**
> ① **Схема v5**: `transactions.currency TEXT NOT NULL DEFAULT 'RUB'` (аддитивно; старые строки = RUB),
> `SCHEMA_VERSION=5`; ② **fingerprint**: код валюты входит в отпечаток только для не-RUB — рублёвые отпечатки
> не изменились (реэкспорт = no-op), равные суммы в разных валютах не склеиваются дедупом;
> ③ **не-RUB не в ₽-агрегациях**: отчёты, бюджеты, дайджест, рекурринги, дневные итоги списка — курсы не смешиваются;
> ④ **импорт** читает валютные колонки (Sber «Валюта операции», Tinkoff «Валюта», Yandex «currency»); нет
> колонки/незнакомое значение → RUB; **API/CLI строгие**: `spendtrack add --currency USD`, `POST /api/transactions`
> c `currency` → 422 на мусор (без молчаливой подмены); ⑤ **UI/экспорт**: код валюты рядом с суммой в списке
> и очереди (RUB — как раньше), колонка «Валюта» в CSV/XLSX, FAQ `/help` обновлён; попутно фикс 500→422
> на кастомном pydantic-валидаторе (`ctx` с ValueError не сериализовался).
> **Контур: 444 unit (+15 `tests/test_currency.py`; `test_export.py` — новые индексы колонок) + 24 e2e, ruff,
> contract ok** (baseline snapshot — осознанно аддитивно: колонка + user_version 4→5 + функция + 2 дефолтных
> параметра). Live: демо-стенд 8767 с новым кодом — «−5.00 USD» в списке, FAQ, консоль 0 ошибок; **прод NSSM
> рестартнут: миграция v5 на реальной БД (user_version=5), doctor 11/11 OK, `/health` 200 (8 tx)**.
> Ревью $0: NO-GO → адъюдикация (P0 NULL-бэкфилл отклонён фактом + страховочный UPDATE принят; ctx-isinstance
> принят; BASE_CURRENCY отклонена) — `EXPERT_REVIEW_CURRENCY_5_OR.md`.
> Следующая по плану — **#15 «10-минутный сценарий» с 3 внешними** (процесс) / P2 #10–#11 / затем монетизация.
> **✅ СДЕЛАНО (21.09, сессия P3 #14 — «Запуск как сервис»; закоммичено `e690da0`+`5b1d1eb`, push ждёт команды).**
> P3 #12–#13 уже закоммичены и запушены (`c350144` + `092603b`, origin/main = HEAD). #4 Сбер-XLS — по-прежнему
> data-gated (образца нет: проверил репо и `data/` — .xls/.xlsx отсутствуют), поэтому взят #14.
> ① **Шаблоны**: `deploy/spendtrack.service` (systemd --user: `ExecStart=%h/.local/bin/spendtrack serve`,
> `Restart=on-failure`, `WantedBy=default.target`) и `deploy/com.spendtrack.serve.plist` (launchd LaunchAgent:
> `/bin/sh -c 'exec "$HOME/.local/bin/spendtrack" serve'`, `RunAtLoad`+`KeepAlive`, логи `/tmp/spendtrack.*.log`).
> ② **README §«Работа в фоне (автозапуск)»**: Windows — Планировщик заданий (AtLogOn, без администратора) и
> NSSM (служба до входа; под LocalSystem пути данных/конфига передаются явно `SPENDTRACK_CONFIG_DIR`/
> `SPENDTRACK_DATA_DIR`); macOS — `launchctl bootstrap gui/$(id -u)`; Linux — `systemctl --user enable --now`
> (+ `loginctl enable-linger`); ключи LLM — в окружении сервиса, шаблоны секретов не содержат.
> ③ **Live-проверка на Windows** (сессия elevated; прод `spendtrack` 8766 не трогали): NSSM-служба
> `spendtrack-svc-check` (шим uv tool под LocalSystem, порт 8799, temp-данные/env) — `start` → `/health` 200
> (0 tx) → `restart` → 200 → `stop` (порт свободен) → `remove`; Планировщик AtLogOn `spendtrack-svc-check` —
> `Start` → `/health` 200 → `Stop`/`Unregister` (задача удалена, слушателя не осталось); прод `/health` 200 (8 tx).
> ④ **Доки**: PIPELINE §«Запуск как сервис (P3 #14)» (с фактами live), CONTEXT — термин «Сервис (автозапуск)»,
> README EN-блок. Тесты: `tests/test_deploy_templates.py` (4, оффлайн: структура юнита/plist через `plistlib`,
> отсутствие заглушек/секретов, README ссылается на шаблоны и все три ОС).
> **Контур: 429 unit (+4) + 24 e2e (не трогали — UI без изменений), ruff чист, contract ok** (Python-код не менялся).
> Ревью $0 — `EXPERT_REVIEW_SERVICE_14_OR.md`. Следующая по плану — **#15 «10-минутный сценарий» с 3 внешними**
> (процесс) либо **P1 #5 мультивалютность** (M, миграция v5).
> **✅ СДЕЛАНО (21.09, сессия P3 #12–#13 — offsite-бэкап + метрики-прокси; закоммичено `c350144`+`092603b`, запушено).**
> ① **#12 Offsite-бэкап**: `scripts/backup.py --copy-to <папка/USB> [--force]` — свежий VACUUM INTO-снимок
> копируется на другой том (guard `same_device` через `st_dev`; Windows — серийник тома), sha256-сверка
> (`spendtrack/checksum.py`), битая копия удаляется; маркер `data/backup/last_offsite_copy.json`
> (`time/source/dest/sha256/size`); ротация `--keep` внешнюю папку не трогает. Новый 11-й doctor-чек
> `offsite_backup`: нет маркера → info, файл не найден/старше 7 дней/битый маркер → warn, sha не совпал →
> critical. ② **#13 Метрики-прокси**: решение — авто-телеметрии/сервера НЕТ; `spendtrack doctor --share`
> локально печатает анонимную сводку (версии, ОС, режим repo/installed, режим LLM, счётчики tx/imported/
> партии/категории/правила/бюджеты/pending, бакет истории, наличие бэкапов) + prefilled GitHub-ссылку
> (ручной opt-in ping; ~1400 символов). Суммы/описания/мерчанты/счета/точные даты/пути/секреты исключены —
> канон `PRIVACY.md` §Метрики без телеметрии, тесты анонимности.
> **Тесты: 425 unit (+25) + 24 e2e** (ревью-P1: +2 теста ротации/пути), ruff, contract ok (baseline
> аддитивно +4 символа — осознанно; ревью $0: GO, P0 нет, 3 P1 приняты — см. адъюдикацию в артефакте).
> Live: `--copy-to` D:→C: (sha+маркер) → doctor OK 11/11 → артефакт теста убран (offsite = info);
> `doctor --share --json` проверен; NSSM рестартнут, `/health/data` 200 (11 чеков), `/help` 200 с новыми FAQ,
> playwright-смоук — 0 ошибок консоли. Ревью $0 — см. `EXPERT_REVIEW_P3_BACKUP_METRICS_OR.md`.
> Дальше по плану: **#4 Сбер-XLS (data-gated: нужен обезличенный образец)**, затем #14–#15, P1 #5 мультивалютность.
> **✅ СДЕЛАНО (21.09, сессия P1-импорт — POLISH_PLAN #1–#3; закоммичено, ждёт push).**
> ① **Дрейф формата** (`csv_import.py`): проверка обязательных колонок банка (`REQUIRED_COLUMNS`, синонимы,
> допуск пробелов/регистра) перед разбором; смена формата/неопознанный банк → `status="format_error"`
> (`missing_columns`/`found_columns` + `message` с просьбой прислать обезличенный образец), БД и партия
> импорта не трогаются (проверено live: после попытки /health=8 tx); `sniff_bank` узнаёт Сбера и по
> «Дата платежа»; неоднозначный набор колонок (подходит нескольким банкам) — не ошибка. ② **Отчёт импорта**
> «+N добавлено · S пропущено (причины) · K подозрительно (причины) · банк» — единый `summarize()` для CLI и UI;
> причины: duplicate/status/missing_fields/amount_unparsed/amount_limit, date_unrecognized (импортируется
> с пометкой); ключи `dupes`/`invalid` сохранены. CLI `import [--json]`; ③ **anonymizer**
> `scripts/anonymize.py` (PII → псевдонимы, формат сохраняется — образец валидная фикстура). ④ Попутно
> live-смоук вскрыл 500 на битой кодировке тела → `_json_payload` (400/422 вместо 500).
> **Тесты: 400 unit (+9 к P2) + 24 e2e**, ruff, contract ok (baseline +2 аддитивно). **Ревью $0: GO**
> (ultra-550b, 270 с; `EXPERT_REVIEW_IMPORT_P1_OR.md`) — принят fail-open при неоднозначных колонках,
> закрыты тест-гэпы (CLI --json, JSON-422/400, граница лимита, неоднозначные колонки).
> Следующая по плану — **P3 #12–#13** (offsite-бэкап, метрики-прокси), затем #4 Сбер-XLS (data-gated).
> **✅ СДЕЛАНО (21.09, сессия P2 UX-полировка — POLISH_PLAN #7–#9; закоммичено `bceac1b`+`fa149dc`+`79b0847`).**
> ① **#9 знаки сумм**: `fmt_amount_signed` (`store.py`) — `+`/`−` (U+2212), ноль «0.00»; применение в списке/очереди/
> дашборде/аномалиях дайджеста; `fmt_amount` (ASCII) не тронут (CSV/промпты/CLI). Попутно закрыт ложный «+259.00»
> у скачка цены (медианы — магнитуды, знак ставится явно) — найден визуальным смоуком, закрыт тестами.
> ② **#9 контраст**: `colors.py` — `badge_text_color` (адаптивный #020617/#ffffff, все 18 дефолтных цветов ≥4.5:1,
> счётчик очереди ≈10.4:1) + правки бейджей в 5 местах; тесты `test_colors.py`.
> ③ **#7 пустые состояния**: список (нет данных / фильтр / пустой месяц), очередь («Все подтверждены» + якорь
> `/help#faq-queue-why`, общий partial `review_empty.html` с OOB), дашборд (онбординг `#onboarding` при 0 tx,
> заметка на пустой месяц). ④ **#8 микро-подсказки**: импорт → `/help#faq-import-sber`, очередь → порог из конфига.
> **Тесты: 372 unit (+16) + 24 e2e (+3, файл `test_ui_polish_e2e.py`)**, ruff чист, contract ok (baseline snapshot
> аддитивно +5 символов — осознанно). Live: прод NSSM рестартнут, `/health`/`/health/data` ok; визуальный смоук
> стенда `127.0.0.1:8767` (demo.db, 350 tx) — знаки/подсказки/бейджи ок, консоль без ошибок. **Ревью $0**
> (OpenRouter :free, nemotron-ultra-550b, 136 с): **GO, P0/P1 нет**; принят P2.1 (общий partial пустой очереди),
> остальные P2 — осознанно оставлены (полная гарантия контраста для произвольного пользовательского цвета
> невозможна без правки его выбора; `has_any=True` в пагинации — намеренный фолбэк). **Stretch #10–#11 не взяты.**
> **СЛЕДУЮЩАЯ СЕССИЯ (по порядку плана): P1 #1–#3** — детектор дрейфа формата банка, отчёт импорта
> «добавлено/пропущено/подозрительно», anonymizer-скрипт (`POLISH_PLAN_SPENDTRACKER.md`). Дальше — P3 #12–#13
> (offsite-бэкап, метрики-прокси), #4 Сбер-XLS — data-gated, затем документы монетизации.
> Источник формулировок — `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (§4, §6). Монетизация — ПОСЛЕ доработки приложения.
> **АКТУАЛЬНО (21.09, доп.: анализ «монетизация, если автор из Беларуси»).** Два free-ресёрча
> (`RESEARCH_BELARUS_PAYMENTS.md` — каналы/санкции; `RESEARCH_BELARUS_TAX_LEGAL.md` — налоги/юр, всё по первоисточникам)
> → синтез `MONETIZATION_BELARUS_ANALYSIS.md` + раздел §15 в `BUSINESS_PLAN_SPENDTRACKER.md`.
> Главное: западные каналы закрыты для BY так же, как для РФ (GitHub Sponsors, Stripe/PayPal-приём, Payoneer, Wise,
> Patreon, Ko-fi, Gumroad, LS, Paddle, OSC); **Boosty работает** (вывод нерезидентам на карту USD/EUR, 11.7%);
> появляется дешёвый **BY-эквайринг** (WebPay от 1.5%, bePaid 2.4–3.5%) — шаг фазы B; BY-НПД **10%** +
> **минимум 45 BYN/мес** даже при нулевых продажах (риск при редких чеках $25; при простое — сниматься с учёта);
> главный юр-риск — классификация «разовой лицензии на ПО» под НПД (ОКЭД 58290 не в перечне; п. 16/63 спасают —
> нужен письменный ответ МНС); hosted по-прежнему нельзя (99-З/152-ФЗ включаются при сборе данных).
> Эффективная нагрузка: Boosty ≈ 20–22%, прямой эквайринг ≈ 12–14%. В репо изменён только continue.md;
> артефакты — в `D:\dev\docs\machine\`. Коммит — по команде юзера.
> **АКТУАЛЬНО (20.09, вечер-6, хвостовая сессия): ✅ хвосты закрыты (③ из плана; ждёт коммита/push).**
> ① **favicon-404 приложения закрыт:** `static/favicon.svg` + `<link rel="icon">` в base.html; live `/static/favicon.svg`
> 200 (`image/svg+xml`), playwright после навигации — 0 ошибок консоли (404 исчез); тесты `tests/test_static_assets.py` (2).
> ② **install-ревью P0-факт-чек:** незакрытых P0 нет; P1-фикс подтверждён в коде (`config.py:101 _atomic_copy`,
> `cli.py:282 except OSError`, тест `test_serve_reports_unwritable_config`) — артефакт дополнен, хвост закрыт.
> ③ **go-usage off-peak окно исправлено** (bootstrap-репо, не spend-tracker): пик 01:00–04:00/06:00–10:00 UTC пн–пт,
> выходные off-peak, выводится «следующий пик»; 5 границ проверены `-Now`; MODEL_ROUTING §11.2/§12 — открытый вопрос закрыт.
> ④ **Codespace-404 (user env):** на нашей стороне не чинится; в README восстановлен/дополнен troubleshooting
> (PORTS → Open in Browser, Stop/Start после Rebuild, Simple Browser, проверка входа) + случай 500 после обновления кода.
> **Тесты: 356 unit + 21 e2e**, ruff чист, contract ok. NSSM не трогали (Python не менялся). **Ревью $0 (ultra-550b, 64 с):
> GO, P0/P1 нет** (`EXPERT_REVIEW_TAILS_OR.md`). Коммит/push (spend-tracker и bootstrap — отдельными командами) — за юзером.
> **АКТУАЛЬНО (20.09, вечер-5, сессия 6): ✅ README + бизнес-план + /help (запрос юзера; ждёт коммита/push).**
> ① **README переписан** для обычных пользователей: «что умеет / кому подойдёт / установка одной командой /
> первые шаги / частые вопросы (`<details>`) / таблица команд»; факты и команды сохранены, ссылка на лендинг.
> ② **Ресёрч ×2** (free-субагенты): `RESEARCH_BUSINESS_PLAN_SPENDTRACKER.md` (дельта цен/бенчмарков/банков:
> GitHub Sponsors для РФ недоступен; Boosty 11.7% + НПД ≈ 15–17% с оборота; Сбер для физлиц без CSV; PFM-рынок РФ
> $8.7→9.7 млн; freemium fintech медиана 4.1%) и `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (Diátaxis, WCAG 2.2, NN/g,
> топ-20 FAQ, 15 терминов, легенда, a11y-чеклист; FAQPage JSON-LD не нужен — Google снял rich results 07.05.2026).
> ③ **Бизнес-план для руководства**: `D:\dev\docs\machine\BUSINESS_PLAN_SPENDTRACKER.md` (exec summary + 14 секций +
> слайд-скелет на 20 слайдов; честная рамка «project economics», TAM→SAM→SOM, unit-economics, риски, метрики 90 дней).
> ④ **Страница `/help`** (роут `frontend.py` + `templates/help.html` + ссылка в nav после «Подтвердить»):
> быстрый старт, how-to, глоссарий (15 терминов), легенда источников/статусов/цветов, 22 FAQ на нативных
> `<details>`, приватность, «Почему так?», ссылки; порог 0.9 и число категорий — из конфига. Лендинг: +3 FAQ
> (дубли/переводы/LLM-payload).
> **Тесты: 354 unit + 21 e2e** (+3 `tests/test_help.py`, +1 e2e `test_help_page_nav_and_faq`), ruff чист,
> contract ok (baseline +1 роут `/help`). Live: NSSM рестартнут, `/help` 200, `/health` 200; playwright desktop 1280 +
> mobile 390 — ок (консоль: только favicon-404 — хвост приложения).
> **Ревью $0** (ultra-550b, 153 с): NO-GO → адъюдикация: **P0 отклонён фактом** (`queued_for_review` возвращает свежий
> `[dict(r) for r in rows]`, паттерн index/approve/dashboard), **P1 принят** (тест читает порог из `load_settings()`);
> артефакт `EXPERT_REVIEW_HELP_OR.md`. Коммит/push — по команде юзера.
> **АКТУАЛЬНО (20.09, вечер-4, доп. deliverable): ✅ e2e-флейк CI закрыт (ждёт коммита/push).**
> Симптом: `test_rule_dead_badge_and_preview` падал на 4 пушах подряд (таймаут `_preview`), локально зелёный.
> Корень (доказан): htmx 2.0.4 `defaultSettleDelay=20ms` — `.htmx-request` снимается ДО settle, новый контент
> получает обработчики только в settle (`processNode`; маркер незрелого контента — `.htmx-added`). `_wait_single`
> ждал не того: `fill` попадал в инпут без слушателей, событие терялось, baseline `changed` фиксировался на
> введённом значении → превью-запрос не уходил вовсе (0 `htmx:trigger`, 0 сетевых запросов). Фикс: `_wait_single`
> ждёт снятия `.htmx-added`; новый детерминированный регресс-тест `tests/e2e/test_htmx_settle.py` (input в окне
> settle → 0 запросов, после → 1); правило-трап в `spec/PIPELINE.md`. Код приложения не менялся.
> Доказательства: временный зонд-петля (удалён, копия в temp) 17/52 падений ДО → 52/52 ПОСЛЕ; полный e2e
> 20 passed ×3; 351 unit; ruff; contract ok. **Ревью $0 (ultra-550b, 166 с): GO, P0/P1 нет**
> (`EXPERT_REVIEW_E2E_FLAKE_OR.md`). Коммит/push — по команде юзера.
> **АКТУАЛЬНО (20.09, вечер-3, сессия 5): ✅ лендинг + демо-кнопка (Codespaces) + Supporter/Boosty (волна 3, шаг 4) — реализовано, закоммичено (`b8e0598` + `79ee705`) и запушено; Pages live проверен.**
> `landing/` — статический лендинг (RU + EN-блок): оффер «Бюджет и подписки без облака», 3 скриншота витрины
> (дашборд с бюджетами/дайджестом, дайджест с 5 аномалиями, очередь с LLM-предложениями — сняты со стенда
> синтетики `data/demo.db`, НЕ с прод-БД), «10 минут от установки до дайджеста» (обе команды установщика),
> демо-кнопка `codespaces.new/ExNihil14/spend-tracker`, Supporter ($25/1900₽: mailto + issue-форма),
> Boosty (заглушка `REPLACE_ME` — **заменить перед запуском: `landing/index.html`, `README.md`, `.github/FUNDING.yml`**),
> опрос Telegram-vs-PWA (issue-формы), FAQ, приватность, footer. Внешних ресурсов и аналитики нет by design
> (закреплено тестом); favicon — data-URI.
> **Инфра: GitHub Pages включён** (`gh api repos/.../pages -X POST -f build_type=workflow`) → деплой по `.github/workflows/pages.yml`
> (paths `landing/**`) при push в main; URL **https://exnihil14.github.io/spend-tracker/**. Issue-формы
> `{poll-pwa,poll-telegram,supporter,bug-report}.yml` + лейблы `poll`/`supporter` созданы; `FUNDING.yml` ведёт на Boosty.
> **Тесты: 351 unit** (+7 `tests/test_landing.py` — внешних ресурсов нет, локальные ссылки/якоря существуют,
> механики на месте, workflow/FUNDING целы), ruff чист, contract ok (схема/API/роуты не менялись).
> **Live: http.server 8788** — `/`, `style.css`, 3 PNG = 200; playwright-смоук: 0 ошибок консоли, копирование команд
> в clipboard работает, skip-link `:focus-visible` 2px, desktop 1280 + mobile 390 просмотрены.
> **Ревью $0** (nemotron-3-ultra-550b:free, 172 с): **GO, P0 нет**; P1.1 (install-ссылки «сломаны на Pages») отклонён
> фактом — URL абсолютные raw.githubusercontent, не Pages-относительные (закреплено ассертом); **P1.2 принят** —
> тест теперь валидирует якоря `<a href="#...">`; артефакт `D:\dev\docs\machine\EXPERT_REVIEW_LANDING_OR.md`.
> **После push (20.09):** живой URL проверен — https://exnihil14.github.io/spend-tracker/ (`/`, `style.css`, скриншоты = 200;
> playwright: 0 ошибок консоли, рендер совпадает с локальным); CI на этом пуше **зелёный** (все 3 jobs, включая e2e).
> ⚠️ **Наблюдение:** на 4 предыдущих пушах (fix cli, экспорт, сессия 4) e2e-джоб падал на `test_rule_dead_badge_and_preview`
> (таймаут `_preview` 30 с), локально тест стабильно зелёный — флейк CI-окружения, кандидат на отдельную диагностику.
> **Открыто:** хвосты (favicon 404 приложения, Codespace-404 user env, go-usage off-peak); дальше по волне 3 —
> **PWA только после 10 внешних с ≥2 импортами** (лендинг = landing-тест; метрики-прокси без счётчиков).
> **АКТУАЛЬНО (20.09, вечер-2, сессия 4): ✅ one-command установка (волна 3, шаг 3) реализована и закоммичена (`ce4cd3b`, `6af46d1`).**
> Формат: `uv tool`/uvx + bootstrap-скрипты (Windows/Unix) + Docker; DoD «до первого дайджеста ≤10 минут».
> ① **Пути/режимы:** `config.py` — `PKG_DIR`/`DEFAULTS_DIR`, `repo_mode()` (по `config/settings.toml` рядом),
> приоритет env `SPENDTRACK_CONFIG_DIR`/`SPENDTRACK_DATA_DIR` → repo (`config/`,`data/` — прод NSSM не изменён) →
> user-dir (Win `%APPDATA%`/`%LOCALAPPDATA%\spendtrack`; Unix XDG). Дефолты `settings.toml`/`taxonomy.toml` лежат
> в пакете (`src/spendtrack/defaults/`, входят в wheel) и идемпотентно материализуются в user-config при первом
> `serve`/правке таксономии. Потребители переведены: store/doctor (БД), taxonomy/taxonomy_repo/csv_import (конфиг),
> main (static/logs), роутеры (templates). ② **CLI:** `spendtrack serve [--host/--port/--open]` и
> `spendtrack paths [--json]`. ③ **Bootstrap:** `install.ps1` (UTF-8 BOM) / `install.sh` — проверяют uv
> (нет → официальный installer astral.sh; uv сам поставит Python 3.13), `uv tool install git+https://...`,
> `serve --open`; флаги `-NoServe/--no-serve`, `-Source` (wheel/путь — для проверок). ④ **Docker (опция):**
> `Dockerfile` (`ghcr.io/astral-sh/uv:python3.13-bookworm-slim`, `uv sync --frozen --no-dev`, том `/data`,
> данные+конфиг в нём) — собран и проверен запуском.
> **Live-верификация (факты):** wheel-установка в чистый tool-env → `paths` (mode installed), `add` (ПЯТЕРОЧКА →
> groceries), `digest`, `doctor`; `serve --port 8790` → `/health`, `/`, `/static/htmx.min.js`, `/dashboard`,
> `/approve`, `/settings` — все 200, транзакция рендерится, конфиг в `%APPDATA%\spendtrack`. `uv tool run --from .`
> (uvx-путь) → installed-режим. Docker: build + run с volume → 200, в томе `spend.db`/`config/`/`logs/`;
> контейнер/том/образ удалены после проверки. `install.ps1 -NoServe` с wheel — ок; `install.sh` — синтаксис
> (полный git-путь — после push). **Live-проверка нашла реальный packaging-баг:** `llm.py` импортирует `httpx`
> на уровне модуля, а он был только в dev-группе → wheel-установка падала `ModuleNotFoundError`; `httpx` добавлен
> в runtime-зависимости. **Тесты:** 344 unit + 19 e2e, ruff, contract ok (baseline +9 символов, аддитивно; схема/роуты
> не менялись). **Прод:** NSSM рестартнут → `/health` 8 tx, `/health/data` 200, `paths` = repo-режим (`data/spend.db`),
> doctor 10/10. **Гит:** сессия 4 закоммичена по команде юзера — `ce4cd3b` (fix packaging: httpx) + `6af46d1`
> (feat install, 25 файлов); `main` ahead 2, push — по отдельной команде. **Ревью $0 (super-120b, 166 с): P0 нет; единственный P1 принят** —
> `ensure_config_dir()`: атомарное копирование дефолтов (`_atomic_copy`: tmp + `os.replace`) + понятная ошибка
> в `serve` (exit 1 с подсказкой `SPENDTRACK_CONFIG_DIR`) + тест (первый прогон ultra-550b — пустые `choices`,
> ретрай) → `EXPERT_REVIEW_INSTALL_OR.md`; **344 unit**. **Открыто:** favicon 404, Docker Desktop оставлен
> запущенным (можно закрыть), дальше — волна 3 шаг 4 (лендинг/демо-кнопка) или план E (SSE/UI-агент).
> **АКТУАЛЬНО (19.09, сессия 2 — план E, всё запушено `fec01fb`):** ① **экспорт Abacus: 506 диалогов (54 МБ)**
> + просмотрщик (`D:\data\notes\abacus-export\2026-09-19\viewer\index.html`; CLI-поиск `abacus_search.py`) —
> скрипты `abacus_web_export.py`/`abacus_render.py`, эндпоинты сняты через playwright; ② **второй мастер-план канала**
> (`out_analysis/MASTER_PLAN_AI_SHEMSEDINOV_ROUND2.md`: 15 видео/429 записей, Opus 5 ≈$0.65); ③ **слепой аудит Fable 5.1**
> (`EXPERT_AUDIT_SPENDTRACKER_FABLE.md` ≈$0.5) → **волна 3 пересобрана: BYO-LLM → экспорт → установка → лендинг →
> PWA после 10 внешних**, hosted убран; ④ **фаза 0 в коде:** офлайн-гейт LLM (без ключей — ноль сетевых вызовов),
> лимиты импорта (байты/413/HTMX), `PRIVACY.md`/`SECURITY.md`, тест «нулевой сети»; попутно закрыт реальный баг:
> импорт не ставил `pending`/терял `category_llm`; ⑤ `fix(codespaces)`: сервер обслуживает демо-БД (было demo.db ≠ spend.db).
> **299 unit + 18 e2e**, contract ok, ревью $0 (`EXPERT_REVIEW_PHASE0_OR.md`). Коммиты: `9fe3697`,`8a609c1`,`58de1d2`,`c1d3d6c`,`fec01fb`.
> **Открыто (user env):** Codespace-порт 8766 отдаёт GitHub-404 при `curl localhost:8766/health`=200 — диагноз/шаги
> в `SESSION_START_PROMPT.md` (сверить `$CODESPACE_NAME`, пере-форвардинг, Stop/Start, Simple Browser как обход).
> **Дальше:** ③ SSE-батчи (0 кред.) / ④ UI-агент по рынку / волна 3 шаг 1 = BYO-LLM.
> **АКТУАЛЬНО (20.09): волна 3, шаг 1 — BYO-LLM/Ollama реализован (deliverable сессии; ждёт коммита по команде юзера).**
> Закрыт P0 «нет облака vs free-LLM»: явный выбор провайдера без «тихих» фолбэков. Режимы (приоритет): off (дефолт —
> ноль сети) → BYO (`SPENDTRACK_LLM_BASE_URL/MODEL/API_KEY`, любой OpenAI-совместимый сервер) → Ollama-пресет
> (`SPENDTRACK_LLM_PROVIDER=ollama`, air-gap, модель `llm.offline`) → free-цепочка (ключи; локальные шимы — строго
> `ALLOW_LOCAL_LLM=1`). Код: `llm.py` (`resolve_providers()`/`llm_status()`, frozen `LLMProvider`), `cli.py`
> (`spendtrack llm-status [--json]`), `config.py` (поля `llm_*`); попутно фикс маппинга ключ↔URL после swap `c90e43e`.
> Тесты **314 unit** (+15: `tests/test_llm_byo.py`, BYO-тест в `test_offline.py`), ruff, contract ok (baseline обновлён).
> Live: BYO через локальную заглушку (11500) → `groceries`/`source=llm`; **реальный прогон на локальном Ollama**
> (`qwen2.5-coder:3b` скачан, outbound заблокирован кроме loopback): `ДОДО ПИЦЦА МОСКВА` → `restaurants` conf 0.98
> (принято), неизвестный мерчант → `other` conf 0.5 → **очередь (`pending`, `category_llm`)**. Прогон выявил и
> закрыл реальный баг: CLI `add` терял `category_llm`/`review_status`/`confidence` — фикс + `tests/test_cli_add.py`
> (**317 unit**); те же гарантии, что phase-0 фикс импорта.
> Прод NSSM рестартнут: `/health` ok, `/health/data` ok; прод-`.env` без ключей → режим LLM = off. Ревью $0:
> **GO без P0** (`D:\dev\docs\machine\EXPERT_REVIEW_BYO_LLM_OR.md`; 5 P1 — 3 приняты/внесены, 2 отклонены фактами).
> **Дальше по волне 3:** ② экспорт CSV/Excel → ③ one-command установка → ④ лендинг/демо → ⑤ PWA после 10 внешних.
> **АКТУАЛЬНО (20.09, шаг 2 волны 3): ✅ экспорт CSV/XLSX реализован (закоммичен `44adca4`, запушен).**
> `Store.export_transactions()` (tuple, без лимита страницы 500) + `export.py` (CSV: utf-8-sig/«;»/CRLF/ASCII-минус;
> XLSX: openpyxl — нативные типы, автофильтр, freeze; защита от formula-инъекций `'` в текстовых полях) + CLI
> `spendtrack export [--format csv|xlsx] [--month|--from/--to] [--out]` + веб `GET /export.csv|.xlsx` (текущий фильтр)
> и кнопка «Экспорт CSV» на главной. **E2E поймал реальный баг:** `hx-boost` на `<body>` перехватывал клик и
> скачивание не происходило → фикс `hx-boost="false"`. Тесты **331 unit + 19 e2e**, ruff, contract ok (baseline
> +9 символов/+2 роута; новая зависимость openpyxl). Live: прод NSSM рестартнут; `/export.csv` 200 (BOM, 8 строк),
> `/export.xlsx` 200 (PK, 6 КБ), кнопка видна (playwright MCP). **Ревью $0: NO-GO → после адъюдикации** — исправлен
> реальный UX-баг (невалидные `--from/--to/--month` давали тихий пустой файл: теперь argparse-ошибка), приняты
> docstring-ограничения памяти и одноразовой итерации XLSX, добавлены тесты пустого XLSX/инъекций/фильтров;
> 2 P1 отклонены фактами (`EXPERT_REVIEW_EXPORT_OR.md`). Дальше: one-command установка.
> **АКТУАЛЬНО (19.09, вечер-2): автоматизация + демо-режим + стратегия рынка + AGPLv3.** ① Автогейт контракт-дельты
> (`scripts/contract_delta.py`, CI-шаг) и one-command ревью (`scripts/review.py`) — **289 unit**, коммиты `a3f1871`/`d0e5c83`;
> ② **демо-режим** (`scripts/demo_data.py`: 350 tx, 6 подписок, 3 типа аномалий, 6 pending, 5 бюджетов; Codespaces-автосид,
> стенд 8767) — `0f80e5c`/`d81c369`; ③ **рынок**: `RESEARCH_SPENDTRACKER_MARKET.md` (46 источников) + `EXPERT_STRATEGY_...`;
> решения — **AGPLv3**, **RU-first**, валидация «10 CSV» → лендинг-запуск, Boosty (11.7%); ④ **волна 3 расширена рыночными
> S-задачами:** экспорт CSV/Excel, one-command установка (Docker/uvx), лендинг + демо-кнопка (Codespaces), BYO-LLM/Ollama;
> ⑤ i18n/локализация/юр/a11y — `D:\dev\docs\machine\DESIGN_I18N_LEGAL_A11Y.md`. **Ждут коммита: LICENSE (AGPLv3) + README
> (Для кого/EN/поддержка) + continue.md.** Push — юзера (ahead: см. git status).
> **АКТУАЛЬНО (19.09): тяжёлый one-shot экспертный анализ проекта + роадмапа выполнен (Abacus, claude-opus-5).**
> Артефакт: `D:\dev\docs\machine\EXPERT_ANALYSIS_SPENDTRACKER_ABACUS.md` (протокол отбора модели + факт-чек P0 + полный отчёт).
> Прогон: 1 запрос, 110 с, 2990 in / 5910 out ≈ $0.175 ≈ 0.9% месячного лимита Abacus; рекурсии нет. Ключевые выводы:
> ① «фичи опережают данные» (в проде 8 tx; recurring/digest/калибровка data-gated) → **рекомендация: волна 3 = Telegram
> quick-capture как канал данных** (при неприятии приватности — PWA-быстрый ввод), merge категорий попутно, цели/net worth
> отложить до ≥3 мес истории; ② P0-долг: `busy_timeout` (WAL/`foreign_keys` уже есть), restore-drill бэкапа + копия вне
> ноутбука, gitleaks в CI, кламп confidence/лимит длины LLM-входа; ③ evals-контур: golden-набор ~100+ merchant-строк →
> оффлайн-калибровка порога 0.9 без ожидания прода. Наш факт-чек: тезис про fingerprint/`export_rowid` частично отклонён
> (дедуп уже hardening’ен 15.09 — индекс повторяемости), остальное принято. **Контр-мнение (Gemini 3.1 Pro, 1 запрос ≈$0.027, адъюдикация — в артефакте §5):** долг ДО фичи; **PWA-ввод предпочтительнее Telegram** (ноутбук спит — long-polling вне дома не работает; у TG-варианта апдейты копятся в облаке, но «мгновенного захвата» нет); И3 (evals на синтетике) урезать до smoke-калибровки; sync+идемпотентность обязательно в DoD ввода. **Итог двух моделей: сначала P0-долг (S) → канал данных с PWA-уклоном (M) → merge/bulk попутно. Решение юзера; без команды не реализуем.**
> **Исполнитель реализации (роутинг 19.09, артефакт §3a):** основной — `opencode-go/deepseek-v4.1-flash` (все волны 1–2 на нём);
> эскалация волны 3 при провале — `opencode-go/deepseek-v4-pro` (SWE-V 80.6/TB2 67.9, та же семья, новый чат, ≤2/нед),
> альтернатива `glm-5.3`; Abacus-флагманы — только one-shot дизайн-чек (~$0.05), не исполнители.
> **P0-долг РЕАЛИЗОВАН (19.09, субагент flash по ТЗ `TASK_BRIEF_P0_DEBT.md`) и принят оркестратором:**
> busy_timeout/synchronous + pragma-тест; `scripts/restore_drill.py` + doctor-чек `restore_drill` (info/warn/critical) + маркер;
> gitleaks-job в CI; кламп confidence + лимит description 300. **+22 теста → 275 unit, ruff чист.** Live: drill ok
> (count/sum совпали с живой БД), doctor 10/10, `/health/data` 200 (NSSM рестартнут). Ревью $0 (ultra-550b, 77 с): GO;
> **3 P0 из 4 отклонены фактами** (порядок pragmas — замер sync=1; `as_uri?mode=ro` реально read-only; бэкапы — VACUUM INTO
> без `-wal`), P1 применены (tz-конверсия, детерминированный timing, докстринг). Артефакт `EXPERT_REVIEW_P0DEBT_OR.md`.
> **Закоммичен и запушен (`26f9aec`); доки процесса (дисциплина данных) — `cf1064b`. Следующее — волна 3: канал данных с PWA-уклоном.**
> **АКТУАЛЬНО (18.09, вечер): волна 2 — дайджест недели + флаги аномалий (S+S) реализованы и запушены (`d610370`, `8442950`).**
> Ядро `src/spendtrack/digest.py` (read-only, на лету, состояние не хранится): окно rolling `--days N` (дефолт 7) vs прошлое
> окно; расход/доход/баланс + дельта, топ-5 категорий расхода с дельтами, самый дорогой день, средний расход/день,
> pending, ближайшие ожидаемые списания рекуррингов (`next_expected` ≤14 дн; просроченные помечаются), аномалии top-10:
> ① `large_expense` — ≥3× медианы |расходов| категории за 90 дн, ≥10 наблюдений, пол 1000 ₽; ② `price_jump` — первое
> отклоняющееся ≥10% списание после активного рекурринг-кластера (событие смены цены; повторно не флагуется);
> ③ `near_duplicate` — один день + мерчант + |сумма|, ≥2 строк (fingerprint не склеил). Переводы исключены везде,
> доход — только в итогах. CLI `spendtrack digest [--days N] [--json]` + карточка «Дайджест недели» на `/dashboard`.
> **252 unit + 18 e2e зелёные, ruff чист**; live-прогон на прод-БД (в окне пусто — data-gated норма, pending 6), NSSM 8766
> рестартнут, `/health/data` ok, карточка проверена playwright MCP (prod, empty-state). Ревью OpenRouter :free ×2 $0
> (`EXPERT_REVIEW_DIGEST_OR.md`): **все 3 P0 отклонены фактами** (семантика первого скачка, `category NOT NULL`,
> знак Δ расхода), приняты P1 (bound `date<=end`, «просрочено» в CLI, шкалы score, +4 теста). Доки: PIPELINE/CONTEXT/AGENTS.
> **Следующее — волна 3 по выбору юзера:** Telegram quick-capture (M, приватность) / слияние категорий (S) / цели-net worth;
> калибровка 0.9 — 2/20 решённых (data-gated).
> **АКТУАЛЬНО (17.09, вечер): СЕССИЯ ЗАКРЫТА — всё запушено, CI зелёный, MCP-стек активен.**
> `origin/main = 7da8cfe` (8 коммитов: doctor, recurring, suggest-rules, фиксы Codespaces/CI, doctor-hardening, доки);
> CI на последних push: `e2e` + `lint-and-test` зелёные (фикс флейка превью подтверждён). Bootstrap: `9592aeb` (probe-mcp.py).
> **MCP (после рестарта opencode) проверен живыми вызовами:** context7 (FastAPI IDs), memory (граф), **playwright —
> открыл `/dashboard` стенда 8767, карточка «Подписки / рекурринги» найдена («активных 3, −652.00 ₽/мес»)**.
> Бэклог-мелочь: `favicon.ico` 404 в консоли (добавить favicon в `static/` + link в `base.html`).
> **Следующая сессия — волна 2: дайджест недели + флаги аномалий** (S+S; стартер обновлён в `SESSION_START_PROMPT.md`).
> **`suggest-rules` (волна 1 п.3) реализован, отревьюен и закоммичен** (`1b953c4` + doctor-фикс `aa79fb9` + доки `7da8cfe`):
> read-only кандидаты keyword-правил из решений человека (corrections, переопределения LLM в approved-строках, examples,
> тип «merchant»); униграммы/биграммы (UPPER, без цифр, длина 2–64), пороги n≥3/чистота ≥80%, конфликты видны, статусы по
> `analyze_rules` (новое/дубль/мёртвое/пересечение); CLI `spendtrack suggest-rules [--json]`, записей нет. **225 unit зелёные
> (14 в test_suggestions), ruff чист**; live на прод-БД: «решённых строк 1, кандидатов 0» — data-gated норма.
> Ревью :free $0 (ultra NO-GO / super обрезано): приняты — лимит длины паттерна 2–64, верный текст «пересечение»,
> кириллица І/Ї/Ґ/Ў, тип исключения в `_guarded`, +5 тестов; ложный P0 super («двойной счёт при OR») отклонён фактом SQL;
> артефакт `EXPERT_REVIEW_SUGGEST_RULES_OR.md`.
> **Попутный doctor-фикс (найден стрессом флейка):** `_guarded` переводит любое исключение чека в critical,
> `quick_check` корректно обрабатывает «PRAGMA упал» (malformed); тест порчи БД стал детерминированным (rootpage),
> 15/15 в стрессе. Детали — в PIPELINE §Suggest-rules.
> **АКТУАЛЬНО (16.09, ночь): рекурринги/подписки готовы и закоммичены `236525f` (волна 1 п.2; ждёт визуального смоука и push юзера).**
> **Фиксы по следам проверок (16.09 ~22:00, закоммичены):** ① Codespaces-500 на `/dashboard` — воркспейс синкнулся на новый
> коммит при живом старом uvicorn (Jinja горячие, Python нет) → `UndefinedError: 'recurring'`; фикс — `--reload` в
> `.devcontainer/start-app.sh` + README-troubleshooting (`d47e3eb`). ② CI-флейк `test_rule_dead_badge_and_preview`
> (падал в CI с 12:57, к recurring отношения не имеет: гонка дебаунс-запросов превью и пустого фрагмента для паттерна
> <2 символов) — фикс: ожидание своего запроса по `post_data` через `expect_response` (`7bfd16a`).
> Ревью :free $0 — GO без замечаний (`EXPERT_REVIEW_CODESPACES_CI_OR.md`; ultra-550b 3× пустой ответ провайдера,
> вердикт дал super-120b). **Ждут push юзера: `2579e74`, `d47e3eb`, `7bfd16a`** (CI подтвердит фикс флейка после push).
> 209 unit + 17 e2e зелёные, ruff чист. Ядро `src/spendtrack/recurring.py` (read-only, вычисление на лету): кластеры сумм
> ±5% бегущей медианы, ≥3 повторов, интервалы 27–34 дн (медиана 28–31), 1 пропуск месяца (56–62 дн), `active` ≤40 дн;
> только расходы, без transfers; «цена» = медиана кластера (по всем списаниям), категория — самая частая; уникальные дни —
> для интервалов и счётчика. Вывод: CLI `spendtrack recurring [--json]` + карточка «Подписки / рекурринги» на `/dashboard`
> (по всей истории, активные в итог). Ревью ×2 OpenRouter :free ($0, nemotron ultra/super — `EXPERT_REVIEW_RECURRING_OR.md`):
> **P0 отклонены фактами** (cat_colors/fmt есть в контексте), принята правка «цена по всем списаниям кластера» +регресс-тест.
> Live: прод-БД = 0 находок (демо-масштаб — норма); смоук-стенд `http://127.0.0.1:8767/dashboard` (temp-БД, синтетика
> 4 мес: 4 находки / 3 активные, месячный итог −652.00) — ждёт визуальной проверки юзером; прод NSSM рестартнут,
> `/health/data` ok. Доки: PIPELINE/CONTEXT/ARCHITECTURE/AGENTS. Детали смоука: temp\opencode\recurring_smoke\.
> Ниже — предыдущий статус (doctor) и исторические снимки.
> **АКТУАЛЬНО (16.09, вечер): 191 unit + 16 e2e зелёные, ruff чист; doctor закоммичен и запушен** (`0ad83f2` + `a20dcc8` + `1bd36bf`; **origin/main синхронен**), **прод рестартнут — live `/health/data` = 200 `status: ok` (9/9 чеков ok, backup свежий)**. **Фикс CLI-кодировки `2e4c93a` (+ доки `60d9e16`) запушены — origin/main синхронен** (`fix(cli): UTF-8 stdout` — кириллица в Git Bash/пайпах + символ «≠» в warn-деталях не роняют печать; ревью `EXPERT_REVIEW_CLI_UTF8_OR.md`, GO с правками; 3 теста; **сервер не задет — cli сервером не импортируется, рестарт не требуется**). Состав коммитов: `src/spendtrack/doctor.py` + `tests/test_doctor.py` (25 тестов), правки `cli.py`/`main.py` (`GET /health/data`), доки PIPELINE/CONTEXT/continue.md. Ревью OpenRouter (`EXPERT_REVIEW_DOCTOR_OR.md`, $0, 337с): **GO с правками** — приняты `OR category IS NULL` для budgets (SQLite-квирк TEXT PRIMARY KEY; факт-проверено), detail quick_check (все строки ошибок), +5 тестов (db_open/taxonomy_config/precedence/NULL-budget/путь с пробелом); P0 про NULL в NOT NULL-колонках отклонены фактами (IntegrityError), кэш `/health/data` — YAGNI. Doctor: 9 проверок (quick_check/fingerprint_dupes/user_version/categories_invalid — critical; category_llm_invalid/refs_invalid/pending_source — warn; empty_batches — info; backup — info/warn/critical), CLI `uv run spendtrack doctor [--json]` (exit 1 только critical), API `GET /health/data` (503 при critical; `/health` не тронут). Живые смоуки: CLI на прод-БД (WARN только backup), dev-uvicorn `/health/data` 200 UTF-8 (остановлен). **Doctor нашёл и помог починить реальную проблему:** задача `spendtrack-backup` не срабатывала (LastTaskResult 0x800710E0; Principal Interactive + `DisallowStartIfOnBatteries=True` + `StartWhenAvailable=False`) — 16.09 17:58 включены догон пропусков, запуск на батарее, `ExecutionTimeLimit=PT1H` (XML-снимок до правки: `temp\spendtrack-backup.before.xml`); прогон задачи → `LastTaskResult=0` + свежий `spend-20260916-145810.db`, doctor = ok (см. `spec/PIPELINE.md` §Doctor). **Пуш и рестарт сделаны юзером 16.09 (вечер): origin/main = `1bd36bf`, live `/health/data` 200 `ok`.**
**Второе ревью** (другая модель, `EXPERT_REVIEW_DOCTOR2_OR.md`, $0): GO с правками — приняты `_guarded` ловит и `OSError`,
детерминированная сортировка бэкапов, +3 теста; попутно закрыт найденный нами пробел: **снимок 0 байт проходил
`quick_check` как пустая БД** → добавлена проверка наличия таблицы `transactions` в снимке. Отклонено фактами:
«утечка префикса fingerprint» (localhost; локальный злоумышленник читает саму БД), `MultipleInstances` (уже IgnoreNew),
NULL в `rules.category` (NOT NULL). **Правки doctor.py после ревью закоммичены `a20dcc8`** (+3 теста, 188 unit). **Инцидент 16.09:** 35 мин сессии шли на `hy4-preview` (клиентская смена модели в простое, без 429/автофолбэка; $0.80 = 86% стоимости сессии $0.93) — разбор в `MODEL_ROUTING_OPENCODE_GO.md` §12; там же 🔧 устаревшее окно off-peak в `go-usage.ps1` (наше 16:30–00:30 UTC vs офиц. пик 01:00–04:00/06:00–10:00 UTC пн–пт). Следующий deliverable: детекция рекуррингов/подписок (волна 1 п.2).** Ниже — исторические снимки; цифры в них не актуальны.
> **✅ ФАЗА 2 /settings — ПРАВИЛА В UI (15.09):** `POST /settings/rules` (add в конец), `/delete`, `/move` (up/down swap),
> `/preview` (live-превью дублей/перекрытия, debounce 400мс). Вся запись через общий `save()` — атомарно + `.bak` + аудит
> (`add_rule|delete_rule|move_rule`) + конфликт-хэш. Диагностика `analyze_rules`: мёртвые = нет категории / дубль /
> перехвачено более ранним правилом-подстрокой (first-match) + обратное «перекрывает #…»; сверху сводка.
> **Эксперт-ревью (arch-reviewer, deepseek-v4-pro) — GO с правками, P1 закрыт:** перехватчиком в диагностике считается
> только runtime-валидное правило (рантайм пропускает битые категории) + тестер больше не показывает winner из битого
> правила; закрыты пробелы (`.bak` = предыдущая версия, MAX_RULES, lowercase round-trip). Артефакт:
> `D:\dev\docs\machine\EXPERT_REVIEW_SETTINGS_PHASE2.md` (P2-бэклог: audit не должен ронять операцию, parse-back контентом и др.).
> **Попутно починен латентный баг Фазы 1:** partials не содержали свои обёртки `#settings-categories/#settings-rules`,
> из-за чего вторая операция без перезагрузки не находила htmx-target. E2E теперь изолирует taxonomy (`SPENDTRACK_TAXONOMY`,
> tmp-копия + восстановление) — прод-конфиг не трогается. **Live NSSM:** диагностика нашла реальное мёртвое правило
> в проде (#23 «ЗАРАБОТНАЯ ПЛАТА» перекрыто #21 «ЗАРАБОТНАЯ»), превью вернуло «дубль + будет мёртвым». Дизайн-док обновлён.
> **Импорт провалидирован синтетикой** (реальных выписок нет): `tests/synth_bank.py` (seeded-генератор sber/tinkoff/yandex) + `tests/test_synth_import.py`; critical-фикс дедупа (occurrence вместо позиции строки — реэкспорт со сдвигом не дублирует). Стратегия: `D:\dev\docs\machine\TEST_DATA_STRATEGY.md`.
- ✅ **Фаза B закоммичена (77a25dc)**: дашборды (Chart.js+htmx), URL-фильтры hx-push-url, hx-boost, фикс формы добавления (JSON+form, HX-ветка HTML), deepseek-фолбэк, spec/ A+PIPELINE+stack. **43 passed, ruff чист, рабочее дерево чистое** — практика №3 MASTER_PLAN «commit перед задачей, diff после» выполнена.
- ✅ mattpocock/skills audit (13.09): всё внедрённое используется.
- ⏳ Визуальный smoke `/approve` в браузере юзера (план: `spec/QA_APPROVE_SMOKE.md`, демо-данные `scripts/review_demo.py seed`).
- ✅ Пробелы MASTER_PLAN закрыты/пересмотрены: perf-маркер с JSON закрыт (`75f8165`, `reports/perf.json`, маркер в pyproject); Hoppscotch/Capture MCP — **отклонены** (SPENDRACK_PRIORITIES_REVIEW); Фаза 4 закрыта (v0.1.0, remote, защита `main`).
- ✅ **Сортировка транзакций (14.09):** режимы `recent` (дата DESC; внутри дня — `statement_order` из выписки, иначе id) и `amount` (|сумма| DESC) с URL-состоянием `?sort=`; миграция v3 (`statement_order`), импорт заполняет порядок строк; фильтры/месяц сохраняют sort.
- ✅ **Группировка по дням (15.09):** в режиме «recent» — заголовок дня `ДД.ММ.ГГГГ` + итог за день (цвет по знаку); в «крупные сначала» — плоский список. **Keyset-scroll осознанно отложен:** список помесячный, лимит 500 покрывает месяц; вернуться при мультимесячном режиме.
- ✅ **Словарь мерчантов + точность правил:** `tests/merchants.py` (27 реалистичных брендов/формулировок) + `tests/test_rules_accuracy.py` — покрытие keyword-правил **100%** (оффлайн).
- ✅ **Keyset-пагинация по дням (15.09):** `list_transactions_days` + `partials/tx_rows.html` + `/transactions/more` + sentinel (`hx-trigger="revealed"`) — готовность к большим спискам без разрезания дней/итогов; месяцу хватает одной страницы (PAGE_DAYS=31). Виртуализация `<table>` отклонена (анализ: `D:\dev\docs\machine\VIRTUALIZATION_ANALYSIS.md`); Фаза 2 (div-grid + content-visibility / TanStack Virtual) — по триггеру «все месяцы + >5K узлов».
- ✅ **Toast-подтверждение (15.09):** OOB-тост «Одобрено: <категория> — <описание>» / «Пропущено: …» / «Одобрено записей: N» (`aria-live`, авто-скрытие 1.8с).
- ⏭ Следующее по ROI: визуальный smoke `/settings` в браузере юзера → калибровка порога 0.9 по бакетам
  confidence (данные копятся) → бюджеты по категориям. Из Фазы 4 дизайна — merge категорий (по запросу).
- ✅ Стилизация UI Tailwind завершена (13.09.2026): `base.html` + `index.html` + `approve.html` — утилитарные классы Tailwind v4 vendored (282KB static/tailwind.js), card-style summary, table stripes, responsive grid. Всё рендерится: smoke-тест 200 OK.
- ✅ DeepSeek-категоризация добавлена третьим фолбэком (OpenRouter → FreeLLMAPI → **abacus-web shim:3201/deepseek-v4-1-flash** → offline). Токен TTL 1ч. **Проверена ЖИВЫМ вызовом: «МАГНИТ» → groceries, conf 0.96.**
- ✅ Контур верификации: `tests/test_fallback.py` (порядок primary→fallback→deepseek с моком, оффлайн), итого **37 passed**, ruff чист.
- ✅ **Фаза 2 smoke-тест полного сценария (13.09)**: dev-сервер UP + shim UP → POST /api/transactions (live deepseek, conf 0.35 → llm_pending_review) → GET / (htmx: строка транзакции, бейдж категории, источник+conf, счётчик «Подтвердить»=1). Тестовая запись удалена после проверки.
- ✅ **Фаза 1 (фундамент контекста)**: spec/ теперь содержит ARCHITECTURE.md + stack.md (стек/версии/LLM-маршрут) + PIPELINE.md (команды, контур верификации, аддитивные миграции).

## Stack-вердикт (13.09.2026, анализ с фокусом на 2026-исследования)
**Остаёмся на htmx + FastAPI + SQLite.** React + TS переходит ТОЛЬКО при: >3 concurrent users / offline-first / rich-интерактив (drag-drop, real-time charts) / команда >2 человек (оценка миграции: 80-120ч, обнулит 37 тестов).
- React+TS vs htmx → **htmx** (85%): CRUD-heavy, htmx даёт ~80% UX React за 20% сложности.
- TanStack Query vs htmx data-fetching → **htmx** (80%): наш state серверный (SQLite), client-side кэш не нужен.
- TanStack Router vs React Router v7 → **TanStack Router** (70%, только если React): TS-first, Zod-валидация search params, loader typing.
- FastAPI vs Node → **FastAPI** (90%). SQLite vs PostgreSQL → **SQLite/WAL** (95%).
- НЕ использовать: PostgreSQL, Redis, GraphQL, Docker, Next/Remix (SSR не нужен), microservices.
- Ближайшие улучшения htmx: `hx-boost` (плавные переходы), OOB swap (динамика счётчиков), фильтры в URL через `hx-push-url`, дашборды (Chart.js + htmx).

## Известные ограничения/грабли
- Правка юзера → merchant_cache + few-shot (правит будущий импорт).
- Не запускать qwen 7b одновременно с dev-сервером (GTX 1050 4GB).
- Стройные проверки: «готово» без фактической проверки не принимается.

## Следующие шаги (приоритет — Фаза A/B из MASTER_PLAN.md)
1. ✅ Стилизация UI Tailwind завершена (13.09).
2. ✅ DeepSeek-категоризация (третий фолбэк) — реализована + живая проверка + тест порядка фолбэков.
3. ✅ Live-категоризация в UI (browser-проверка, Фаза 2 smoke): POST /api/transactions → deepseek (conf 0.35, llm_pending_review) → GET / htmx-отображение (бейдж категории, источник+conf, счётчик «Подтвердить»). Проверено через curl, тестовая запись удалена.
4. ✅ spec/: ARCHITECTURE.md + stack.md + PIPELINE.md (Фаза 1 MASTER_PLAN — фундамент контекста).
5. ✅ Фаза B: дашборды (Chart.js + htmx), URL-фильтры `hx-push-url`, hx-boost/OOB-свапы (`77a25dc`).
6. ✅ Импорт банка (Work 2, `422a56f`) + circuit breaker/Playwright E2E (`833c48c`).
7. ✅ Очередь подтверждения категоризации (Work 3, `0b746d6`) + e2e `/approve` (`511b630`).
   Единый фрагмент очереди `partials/review_rows.html`, все действия через `_rows_html`+OOB.
8. ✅ UI-блок закрыт: категории/правила/переименование (`c9c42c4`, `973d280`, `2e12d6c`) + бюджеты (`73cc5fa`).
   Далее: ① ✅ прод-NSSM перезапущен 16.09 13:08 (v4 + фикс дашборда; см. `spec/PIPELINE.md` — шаблоны Jinja
   применяются без рестарта, Python — только с рестартом: после правок и шаблонов, и кода сразу перезапускать);
   ② ✅ **реальная выписка — закрыто:** недоступна, контур синтетический (`D:\dev\docs\machine\TEST_DATA_STRATEGY.md`,
   DoD выполнен; property-тесты `parse_amount` добавлены 16.09); ③ ✅ smoke `/settings` пройден юзером (все чеки);
   ④ калибровка порога 0.9 — при решённых ≥20 (сейчас 2/20); ⑤ FinOps §11 / виртуализация — по триггеру;
   ⑥ ✅ CI e2e-джоб (`e5b13ac`); few-shot-фикс `approve-all` и сортировка очереди запушены (`35064ba`, `ce85a32`).
   ⑦ **Волна 1 (решение юзера 16.09) — ЗАКРЫТА (17.09, всё запушено):** ① ✅ **`doctor`/health целостности** (`0ad83f2`+`a20dcc8`,
   ревью ×3 + hardening `aa79fb9` — guard ловит любое исключение чека); ② ✅ **рекурринги/подписки** (`236525f`, ревью ×2;
   визуальный смоук выполнен агентом через playwright MCP — карточка «Подписки» на `/dashboard` найдена); ③ ✅ **`suggest-rules`**
   (`1b953c4`, ревью `EXPERT_REVIEW_SUGGEST_RULES_OR.md`, 14 unit). Калибровка 0.9 — по мере накопления решённых (2/20).
   ⑧ **Волна 2 — ЗАКРЫТА (18.09):** ✅ **дайджест недели + флаги аномалий** (`digest.py`, CLI `digest [--days N] [--json]`,
   карточка на `/dashboard`; 27 unit + e2e; ревью ×2 OpenRouter :free $0 — `EXPERT_REVIEW_DIGEST_OR.md`). Запушено.
   ⑨ **Волна 3 (пересобрана 19.09 по слепому аудиту Fable — `EXPERT_AUDIT_SPENDTRACKER_FABLE.md`):**
   ① **BYO-LLM/Ollama** (закрывает P0 «нет облака vs free-LLM»); ② **экспорт CSV/Excel**; ③ **one-command установка**
   (`uv tool`/uvx + bootstrap); ④ **лендинг + демо-кнопка** (Codespaces); ⑤ **PWA — только после 10 внешних пользователей
   с ≥2 импортами** (HTTPS/auth/телефоны — скрытая стоимость; ручной ввод нужен в основном для наличных).
   **Hosted убран из плана совсем** (ответ на запросы синка — экспорт/импорт + Syncthing/Tailscale).
   **Сделана фаза 0:** офлайн-first гейт LLM (без ключей — ноль сетевых вызовов), лимиты импорта (10 МБ / санитарные суммы),
   `PRIVACY.md`/`SECURITY.md`, тест «нулевой сети»; попутно найден и закрыт реальный баг: импорт не ставил `pending`/
   `category_llm` (низкоуверенные строки не попадали в очередь).
   **Осталось из аудита (S):** a11y-победы (`:focus-visible`, контраст, e2e-ассерты), golden-фикстуры через anonymizer,
   детектор дрейфа формата банка, «10-минутный сценарий установки» с 3 людьми, метрики-прокси (opt-in ping), offsite-бэкап.
   **Бэклог-опция:** парсеры банков отдельным MIT-пакетом (SEO/встраиваемость).

## Мета
- Возврат к работе: просто прочитай эти файлы: AGENTS.md (команды), CONTEXT.md (словарь),
  spec/ (детали), continue.md (статус).