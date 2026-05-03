"""Cold-start probability model.

Each region holds a last-hit timestamp. Probability that a request would
hit a cold container is modeled as 1 - exp(-dt / TAU) where TAU is the
empirical Cloud Run keep-alive half-life band (~5 min).
A successful route resets the per-region clock.
"""
from __future__ import annotations
import math
import threading
import time

TAU_SEC = 300.0  # ~5 min keep-alive

_last_hit: dict[str, float] = {}
_lock = threading.Lock()


def seed(region_codes: list[str]) -> None:
    now = time.time()
    with _lock:
        # seed all regions as if last hit was 10 min ago - so all start "cold-ish"
        for c in region_codes:
            _last_hit.setdefault(c, now - 600.0)


def cold_prob(region_code: str, t: float | None = None) -> float:
    t = t if t is not None else time.time()
    last = _last_hit.get(region_code, 0.0)
    dt = max(0.0, t - last)
    return 1.0 - math.exp(-dt / TAU_SEC)


def mark_hit(region_code: str, t: float | None = None) -> None:
    t = t if t is not None else time.time()
    with _lock:
        _last_hit[region_code] = t


def cold_for_all(t: float | None = None) -> dict[str, float]:
    return {c: cold_prob(c, t) for c in _last_hit.keys()}


def last_hits() -> dict[str, float]:
    return dict(_last_hit)
