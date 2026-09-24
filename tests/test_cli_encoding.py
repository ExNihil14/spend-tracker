from __future__ import annotations

import sys

from spendtrack.console import utf8_stdout as _utf8_stdout


class _FakeStream:
    def __init__(self, encoding=None):
        self.reconfigured: dict | None = None
        if encoding is not None:
            self.encoding = encoding

    def reconfigure(self, **kw):
        self.reconfigured = kw
        self.encoding = kw["encoding"]


def test_utf8_stdout_reconfigures_non_utf8(monkeypatch):
    """Git Bash/пайп на RU-Windows: cp1251 → UTF-8 (кириллица + «≠» не роняют печать)."""
    fake = _FakeStream("cp1251")
    monkeypatch.setattr(sys, "stdout", fake)

    _utf8_stdout()

    assert fake.encoding == "utf-8"
    assert fake.reconfigured == {"encoding": "utf-8", "errors": "replace"}


def test_utf8_stdout_noop_on_utf8(monkeypatch):
    """Реальная консоль (PEP 528) и pytest-capture уже UTF-8 — не трогаем поток."""
    fake = _FakeStream("UTF-8")
    monkeypatch.setattr(sys, "stdout", fake)

    _utf8_stdout()

    assert fake.reconfigured is None


def test_utf8_stdout_reconfigures_when_encoding_unknown(monkeypatch):
    """Поток без атрибута encoding — переключаемся на UTF-8 best-effort."""
    fake = _FakeStream()
    monkeypatch.setattr(sys, "stdout", fake)

    _utf8_stdout()

    assert fake.encoding == "utf-8"


def test_utf8_stdout_reconfigures_stderr_too(monkeypatch):
    """Предупреждения CLI идут в stderr — он переключается вместе со stdout (K2)."""
    out, err = _FakeStream("UTF-8"), _FakeStream("cp1251")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    _utf8_stdout()

    assert out.reconfigured is None
    assert err.reconfigured == {"encoding": "utf-8", "errors": "replace"}
