"""Проверки шаблонов сервисов (deploy/) и README-раздела об автозапуске — оффлайн, без сети.

Шаблоны запускаются ОС вне Python, поэтому тесты структурные: юнит systemd и plist
parse-ятся/содержат ключевые поля, README ссылается на шаблоны и описывает все три ОС,
в шаблонах нет незаменённых заглушек и секретов.
"""
from __future__ import annotations

import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
SYSTEMD = DEPLOY / "spendtrack.service"
PLIST = DEPLOY / "com.spendtrack.serve.plist"


def test_systemd_unit_structure() -> None:
    text = SYSTEMD.read_text(encoding="utf-8")
    assert "[Service]" in text and "[Install]" in text
    assert "ExecStart=%h/.local/bin/spendtrack serve" in text
    assert "WantedBy=default.target" in text
    assert "Restart=on-failure" in text


def test_plist_is_valid_xml_and_launches_spendtrack() -> None:
    data = plistlib.loads(PLIST.read_bytes())
    assert data["Label"] == "com.spendtrack.serve"
    args = " ".join(data["ProgramArguments"])
    assert "spendtrack" in args and args.endswith("serve")
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] is True
    assert data["StandardOutPath"].startswith("/")


def test_templates_have_no_placeholders_or_secrets() -> None:
    for path in (SYSTEMD, PLIST):
        text = path.read_text(encoding="utf-8")
        for placeholder in ("REPLACE_ME", "CHANGE_ME", "YOUR_", "TODO"):
            assert placeholder not in text
        assert "sk-" not in text
        assert "api_key" not in text.lower()


def test_readme_documents_all_platforms_and_templates() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in (
        "Работа в фоне",
        "nssm install spendtrack",
        "Планировщик заданий",
        "launchctl bootstrap",
        "systemctl --user enable --now spendtrack",
        "deploy/com.spendtrack.serve.plist",
        "deploy/spendtrack.service",
    ):
        assert needle in readme, needle
