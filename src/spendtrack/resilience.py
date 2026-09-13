from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("spendtrack")


class CircuitBreaker:
    """closed → open (N фейлов подряд) → half-open (через recovery_s — 1 проба).

    In-memory: solo-сервис, один процесс; после рестарта breaker прогревается
    за fail_threshold×timeout. Персистентность не нужна (1 импорт/день).
    """

    def __init__(self, name: str, fail_threshold: int = 3, recovery_s: float = 1800.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.recovery_s = recovery_s
        self._fails = 0
        self._state = "closed"
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allowed(self) -> bool:
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open" and time.monotonic() - self._opened_at >= self.recovery_s:
                self._state = "half-open"  # ровно одна пробная попытка
                return True
            return False  # open или half-open (кто-то уже пробует)

    def report_success(self) -> None:
        with self._lock:
            self._fails = 0
            self._state = "closed"

    def report_failure(self) -> None:
        with self._lock:
            self._fails += 1
            if self._state == "half-open" or self._fails >= self.fail_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                log.warning("llm[%s]: circuit OPEN (на %.0f мин)", self.name, self.recovery_s / 60)