from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from helpers import clean_state

ROOT = Path(__file__).resolve().parents[2]
DB_PATH: Path | None = None
TAXONOMY_PATH: Path | None = None
TAXONOMY_ORIGINAL: str | None = None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Отдельный uvicorn на tmp-порту + временные БД и taxonomy (прод-NSSM не трогаем)."""
    global DB_PATH, TAXONOMY_PATH, TAXONOMY_ORIGINAL
    port = _free_port()
    DB_PATH = tmp_path_factory.mktemp("e2e") / "spend.db"
    TAXONOMY_PATH = tmp_path_factory.mktemp("e2e-tax") / "taxonomy.toml"
    TAXONOMY_ORIGINAL = (ROOT / "config" / "taxonomy.toml").read_text(encoding="utf-8")
    TAXONOMY_PATH.write_text(TAXONOMY_ORIGINAL, encoding="utf-8")
    env = {**os.environ, "SPENDTRACK_DB_PATH": str(DB_PATH),
           "SPENDTRACK_TAXONOMY": str(TAXONOMY_PATH), "PYTHONUNBUFFERED": "1"}
    # S6 (адъюдикация 29.09): логи uvicorn — в файлы, а не в DEVNULL: 500-ка сервера должна быть
    # отличима от «селектор не появился» (хвост stderr печатается при Traceback)
    log_dir = tmp_path_factory.mktemp("e2e-logs")
    # файловые handle'ы живут, пока живёт серверный процесс (закрываются в финализаторе)
    stdout_log = open(log_dir / "uvicorn.out.log", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    stderr_log = open(log_dir / "uvicorn.err.log", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "spendtrack.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=stdout_log, stderr=stderr_log,
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
        stdout_log.close()
        stderr_log.close()
        err_text = (log_dir / "uvicorn.err.log").read_text(encoding="utf-8", errors="replace")
        pytest.fail(f"server did not start; uvicorn stderr (хвост):\n{err_text[-2000:]}")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    stdout_log.close()
    stderr_log.close()
    err_text = (log_dir / "uvicorn.err.log").read_text(encoding="utf-8", errors="replace")
    if "Traceback" in err_text:
        print(f"\n[e2e] uvicorn stderr (хвост; логи: {log_dir}):\n{err_text[-4000:]}")


@pytest.fixture()
def db_path(live_server) -> Path:
    """Путь к БД текущего e2e-сервера (для прямого засева данных)."""
    assert DB_PATH is not None, "live_server не запущен"
    return DB_PATH


@pytest.fixture()
def taxonomy_path(live_server) -> Path:
    """Путь к временной taxonomy.toml e2e-сервера (прод-конфиг не трогаем)."""
    assert TAXONOMY_PATH is not None, "live_server не запущен"
    return TAXONOMY_PATH


@pytest.fixture(autouse=True)
def clean_db():
    """Каждый тест стартует с пустой БД и исходной taxonomy (независимость сценариев)."""
    yield
    if DB_PATH is not None and DB_PATH.exists():
        clean_state(DB_PATH)
    if TAXONOMY_PATH is not None and TAXONOMY_ORIGINAL is not None:
        TAXONOMY_PATH.write_text(TAXONOMY_ORIGINAL, encoding="utf-8")