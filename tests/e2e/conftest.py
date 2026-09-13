from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB_PATH: Path | None = None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Отдельный uvicorn на tmp-порту + временная БД (прод-NSSM не трогаем)."""
    global DB_PATH
    port = _free_port()
    DB_PATH = tmp_path_factory.mktemp("e2e") / "spend.db"
    env = {**os.environ, "SPENDTRACK_DB_PATH": str(DB_PATH), "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "spendtrack.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=0.5)
            break
        except Exception:  # noqa: BLE001 — сервер ещё поднимается
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("server did not start")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def db_path(live_server) -> Path:
    """Путь к БД текущего e2e-сервера (для прямого засева данных)."""
    assert DB_PATH is not None, "live_server не запущен"
    return DB_PATH


@pytest.fixture(autouse=True)
def clean_db():
    """Каждый тест стартует с пустой БД (независимость сценариев)."""
    yield
    if DB_PATH is not None and DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        con.execute("DELETE FROM transactions")
        con.execute("DELETE FROM merchant_cache")
        con.commit()
        con.close()