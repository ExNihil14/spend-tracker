from __future__ import annotations

import json

from spendtrack import cli


def test_serve_wires_uvicorn(monkeypatch, capsys):
    import uvicorn

    calls: dict = {}

    def fake_run(app, **kwargs):
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    code = cli.main(["serve", "--port", "8123"])
    assert code == 0
    assert calls["app"] == "spendtrack.main:app"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8123
    assert calls["log_config"] is None
    assert "8123" in capsys.readouterr().out


def test_serve_port_from_settings(monkeypatch):
    import uvicorn

    calls: dict = {}
    monkeypatch.delenv("SPENDTRACK_PORT", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw))
    assert cli.main(["serve"]) == 0
    assert calls["port"] == 8766  # port из config/settings.toml


def test_serve_custom_host_display(monkeypatch, capsys):
    import uvicorn

    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw))
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8124"]) == 0
    assert calls["host"] == "0.0.0.0"
    out = capsys.readouterr().out
    assert "127.0.0.1:8124" in out  # в консоли — кликабельный локальный адрес


def test_serve_reports_unwritable_config(monkeypatch, capsys):
    from spendtrack import config

    def boom() -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(config, "ensure_config_dir", boom)
    assert cli.main(["serve", "--port", "8125"]) == 1
    err = capsys.readouterr().err
    assert "каталог конфига" in err
    assert "SPENDTRACK_CONFIG_DIR" in err


def test_paths_json(capsys):
    assert cli.main(["paths", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert set(info) == {"mode", "package", "config_dir", "data_dir", "db_path"}
    assert info["mode"] in {"repo", "installed"}


def test_paths_text(capsys):
    assert cli.main(["paths"]) == 0
    out = capsys.readouterr().out
    assert "режим" in out and "БД" in out
