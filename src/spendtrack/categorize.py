from __future__ import annotations

import hashlib
import logging
import math

from spendtrack.config import load_settings
from spendtrack.llm import call_llm, parse_llm_json
from spendtrack.prompts import build_system_prompt, build_user_prompt
from spendtrack.store import Store
from spendtrack.taxonomy import Taxonomy

logger = logging.getLogger(__name__)


def _clamp_confidence(value: object) -> float:
    """Мусор (bool/NaN/inf/вне [0,1]) → 0.0.

    S12 (ревью 28.09): значение вне диапазона — признак сломанного вывода, а не уверенность;
    `json.loads` принимает `1e400`/`Infinity`, а `float(True) == 1.0` — авто-приём на таком
    значении запрещён.
    """
    if isinstance(value, bool):
        return 0.0
    try:
        conf = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):  # OverflowError: float(10**400) (Astra 01.10, C1)
        return 0.0
    if not math.isfinite(conf) or not 0.0 <= conf <= 1.0:
        return 0.0
    return conf


def categorize_rules_only(tx: dict, taxonomy: Taxonomy, store: Store) -> str | None:
    """Step 1: merchant cache → keyword rules. Возвращает category или None."""
    merchant = (tx.get("merchant") or tx["description"]).upper().strip()
    amount = tx.get("amount_kopecks") or 0
    cached = store.merchant_cache_get(merchant)
    # C2 (Astra 01.10): кэш не должен обходить проверку знака — «income» не берём для расходной
    # операции. Ноль/неизвестная сумма не отсекаются (направление неизвестно — решает LLM/очередь).
    if cached and taxonomy.is_valid(cached) and not (cached == "income" and amount < 0):
        return cached

    # S7 (ревью 28.09): правила ищут и в merchant — банки кладут имя ТСП в отдельное поле
    haystack = f"{tx['description']} {tx.get('merchant') or ''}".upper()
    for rule in taxonomy.rules:
        if rule.pattern in haystack and taxonomy.is_valid(rule.category):
            if rule.category == "income" and amount < 0:
                # S6: доход на расходной операции — правило не применяем, решает LLM/очередь
                continue
            return rule.category
    return None


def categorize_llm(tx: dict, store: Store, taxonomy: Taxonomy) -> dict:
    """Step 2: LLM-классификация. Возвращает {'category', 'confidence', 'merchant', 'reason', 'source'}."""
    examples = store.list_examples()
    system_prompt = build_system_prompt(examples, taxonomy)
    user_prompt = build_user_prompt(tx)

    llm_result = call_llm(system_prompt, user_prompt, max_tokens=400)
    parsed = parse_llm_json(llm_result["content"])

    # C1 (Astra 01.10): поля ответа LLM проверяем по типам — иначе список/dict в category роняет
    # классификацию (TypeError в is_valid), а гигантская confidence — OverflowError в float().
    category = parsed.get("category") if isinstance(parsed, dict) else None
    if not isinstance(category, str) or not taxonomy.is_valid(category):
        return {"category": "other", "confidence": 0.0, "merchant": tx.get("merchant"),
                "reason": "llm_parse_failed", "source": "llm"}

    confidence = _clamp_confidence(parsed.get("confidence", 0.0))
    merchant_raw = parsed.get("merchant")
    merchant_norm = (merchant_raw.upper().strip() if isinstance(merchant_raw, str) else "") \
        or tx.get("merchant")
    reason_raw = parsed.get("reason")
    return {
        "category": category,
        "confidence": confidence,
        "merchant": merchant_norm,
        "reason": reason_raw if isinstance(reason_raw, str) else "",
        "source": "llm",
    }


def classify_with_injectable(
    tx: dict, taxonomy: Taxonomy, store: Store, llm_getter, acceptance: float,
    commit: bool = True,
) -> dict:
    """Тестируемая версия: llm_getter — функция (tx, store, taxonomy) -> dict.

    Возвращает dict с category/source/confidence/merchant/category_llm/review_status,
    где источник rule|llm|llm_pending_review. `commit=False` — внутри батча импорта
    (запись в кэш мерчанта коммитится вместе с партией, а не посередине).
    """
    rule_result = categorize_rules_only(tx, taxonomy, store)
    if rule_result:
        return {"category": rule_result, "confidence": 1.0, "merchant": tx.get("merchant"),
                "reason": "keyword_rule", "source": "rule",
                "category_llm": None, "review_status": "approved"}

    llm_result = llm_getter(tx, store, taxonomy)
    conf = _clamp_confidence(llm_result.get("confidence", 0.0))
    llm_result["confidence"] = conf
    cat = llm_result.get("category", "")
    bucket = f"{int(conf * 10) / 10:.1f}"
    desc = tx.get("description", "")
    # S8: в INFO — только хэш описания (сырое описание уезжает в issue/поддержку); полный текст — DEBUG
    logger.info("llm_decision: conf=%.3f bucket=%s accepted=%s desc_hash=%s",
                conf, bucket, conf >= acceptance, hashlib.sha1(desc.encode()).hexdigest()[:8])
    logger.debug("llm_decision desc=%s", desc[:40])
    if not taxonomy.is_valid(cat):
        # S4 (Astra 01.10): в очередь отдаём ИСХОДНЫЙ банковский merchant, а не нормализацию модели —
        # недоверенная догадка не должна подменять данные в pending-строке.
        llm_result["merchant"] = tx.get("merchant")
        llm_result.update({"category": "other", "confidence": 0.0, "source": "llm_pending_review",
                           "category_llm": cat or None, "review_status": "pending"})
        return llm_result
    if cat == "income" and (tx.get("amount_kopecks") or 0) < 0:
        # S6: доход возможен только для поступлений — гипотеза уходит в очередь, а не в боевые поля
        llm_result["merchant"] = tx.get("merchant")
        llm_result.update({"category": "other", "source": "llm_pending_review",
                           "category_llm": cat, "review_status": "pending",
                           "reason": "income_sign_mismatch"})
        return llm_result
    llm_result["category_llm"] = cat
    if conf >= acceptance:
        llm_result["source"] = "llm"
        llm_result["review_status"] = "approved"
        # C3 (Astra 01.10): авто-приём LLM больше НЕ обучает доверенный кэш мерчантов — иначе
        # одна ошибка модели превращалась в «правило» (confidence 1.0, source=rule) для всех
        # будущих операций. Кэш наполняет только явное подтверждение (Store.approve_review).
        return llm_result

    # C4: гипотеза при низкой уверенности живёт только в category_llm — дашборд не считает догадку фактом
    llm_result["merchant"] = tx.get("merchant")  # S4: исходный merchant, не догадка модели
    llm_result["source"] = "llm_pending_review"
    llm_result["review_status"] = "pending"
    llm_result["category"] = "other"
    return llm_result


def categorize_transaction(tx: dict, taxonomy: Taxonomy, store: Store, commit: bool = True) -> dict:
    """Полный пайплайн (боевой): rule → merchant-cache → LLM → validation → queue.

    `commit=False` — батч импорта: кэш мерчанта коммитится вместе с партией.
    """
    settings = load_settings()
    return classify_with_injectable(
        tx, taxonomy, store,
        lambda t, s, tax: categorize_llm(t, s, tax),
        settings.acceptance.auto_accept_confidence,
        commit=commit,
    )