"""Матчер правил: границы слова, стем-шаблоны `*`, ё-нормализация.

Класс ошибок (бэклог «матчер»): подстрочный поиск ловил бренды внутри чужих слов —
«ГИПЕРМЕТРО» → transport (МЕТРО), «ПЕРЕВОДЧИК» → transfers (ПЕРЕВОД), «ВБЛИЗИ» → household (ВБ).
Правило = слово целиком; `*` — явный шаблон (префикс/суффикс/подстрока), чтобы стемы
вроде «ЗАРАБОТН» оставались выразимыми без магии.
"""
from __future__ import annotations

import pytest

from spendtrack.categorize import categorize_rules_only
from spendtrack.store import Store
from spendtrack.taxonomy import Rule, load_taxonomy


@pytest.fixture()
def cat(tmp_path):
    taxonomy = load_taxonomy()

    def classify(description: str) -> str | None:
        store = Store(db_path=tmp_path / "boundaries.db")
        try:
            return categorize_rules_only(
                {"description": description, "merchant": description}, taxonomy, store)
        finally:
            store.close()

    return classify


# ── Реальный класс ошибок: бренд внутри чужого слова не должен срабатывать ──
@pytest.mark.parametrize("description", [
    "ГИПЕРМЕТРО 12",            # МЕТРО — не транспорт
    "ПЕРЕВОДЧИК ИВАНОВ",        # ПЕРЕВОД — не перевод средств
    "МАГНИТНЫЙ ДЕРЖАТЕЛЬ",      # МАГНИТ — не продукты
    "ВБЛИЗИ ДОМА",              # ВБ — не Wildberries
    "АПТЕКА 36.6",              # нет правила — остаётся для LLM
    "КНИЖНЫЙ МАГАЗИН",
])
def test_brand_inside_word_is_not_a_match(cat, description):
    assert cat(description) is None


# ── Регрессия: реальные описания из golden-набора продолжают совпадать ──
@pytest.mark.parametrize("description,expected", [
    ("ООО ЛЕНТА 1234", "groceries"),
    ("ЛЕНТА СУПЕРМАРКЕТ МОСКВА", "groceries"),
    ("лента супермаркет", "groceries"),
    ("МАГНИТ У ДОМА 77", "groceries"),
    ("ПЯТЁРОЧКА 8172", "groceries"),
    ("ПЯТЕРОЧКА-12", "groceries"),
    ("ВКУС ВИЛЛ МОСКВА", "groceries"),
    ("АЗС ЛУКОЙЛ 22", "fuel"),
    ("GAZPROMNEFT AZS 12", "fuel"),
    ("ЯНДЕКС GO TRIP", "transport"),
    ("UBER *TRIP", "transport"),
    ("МЕТРО ТУРНИКЕТ", "transport"),
    ("TRANSFER TO CARD 1234", "transfers"),
    ("ПЕРЕВОД НА КАРТУ", "transfers"),
    ("ВОЗВРАТ ПОКУПКИ", "transfers"),
    ("ЗАРАБОТНАЯ ПЛАТА ОКТЯБРЬ", "income"),
    ("ЗАРПЛАТА", "income"),
    ("SALARY PAYMENT", "income"),
    ("NETFLIX.COM", "subscriptions"),
    ("ИВИ.RU", "subscriptions"),
    ("ОЗОН 123", "household"),
    ("ВБ МАРКЕТ", "household"),
    ("WILDBERRIES", "household"),
])
def test_real_descriptions_keep_matching(cat, description, expected):
    assert cat(description) == expected


# ── Явные шаблоны: `*` — единственный способ разрешить частичное совпадение ──
def test_wildcard_semantics():
    assert Rule("ТЕСТ", "other").matches("ТЕСТ 123") is True
    assert Rule("ТЕСТ", "other").matches("ТЕСТОВЫЙ ПЛАТЁЖ") is False
    assert Rule("ТЕСТ*", "other").matches("ТЕСТОВЫЙ ПЛАТЁЖ") is True
    assert Rule("*ТЕСТ", "other").matches("ЛОТЕСТ") is True
    assert Rule("*ТЕСТ*", "other").matches("ПРОТЕСТ") is True
    assert Rule("ТЕСТ*", "other").matches("ЛОТЕСТ") is False


# ── Стем «ЗАРАБОТН*» покрывает падежи, но не «заработал» ──
def test_stem_covers_inflections(cat):
    assert cat("ЗАРАБОТНОЙ ПЛАТЫ ЗА СЕНТЯБРЬ") == "income"
    assert cat("ЗАРАБОТОК НА КУРСЕ") is None


# ── ё/е: банки пишут по-разному ──
@pytest.mark.parametrize("description", ["ПЯТЕРОЧКА 8172", "ПЯТЁРОЧКА 8172"])
def test_yo_normalization(cat, description):
    assert cat(description) == "groceries"


def test_yo_normalization_in_rule():
    assert Rule("ПЯТЁРОЧКА", "groceries").matches("ПЯТЕРОЧКА") is True
    assert Rule("ПЯТЕРОЧКА", "groceries").matches("ПЯТЁРОЧКА") is True
