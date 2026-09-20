"""Статические ресурсы приложения (favicon) — оффлайн, без сети."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "src" / "spendtrack" / "static"


def test_favicon_file_and_link() -> None:
    """favicon.svg лежит в static и подключён в base.html (иначе браузер даёт 404)."""
    assert (STATIC / "favicon.svg").is_file()
    base = (Path(__file__).resolve().parents[1] / "src" / "spendtrack" / "templates"
            / "base.html").read_text(encoding="utf-8")
    assert '/static/favicon.svg' in base


def test_favicon_served(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "fav.db"))
    from spendtrack.main import app

    with TestClient(app) as client:
        r = client.get("/static/favicon.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
