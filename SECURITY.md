# Безопасность spend-tracker

## Модель угроз (честно)

Приложение рассчитано на **одного пользователя на localhost**:

- сервер слушает `127.0.0.1` (и dev-скрипт, и NSSM-сервис) — **без аутентификации**;
  не выставляйте порт в сеть напрямую; для удалённого доступа — только через реверс-прокси с TLS и авторизацией
  (или Tailscale/VPN).
- БД SQLite (`data/spend.db`) **не шифруется** — защищайте файл средствами ОС (BitLocker, ACL).
- Ключи LLM — только в переменных окружения / `.env` (в `.gitignore`); в БД, логи и git они не пишутся.
  Секреты в репозитории проверяет gitleaks в CI.

## Что уже сделано

- **Офлайн по умолчанию**: без ключей LLM сеть не используется (тест `tests/test_offline.py` в CI);
  что именно уходит при включённом LLM — см. [`PRIVACY.md`](PRIVACY.md).
- **Лимиты импорта**: CSV ≤ 10 МБ; операции с |суммой| > 1 млрд ₽ отбрасываются в отчёт `invalid`
  (защита от OOM и мусорных строк).
- **Валидация выхода LLM**: категория проверяется по таксономии (иначе `other`/очередь), confidence в [0,1],
  описание усечено до 300 символов.
- **Дедуп/целостность**: fingerprint-дедуп повторного импорта; `doctor` (13 проверок) + restore-drill бэкапа.
- **Бэкапы**: `scripts/backup.py` (VACUUM INTO) + проверка восстановлением; внешняя копия —
  `--copy-to <USB/папка>` (отказ, если это тот же диск); `doctor` следит за свежестью и целостностью копии.
- **Метрики**: автоматической отправки нет; `doctor --share` только печатает анонимную сводку (см. PRIVACY.md).
- **Периметр браузера**: state-changing запросы (POST/PUT/PATCH/DELETE) проходят гейт Origin/Sec-Fetch-Site
  (`spendtrack/security.py`): `Origin` — только loopback-имена (порт любой), иначе `Sec-Fetch-Site` ∈
  {same-origin, none}; запросы без обоих заголовков (CLI/тесты) пропускаются. Плюс `TrustedHostMiddleware`
  (только `127.0.0.1`/`localhost`, иначе 400) — защита от DNS-rebinding/Host-атак. CSRF-токены не нужны:
  нет сессии/cookie, привязывать нечего; `HX-Request` — не гейт (сломал бы форму без JS).
- **Заголовки безопасности**: CSP `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none';
  form-action 'self'` + `X-Content-Type-Options: nosniff` + `Referrer-Policy: no-referrer` (middleware в
  `main.py`). Inline-скрипты и `hx-on::*` вынесены в `/static/app.js`/`dashboard.js`, `htmx.config.allowEval=false`
  — `unsafe-inline`/`unsafe-eval` для скриптов не требуются. `style-src 'unsafe-inline'` остаётся осознанно:
  inline-стили цветов категорий и темы. Кэш: версионированная статика (`?v=<hash>`) — `immutable`, без версии —
  `no-cache`, HTML/API — `no-store`.
- **Lifecycle данных**: SQLite-соединение — одно на запрос (FastAPI dependency `get_store`), `close()` в
  `finally` + `PRAGMA optimize` перед закрытием; `cache_size=8 МБ`, `temp_store=MEMORY`. Это устраняет
  накопление соединений/WAL-reader'ов до GC.
- **Supply chain**: `uv.lock` в репо + `uv lock --check` в CI; `pip-audit` (dev-зависимость, шаг CI);
  Dependabot (pip + github-actions); все сторонние GitHub Actions пиннуты по commit SHA; `permissions: read`.
- **Диск и бэкапы**: БД и `-wal`/`-shm`/temp лежат plaintext на томе — защищайте BitLocker'ом тома +
  NTFS-ACL на `data/` (в нашей машине BitLocker выключен — включить). Offsite-копия (`--copy-to`) —
  plaintext-файл: если она покидает машину, шифруйте архив. SQLCipher осознанно не используется (вне модели
  угроз; ломает stdlib `sqlite3`).

## Сообщить об уязвимости

- Откройте issue в GitHub (без публичного PoC: напишите «есть уязвимость, нужен приватный канал»),
  либо свяжитесь с автором напрямую. Исправление — до раскрытия деталей.
- Поддерживается только текущая версия `main`; фиксы выходят обычными коммитами.
