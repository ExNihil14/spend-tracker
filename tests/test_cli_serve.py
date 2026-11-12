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
    monkeypatch.setenv("SPENDTRACK_ALLOW_INSECURE_LAN", "1")
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw))
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8124"]) == 0
    assert calls["host"] == "0.0.0.0"
    out = capsys.readouterr().out
    assert "127.0.0.1:8124" in out  # в консоли — кликабельный локальный адрес


def test_serve_refuses_insecure_lan_without_explicit_optin(monkeypatch, capsys):
    """LAN HTTP без TLS не включаем случайно: нужен явный SPENDTRACK_ALLOW_INSECURE_LAN=1."""
    import uvicorn

    monkeypatch.delenv("SPENDTRACK_ALLOW_INSECURE_LAN", raising=False)

    def fail(*_args, **_kwargs):
        raise AssertionError("uvicorn must not run")

    monkeypatch.setattr(uvicorn, "run", fail)
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8124"]) == 2
    err = capsys.readouterr().err
    assert "LAN HTTP выключен" in err


def test_serve_reports_unwritable_config(monkeypatch, capsys):
    from spendtrack import config

    def boom() -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(config, "ensure_config_dir", boom)
    assert cli.main(["serve", "--port", "8125"]) == 1
    err = capsys.readouterr().err
    assert "каталог конфига" in err
    assert "SPENDTRACK_CONFIG_DIR" in err


def test_serve_broken_settings_friendly_error(tmp_path, monkeypatch, capsys):
    """W1 ресёрча ошибок: `serve` с битым settings.toml — понятная ошибка rc=1, не трейсбек."""
    monkeypatch.setenv("SPENDTRACK_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("SPENDTRACK_BASE_CURRENCY", raising=False)  # env маскирует поломку TOML
    (tmp_path / "settings.toml").write_text('base_currency = "RUBL"\n', encoding="utf-8")
    assert cli.main(["serve"]) == 1
    err = capsys.readouterr().err
    assert "настройки не читаются" in err and "Traceback" not in err


def test_capture_serve_wraps_app_and_uses_loopback(monkeypatch, capsys):
    import uvicorn

    from spendtrack.capture_gateway import CaptureOnlyApp

    monkeypatch.setenv("SPENDTRACK_CAPTURE_TOKEN", "test-capture-token")
    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    assert cli.main(["capture-serve", "--port", "8767"]) == 0
    assert isinstance(calls["app"], CaptureOnlyApp)
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8767
    assert calls["log_config"] is None
    assert "/capture" in capsys.readouterr().out


def test_capture_serve_reads_token_file(monkeypatch, tmp_path, capsys):
    import os

    import uvicorn

    from spendtrack.capture_gateway import CaptureOnlyApp

    token_file = tmp_path / "capture-token.txt"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_CAPTURE_TOKEN", "")
    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    assert cli.main([
        "capture-serve", "--port", "8767", "--token-file", str(token_file),
    ]) == 0
    assert isinstance(calls["app"], CaptureOnlyApp)
    assert os.environ["SPENDTRACK_CAPTURE_TOKEN"] == "file-token"
    assert "/capture" in capsys.readouterr().out


def test_capture_serve_refuses_without_token(monkeypatch, capsys):
    import uvicorn

    monkeypatch.delenv("SPENDTRACK_CAPTURE_TOKEN", raising=False)

    def fail(*_args, **_kwargs):
        raise AssertionError("uvicorn must not run without a capture token")

    monkeypatch.setattr(uvicorn, "run", fail)
    assert cli.main(["capture-serve", "--port", "8767"]) == 2
    assert "SPENDTRACK_CAPTURE_TOKEN" in capsys.readouterr().err


def test_capture_serve_refuses_non_utf8_token_file(monkeypatch, tmp_path, capsys):
    import uvicorn

    token_file = tmp_path / "capture-token.txt"
    token_file.write_bytes(b"\xff")
    monkeypatch.delenv("SPENDTRACK_CAPTURE_TOKEN", raising=False)

    def fail(*_args, **_kwargs):
        raise AssertionError("uvicorn must not run with an unreadable token file")

    monkeypatch.setattr(uvicorn, "run", fail)
    assert cli.main([
        "capture-serve", "--port", "8767", "--token-file", str(token_file),
    ]) == 2
    assert "token file" in capsys.readouterr().err


def test_paths_json(capsys):
    assert cli.main(["paths", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert set(info) == {"mode", "package", "config_dir", "data_dir", "db_path"}
    assert info["mode"] in {"repo", "installed"}


def test_paths_text(capsys):
    assert cli.main(["paths"]) == 0
    out = capsys.readouterr().out
    assert "режим" in out and "БД" in out
