"""Структурные проверки лендинга (landing/) — оффлайн, без сети.

Лендинг статический (GitHub Pages): проверяем, что он не тянет внешние ресурсы,
что все локальные ссылки/ассеты существуют, что механики запуска (демо-кнопка,
почта, опрос, поддержка) на месте и что workflow деплоя не потерян.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"
ISSUE_TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
EXTERNAL_PREFIXES = ("http://", "https://", "//")
SKIP_PREFIXES = ("#", "mailto:", "data:", *EXTERNAL_PREFIXES)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.local_refs: list[str] = []
        self.anchor_refs: list[str] = []
        self.external_resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            href = a["href"]
            self.links.append(href)
            if href.startswith("#"):
                self.anchor_refs.append(href[1:])
            elif not href.startswith(SKIP_PREFIXES):
                self.local_refs.append(href)
        if tag in {"img", "script", "iframe", "link"}:
            ref = a.get("src") or a.get("href")
            if not ref:
                return
            if ref.startswith(EXTERNAL_PREFIXES):
                self.external_resources.append(ref)
            elif not ref.startswith(SKIP_PREFIXES):
                self.local_refs.append(ref)


def _parse_index() -> tuple[str, _Collector]:
    html = (LANDING / "index.html").read_text(encoding="utf-8")
    collector = _Collector()
    collector.feed(html)
    return html, collector


def test_landing_files_exist() -> None:
    assert (LANDING / "index.html").is_file()
    assert (LANDING / "style.css").is_file()
    for name in ("shot-dashboard.png", "shot-digest.png", "shot-approve.png"):
        assert (LANDING / "assets" / name).is_file(), name


def test_no_external_resources() -> None:
    _, collector = _parse_index()
    assert collector.external_resources == []


def test_local_references_resolve() -> None:
    _, collector = _parse_index()
    missing = [ref for ref in collector.local_refs if not (LANDING / ref.split("?")[0]).exists()]
    assert missing == []
    broken_anchors = [ref for ref in collector.anchor_refs if ref not in collector.ids]
    assert broken_anchors == []


def test_required_sections_and_mechanics() -> None:
    html, collector = _parse_index()
    for anchor in ("demo", "install", "support", "features", "privacy"):
        assert anchor in collector.ids, anchor
    assert "https://codespaces.new/ExNihil14/spend-tracker" in collector.links
    assert any(link.startswith("mailto:") for link in collector.links)
    assert "Разовая поддержка — скоро" in html  # лист ожидания до Boosty/URL; живой заглушки нет
    raw = "https://raw.githubusercontent.com/ExNihil14/spend-tracker/main/"
    assert raw + "install.ps1" in html and raw + "install.sh" in html


def test_poll_and_support_issue_templates_linked_and_present() -> None:
    _, collector = _parse_index()
    templates = {"poll-pwa.yml", "poll-telegram.yml", "supporter.yml", "bug-report.yml"}
    linked = {
        name
        for name in templates
        if any(f"template={name}" in link for link in collector.links)
    }
    assert linked == templates
    for name in templates:
        assert (ISSUE_TEMPLATES / name).is_file(), name


def test_pages_workflow_deploys_landing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "path: landing" in workflow
    assert "pages: write" in workflow
    assert "actions/deploy-pages" in workflow
    assert "workflow_dispatch" in workflow


def test_no_misleading_supporter_claims() -> None:
    """Гигиена публичных текстов (ревью 21.09 + ре-ревью Opus-5.5 23.09): без managed-прокси и «разовой
    лицензии», честные оговорки про CSV Сбера и состав данных для LLM, без живой Boosty-заглушки и
    донат-перков; проверяем и README/issue-форму, чтобы дрейф не повторился."""
    html, _ = _parse_index()
    lowered = html.lower()
    assert "managed-llm" not in lowered
    assert "разовая лицензия" not in lowered
    assert "разовая поддержка" in lowered
    assert "xls-импорт в планах" in lowered
    assert "boosty.to" not in lowered  # нет живой ссылки-заглушки (REPLACE_ME)
    assert "доступ к заметкам" not in lowered  # донат без перков
    assert "по умолчанию данные не покидают" in lowered  # без безусловного «данные не покидают»
    assert "псевдоним счёта" in lowered  # карточка «Что уходит к LLM» не занижает состав данных

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "managed-llm" not in readme
    assert "разовая лицензия" not in readme
    assert "xls-импорт" in readme

    supporter = (ISSUE_TEMPLATES / "supporter.yml").read_text(encoding="utf-8").lower()
    assert "managed" not in supporter
    assert "лицензи" not in supporter


def test_tokens_copy_in_sync() -> None:
    """Общий tokens.css (дизайн-ревью M-1): копия для лендинга обязана совпадать с пакетной."""
    def norm(path: Path) -> str:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")

    src = norm(ROOT / "src" / "spendtrack" / "tokens.css")
    landing = norm(LANDING / "tokens.css")
    assert src == landing


def test_funding_has_no_live_placeholder() -> None:
    """До запуска кнопка Sponsor не должна вести на несуществующий URL (риск захвата ника)."""
    funding = (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8")
    active = [line.strip() for line in funding.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert not any(line.startswith("custom:") for line in active)
    assert all("boosty.to" not in line for line in active)
