"""Статические ресурсы приложения (favicon, prebuilt CSS) — оффлайн, без сети."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "spendtrack" / "static"
BASE = ROOT / "src" / "spendtrack" / "templates" / "base.html"


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "assets.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_favicon_file_and_link(tmp_path, monkeypatch) -> None:
    """favicon.svg лежит в static и подключён в base.html (иначе браузер даёт 404)."""
    assert (STATIC / "favicon.svg").is_file()
    base = BASE.read_text(encoding="utf-8")
    assert "static('favicon.svg')" in base  # версионированный URL через Jinja-хелпер
    with _client(tmp_path, monkeypatch) as client:
        assert "/static/favicon.svg?v=" in client.get("/").text


def test_favicon_served(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "fav.db"))
    from spendtrack.main import app

    with TestClient(app) as client:
        r = client.get("/static/favicon.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")


def test_prebuilt_css_present_and_linked(tmp_path, monkeypatch) -> None:
    """Prebuilt CSS (Tailwind standalone, без Node): артефакт есть, подключён, browser build не используется."""
    css_path = STATIC / "app.css"
    assert css_path.is_file(), "app.css не собран: uv run python scripts/build_css.py"
    css = css_path.read_text(encoding="utf-8")
    assert len(css) > 10_000
    # Семантические маркеры: базовые утилиты, адаптивность (медиа-запрос sm-брейкпоинта), скролл/перенос.
    for needle in (".bg-slate-950", ".text-slate-200", "@media (min-width:40rem)",
                   ".overflow-x-auto", ".flex-wrap"):
        assert needle in css, needle
    with _client(tmp_path, monkeypatch) as client:
        html = client.get("/").text
    assert "/static/app.css?v=" in html  # версионированный URL (immutable-кэш)
    assert "/static/app.js?v=" in html
    assert "tailwind.js" not in html, "browser build не должен подключаться в проде"
    assert "chart.umd" not in html, "Chart.js грузится только на дашборде (dashboard.js)"


def test_prebuilt_css_served(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "css.db"))
    from spendtrack.main import app

    with TestClient(app) as client:
        r = client.get("/static/app.css")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/css")
        assert ".bg-slate-950" in r.text
