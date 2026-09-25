---
name: bank-adapter
description: Маршрут «адаптер → фикстура → тест → golden» для банковских выписок spend-tracker: новый банк, синонимы шапки, порядок sniff, кодировки. Use when импорт не распознал выписку, добавляется банк или меняется парсинг CSV.
---

# Банковский адаптер

Один маршрут на любой случай: новая выписка, «не распознал банк», правка колонок. Шаг закрыт, когда зелёный его тест; маршрут закрыт, когда прошёл контур из `spec/PIPELINE.md` (`uv run pytest`, `uv run ruff check .`, `scripts/contract_delta.py check`, `scripts/build_css.py --check`).

## Шаги
1. **Форма.** Достань реальную шапку: сырьё — только `D:\data\finance\statements\<bank>\raw\` (immutable, в git и LLM не попадает); публично — обезличенный образец `spendtrack anonymize IN OUT --rows 0`. Синтетика — генераторы в `tests/synth_bank.py` (`gen_sber`, `gen_tinkoff_real`, …).
2. **Адаптер** в `src/spendtrack/csv_import.py`: класс с `parse(rows)`; колонки — `_cell(r, "Имя1", "Имя2")`; статусы («в обработке», «отклонено») → `{"_skip": "status"}`; битый ряд → `_skip` с причиной, без исключений. Синонимы колонок — `REQUIRED_COLUMNS`, реестр — `BANKS`, снеффинг — `sniff_bank`.
3. **Фикстура.** Добавь `gen_<bank>` в `tests/synth_bank.py`: детерминированный seed, форма — как у реальной выписки (лишние колонки, `;`, cp1251 при необходимости), а не «удобная».
4. **Тест.** `tests/test_csv_import.py` — happy-path и колонки; `tests/test_import_chaos.py` — мусор, кодировки, лимиты; отдельно проверь `sniff_bank` на реальной шапке банка.
5. **Golden.** Нужны ли новые мерчант-паттерны — дополни `tests/golden/merchants.csv`; прогони `scripts/golden_report.py` (read-only, отчёт в `reports/`, не коммитится).

## Gotchas (реальные выписки)
- **sniff: Т-Банк раньше Сбера.** Реальный Т-Банк (13 колонок) содержит «Дата операции»; его выдают `MCC`/`Кэшбэк`/`Бонусы` — они проверяются первыми, иначе выписка уходит в Sber.
- **Сумма — только копейки-INTEGER** (`_row_tx`); встречаются `-,01`, `U+2212`; `parse_amount("nan"/"inf")` → контролируемая `InvalidOperation`, не `ValueError`.
- **Дата:** `_iso_date` принимает слэши и точки; нераспознанное — `_skip`, никогда 500 (P0-регресс).
- **Байты, не text-mode:** utf-8-sig → cp1251-фолбэк, одиночный `\r` нормализуется; text-mode превращал CRLF в `\r\r\n`.
- **Сбер email-CSV:** расчётная сумма — «Сумма в валюте счета» (RUB); XLS/XLSX у физлиц не существует (CSV/PDF).
- **Дедуп:** fingerprint `sha1(date|amount|desc|account_anon|export_rowid)`; повторный импорт — no-op. Менять формулу — только по тикету с ревью.
- **Тесты оффлайн**, LLM — стаб; сырые выписки не коммитить.
