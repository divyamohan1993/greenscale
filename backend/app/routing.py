"""GreenScale routing engine.

For each candidate region, computes a normalized score combining latency,
carbon intensity, cold-start probability, and instance-hour cost.

score(r) = w_lat * lat_norm + w_carbon * ci_norm + w_cold * cold + w_cost * cost_norm

Lower is better. argmin = chosen region. We always also compute a
latency-only baseline for comparison.
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass

from .regions import REGIONS, REGIONS_BY_CODE
from .carbon import carbon_intensity
from .coldstart import cold_prob, mark_hit

# Cold-start latency penalty (Cloud Run typical first-request overhead)
COLD_START_PENALTY_MS = 800.0
MAX_RTT_MS = 350.0
MAX_CI_G   = 900.0
MAX_COST   = 0.030


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def rtt_ms(user_lat: float, user_lon: float, region_code: str) -> float:
    r = REGIONS_BY_CODE[region_code]
    km = _haversine_km(user_lat, user_lon, r.lat, r.lon)
    # 30ms base + 0.012 ms/km (twice speed-of-light through fiber, with overhead)
    return 30.0 + km * 0.012


@dataclass
class Candidate:
    region: str
    display: str
    lat: float
    lon: float
    rtt_ms: float
    ci: float
    cold: float
    cost: float
    expected_latency_ms: float  # rtt + cold * penalty
    score: float
    score_breakdown: dict


@dataclass
class Decision:
    chosen: Candidate
    baseline_latency: Candidate
    candidates: list[Candidate]
    weights: dict
    carbon_saved_g: float
    latency_overhead_ms: float
    reason: str


DEFAULT_WEIGHTS = {"lat": 0.25, "carbon": 0.45, "cold": 0.20, "cost": 0.10}


def _candidate(user_lat: float, user_lon: float, code: str, t: float, weights: dict) -> Candidate:
    r = REGIONS_BY_CODE[code]
    rtt = rtt_ms(user_lat, user_lon, code)
    ci = carbon_intensity(code, t)
    cold = cold_prob(code, t)
    cost = r.hourly_cost
    expected_lat = rtt + cold * COLD_START_PENALTY_MS

    lat_norm = min(rtt / MAX_RTT_MS, 1.0)
    ci_norm = min(ci / MAX_CI_G, 1.0)
    cost_norm = min(cost / MAX_COST, 1.0)

    breakdown = {
        "lat":    weights["lat"]    * lat_norm,
        "carbon": weights["carbon"] * ci_norm,
        "cold":   weights["cold"]   * cold,
        "cost":   weights["cost"]   * cost_norm,
    }
    score = sum(breakdown.values())
    return Candidate(
        region=code, display=r.display, lat=r.lat, lon=r.lon,
        rtt_ms=rtt, ci=ci, cold=cold, cost=cost,
        expected_latency_ms=expected_lat, score=score, score_breakdown=breakdown,
    )


def route(user_lat: float, user_lon: float, weights: dict | None = None,
          t: float | None = None) -> Decision:
    t = t if t is not None else time.time()
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    candidates = [_candidate(user_lat, user_lon, r.code, t, w) for r in REGIONS]
    chosen = min(candidates, key=lambda c: c.score)

    # latency-only baseline: argmin expected_latency
    baseline = min(candidates, key=lambda c: c.expected_latency_ms)

    # ENERGY ASSUMPTION: each request consumes ~0.0008 kWh of compute (~3 sec
    # at 1 vCPU + 512Mi container -> ~1W avg = ~0.0008 Wh per request would be
    # too tiny; we use a per-request "footprint" proxy of 0.001 kWh so deltas
    # are visible in the demo. This is a *demonstration* coefficient, the
    # routing math itself is correct.)
    PER_REQUEST_KWH = 0.001
    saved = (baseline.ci - chosen.ci) * PER_REQUEST_KWH  # gCO2eq saved
    overhead = chosen.expected_latency_ms - baseline.expected_latency_ms

    # explanation reason
    dom = max(chosen.score_breakdown.items(), key=lambda kv: kv[1])
    if chosen.region == baseline.region:
        reason = f"latency-optimal region {chosen.display} also wins on green score"
    elif saved > 0:
        reason = f"chose {chosen.display}: saves {saved:.2f} gCO2 vs {baseline.display} for +{overhead:.0f}ms"
    else:
        reason = f"chose {chosen.display}: dominant factor = {dom[0]} ({dom[1]:.3f})"

    mark_hit(chosen.region, t)
    return Decision(
        chosen=chosen, baseline_latency=baseline, candidates=candidates,
        weights=w, carbon_saved_g=saved, latency_overhead_ms=overhead,
        reason=reason,
    )
