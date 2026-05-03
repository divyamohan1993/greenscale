"""Time-varying grid carbon intensity model.

ci(r, t) = mean(r) * (1 + amp(r) * sin(2*pi*(local_hour - phase) / 24)) + noise
The minimum is at `phase_hour` UTC (solar peak local time for that longitude).
Noise is deterministic per (region, minute) so frontend & decision log agree.
"""
from __future__ import annotations
import math
import hashlib
import time
from datetime import datetime, timezone

from .regions import Region, REGIONS_BY_CODE


def _det_noise(region: str, minute_epoch: int, scale: float) -> float:
    h = hashlib.md5(f"{region}:{minute_epoch}".encode()).digest()
    n = int.from_bytes(h[:4], "big") / 2**32  # [0,1)
    return (n - 0.5) * 2 * scale  # [-scale, +scale]


def carbon_intensity(region_code: str, t: float | None = None) -> float:
    r = REGIONS_BY_CODE[region_code]
    t = t if t is not None else time.time()
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    hour = dt.hour + dt.minute / 60.0
    # sine has minimum at hour == phase_hour
    phase = (hour - r.phase_hour) * 2 * math.pi / 24.0
    diurnal = -math.cos(phase)  # = -1 at hour=phase, +1 at hour=phase+12
    base = r.mean_ci * (1.0 + r.amp * diurnal)
    minute_epoch = int(t // 60)
    base += _det_noise(region_code, minute_epoch, scale=r.mean_ci * 0.05)
    return max(20.0, base)


def carbon_for_all(t: float | None = None) -> dict[str, float]:
    return {r.code: carbon_intensity(r.code, t) for r in REGIONS_BY_CODE.values()}
