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
    assert any("boosty.to" in link for link in collector.links)
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


def test_funding_points_to_boosty() -> None:
    funding = (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8")
    assert "boosty.to" in funding
