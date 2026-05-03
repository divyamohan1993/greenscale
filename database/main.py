"""GreenScale DB service.

SQLite-backed REST API. The SQLite file lives in /data/db.sqlite. On startup,
if a file exists in GCS at gs://$GCS_BUCKET/db.sqlite we restore it; this
makes Cloud Run cold starts durable. A background task uploads the file
back to GCS every PUSH_EVERY_SEC. SIGTERM also triggers a final push.

This service runs on Cloud Run with min-instances=0 and is therefore
zero-idle-cost. RPO is bounded by PUSH_EVERY_SEC (default 30s) and the
trailing transactions if the instance is killed without graceful shutdown.
"""
from __future__ import annotations
import asyncio
import contextlib
import json
import logging
import os
import signal
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s',
)
log = logging.getLogger("greenscale-db")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "db.sqlite"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_OBJECT = os.environ.get("GCS_OBJECT", "db.sqlite")
PUSH_EVERY_SEC = int(os.environ.get("PUSH_EVERY_SEC", "30"))

_db_lock = threading.Lock()
_dirty = False  # protected by _db_lock
_last_push_ts = 0.0


def _gcs_client():
    if not GCS_BUCKET:
        return None
    from google.cloud import storage
    return storage.Client()


def _gcs_pull():
    if not GCS_BUCKET:
        log.info("no GCS_BUCKET set, skipping pull")
        return
    try:
        client = _gcs_client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_OBJECT)
        if blob.exists():
            blob.download_to_filename(str(DB_PATH))
            log.info("restored db from gs://%s/%s (%d bytes)", GCS_BUCKET, GCS_OBJECT, DB_PATH.stat().st_size)
        else:
            log.info("no existing db in GCS, will create fresh")
    except Exception as e:
        log.error("gcs pull failed: %s", e)


def _gcs_push():
    global _last_push_ts
    if not GCS_BUCKET or not DB_PATH.exists():
        return
    try:
        client = _gcs_client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_OBJECT)
        blob.upload_from_filename(str(DB_PATH))
        _last_push_ts = time.time()
        log.info("pushed db to gs://%s/%s (%d bytes)", GCS_BUCKET, GCS_OBJECT, DB_PATH.stat().st_size)
    except Exception as e:
        log.error("gcs push failed: %s", e)


def _init_db():
    _gcs_pull()
    with sqlite3.connect(DB_PATH) as c:
        c.executescript(SCHEMA_PATH.read_text())
        c.commit()
    log.info("sqlite ready at %s", DB_PATH)


def _connection():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


# --- Background pusher ----------------------------------------------------

_stopping = threading.Event()


async def _pusher():
    while not _stopping.is_set():
        await asyncio.sleep(PUSH_EVERY_SEC)
        global _dirty
        with _db_lock:
            if _dirty:
                _dirty = False
                push = True
            else:
                push = False
        if push:
            await asyncio.to_thread(_gcs_push)


# --- FastAPI --------------------------------------------------------------

app = FastAPI(title="GreenScale DB", version="1.0.0")


class DecisionIn(BaseModel):
    ts: str
    user_lat: float | None = None
    user_lon: float | None = None
    chosen_region: str
    baseline_region: str
    candidates_json: str
    weights_json: str
    carbon_saved_g: float
    latency_overhead_ms: float
    reason: str


@app.on_event("startup")
async def startup():
    _init_db()
    asyncio.create_task(_pusher())


@app.on_event("shutdown")
async def shutdown():
    _stopping.set()
    log.info("shutdown: final push")
    await asyncio.to_thread(_gcs_push)


@app.get("/health")
def health():
    with _connection() as c:
        n = c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    return {
        "status": "ok",
        "rows": n,
        "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "last_push_ts": _last_push_ts,
        "gcs_bucket": GCS_BUCKET or None,
    }


@app.post("/decisions")
def post_decision(d: DecisionIn):
    global _dirty
    sql = """INSERT INTO decisions
        (ts, user_lat, user_lon, chosen_region, baseline_region,
         candidates_json, weights_json, carbon_saved_g, latency_overhead_ms, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    args = (d.ts, d.user_lat, d.user_lon, d.chosen_region, d.baseline_region,
            d.candidates_json, d.weights_json, d.carbon_saved_g,
            d.latency_overhead_ms, d.reason)
    with _db_lock:
        with _connection() as c:
            cur = c.execute(sql, args)
            c.commit()
            decision_id = cur.lastrowid
        _dirty = True
    return {"id": decision_id}


@app.get("/decisions")
def list_decisions(limit: int = 50):
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be 1..500")
    with _connection() as c:
        rows = c.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/stats")
def stats():
    with _connection() as c:
        total = c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        agg = c.execute(
            """SELECT COALESCE(SUM(carbon_saved_g),0)   AS total_carbon_saved_g,
                       COALESCE(AVG(latency_overhead_ms),0) AS avg_latency_overhead_ms,
                       COALESCE(SUM(CASE WHEN chosen_region != baseline_region THEN 1 ELSE 0 END),0) AS reroutes,
                       COALESCE(SUM(CASE WHEN carbon_saved_g > 0 THEN 1 ELSE 0 END),0) AS green_wins
               FROM decisions"""
        ).fetchone()
        per_region = c.execute(
            """SELECT chosen_region AS region, COUNT(*) AS n,
                       COALESCE(SUM(carbon_saved_g),0) AS carbon_saved_g
               FROM decisions GROUP BY chosen_region ORDER BY n DESC"""
        ).fetchall()
    return {
        "total_requests": total,
        "total_carbon_saved_g": round(agg["total_carbon_saved_g"], 4),
        "avg_latency_overhead_ms": round(agg["avg_latency_overhead_ms"], 2),
        "reroutes": agg["reroutes"],
        "green_wins": agg["green_wins"],
        "per_region": [dict(r) for r in per_region],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
