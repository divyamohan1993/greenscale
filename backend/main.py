"""GreenScale router service - FastAPI entrypoint.

Exposes the routing API + region/carbon snapshots for the dashboard.
Persists every decision to the greenscale-db service.
"""
from __future__ import annotations
import asyncio
import dataclasses
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import coldstart, db_client
from app.carbon import carbon_for_all, carbon_intensity
from app.regions import REGIONS, REGIONS_BY_CODE
from app.routing import route, DEFAULT_WEIGHTS, rtt_ms

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s',
)
log = logging.getLogger("greenscale")

app = FastAPI(title="GreenScale Router", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

coldstart.seed([r.code for r in REGIONS])

# in-memory rate limit buckets per IP for /v1/demo-request
_rate: dict[str, deque] = {}
RATE_WINDOW_S = 60
RATE_LIMIT = 30


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _rate.setdefault(ip, deque())
    while q and now - q[0] > RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return False
    q.append(now)
    return True


def _candidate_dict(c) -> dict:
    return {
        "region": c.region, "display": c.display,
        "lat": c.lat, "lon": c.lon,
        "rtt_ms": round(c.rtt_ms, 1),
        "ci_g_per_kwh": round(c.ci, 1),
        "cold_p": round(c.cold, 4),
        "cost_usd_hr": c.cost,
        "expected_latency_ms": round(c.expected_latency_ms, 1),
        "score": round(c.score, 5),
        "score_breakdown": {k: round(v, 5) for k, v in c.score_breakdown.items()},
    }


class RouteReq(BaseModel):
    user_lat: float = Field(..., ge=-90, le=90)
    user_lon: float = Field(..., ge=-180, le=180)
    weights: dict[str, float] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/v1/regions")
def regions(user_lat: float = 19.0760, user_lon: float = 72.8777):
    """Snapshot of all regions for the dashboard."""
    out = []
    for r in REGIONS:
        out.append({
            "region": r.code, "display": r.display,
            "lat": r.lat, "lon": r.lon,
            "mean_ci": r.mean_ci,
            "ci_g_per_kwh": round(carbon_intensity(r.code), 1),
            "cold_p": round(coldstart.cold_prob(r.code), 4),
            "rtt_ms": round(rtt_ms(user_lat, user_lon, r.code), 1),
            "cost_usd_hr": r.hourly_cost,
        })
    return {"regions": out, "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/v1/carbon")
def carbon():
    return {
        "carbon": {k: round(v, 1) for k, v in carbon_for_all().items()},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/route")
def route_only(req: RouteReq):
    """Computes a routing decision but does NOT persist it (preview)."""
    d = route(req.user_lat, req.user_lon, req.weights)
    return _decision_payload(d, req.user_lat, req.user_lon)


@app.post("/v1/demo-request")
async def demo_request(req: RouteReq, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    if not _rate_ok(ip):
        raise HTTPException(429, "rate limit: 30 / minute")
    d = route(req.user_lat, req.user_lon, req.weights)
    payload = _decision_payload(d, req.user_lat, req.user_lon)

    row = {
        "ts": payload["ts"],
        "user_lat": req.user_lat, "user_lon": req.user_lon,
        "chosen_region": d.chosen.region,
        "baseline_region": d.baseline_latency.region,
        "candidates_json": json.dumps(payload["candidates"]),
        "weights_json": json.dumps(d.weights),
        "carbon_saved_g": round(d.carbon_saved_g, 4),
        "latency_overhead_ms": round(d.latency_overhead_ms, 2),
        "reason": d.reason,
    }
    decision_id = await db_client.post_decision(row)
    payload["id"] = decision_id
    return payload


def _decision_payload(d, user_lat: float, user_lon: float) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_lat": user_lat, "user_lon": user_lon,
        "chosen": _candidate_dict(d.chosen),
        "baseline_latency": _candidate_dict(d.baseline_latency),
        "candidates": [_candidate_dict(c) for c in d.candidates],
        "weights": d.weights,
        "carbon_saved_g": round(d.carbon_saved_g, 4),
        "latency_overhead_ms": round(d.latency_overhead_ms, 2),
        "reason": d.reason,
    }


@app.get("/v1/decisions/recent")
async def recent(limit: int = 50):
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be 1..500")
    rows = await db_client.list_decisions(limit)
    return {"decisions": rows}


@app.get("/v1/stats")
async def stats():
    s = await db_client.stats()
    return s


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
