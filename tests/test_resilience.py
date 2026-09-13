from __future__ import annotations

import time

from spendtrack.resilience import CircuitBreaker


def test_opens_after_threshold():
    br = CircuitBreaker("t", fail_threshold=3, recovery_s=60)
    for _ in range(3):
        br.report_failure()
    assert br.allowed() is False


def test_half_open_single_probe_then_recovery():
    br = CircuitBreaker("t", fail_threshold=1, recovery_s=0.05)
    br.report_failure()
    assert br.allowed() is False
    time.sleep(0.06)
    assert br.allowed() is True  # half-open: проба разрешена (одна)
    assert br.allowed() is False  # остальные мгновенно отклонены
    br.report_success()
    assert br.allowed() is True  # сброс в closed


def test_success_resets_fail_count():
    br = CircuitBreaker("t", fail_threshold=3, recovery_s=60)
    br.report_failure()
    br.report_failure()
    br.report_success()
    br.report_failure()
    assert br.allowed() is True  # счётчик обнулён, порога не достиг


def test_closed_always_allowed():
    br = CircuitBreaker("t")
    assert br.allowed() is True
    br.report_success()
    assert br.allowed() is True