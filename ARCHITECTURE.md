# GreenScale — Architecture & Contracts

## Three Cloud Run services (all min-instances=0)

```
                         ┌──────────────────────────┐
                         │      User browser        │
                         └────────────┬─────────────┘
                                      │ HTTPS
                                      ▼
                         ┌──────────────────────────┐
   /, /pitch, /report ◄──┤  greenscale-frontend     │  nginx static
                         │  Cloud Run · 256Mi · 1cpu│  min=0
                         └────────────┬─────────────┘
                          /api/* proxy │
                                      ▼
                         ┌──────────────────────────┐
   /v1/route             │  greenscale-backend      │  Python · FastAPI
   /v1/regions           │  Cloud Run · 512Mi · 1cpu│  routing logic
   /v1/decisions         │  min=0                   │  carbon model
   /v1/stats             └────────────┬─────────────┘  cold-start model
                                      │
                                      ▼
                         ┌──────────────────────────┐
   POST /decisions       │  greenscale-db           │  Python · FastAPI
   GET  /decisions       │  Cloud Run · 256Mi · 1cpu│  SQLite + GCS
   GET  /stats           │  min=0                   │  pull-on-start
                         └────────────┬─────────────┘  push-periodic
                                      │
                                      ▼
                              gs://greenscale-state
                                      │
                                      ▼
                              db.sqlite (durable)
```

## Backend routing math

For each candidate region `r` at time `t`, given user `(lat,lon)`:

```
latency_norm  =  rtt_ms(user, r) / MAX_RTT
carbon_norm   =  ci_g_per_kwh(r, t) / MAX_CI
cold_norm     =  P_coldstart(r, t)              # already in [0,1]
cost_norm     =  hourly_cost(r) / MAX_COST

score(r, t)   =  w_lat * latency_norm
              +  w_carbon * carbon_norm
              +  w_cold * cold_norm
              +  w_cost * cost_norm

chosen = argmin_r score(r, t)
```

Default weights (sustainability-leaning): `w_lat=0.25, w_carbon=0.45, w_cold=0.20, w_cost=0.10`.

Latency-only baseline for comparison: `w_lat=1, others=0`. We log both choices on every decision and compute `carbon_saved_g` and `latency_overhead_ms`.

## Six simulated regions (realistic 2025 grid intensity)

| Region | Display | Lat | Lon | Mean gCO2/kWh | Hourly cost (USD) |
|--------|---------|-----|-----|---------------|-------------------|
| asia-south1 | Mumbai | 19.07 | 72.87 | 710 | 0.024 |
| asia-southeast1 | Singapore | 1.35 | 103.82 | 480 | 0.024 |
| europe-west1 | St-Ghislain | 50.45 | 3.95 | 165 | 0.024 |
| europe-north1 | Hamina | 60.57 | 27.20 | 100 | 0.022 |
| us-central1 | Iowa | 41.26 | -95.86 | 430 | 0.024 |
| us-west1 | The Dalles | 45.60 | -121.18 | 90 | 0.024 |
| southamerica-east1 | Sao Paulo | -23.55 | -46.63 | 95 | 0.024 |

Time-of-day variation: solar-heavy regions dip 30% at midday, peak at night. Coal-heavy stays flat ±10%.

## DB schema (SQLite)

```sql
CREATE TABLE regions (
  region TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  mean_ci_g_per_kwh REAL NOT NULL,
  hourly_cost_usd REAL NOT NULL
);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_lat REAL, user_lon REAL,
  chosen_region TEXT NOT NULL,
  baseline_region TEXT NOT NULL,         -- latency-only choice
  candidates_json TEXT NOT NULL,         -- per-region scores
  weights_json TEXT NOT NULL,
  carbon_saved_g REAL NOT NULL,          -- vs baseline, per request
  latency_overhead_ms REAL NOT NULL,
  reason TEXT NOT NULL
);
CREATE INDEX idx_decisions_ts ON decisions(ts);

CREATE TABLE carbon_history (
  region TEXT NOT NULL,
  ts TEXT NOT NULL,
  intensity_g_per_kwh REAL NOT NULL,
  PRIMARY KEY (region, ts)
);
```

## Cold-start model

Per-region last-hit timestamp `t_last(r)` is held in router memory. Probability of cold start at time `t`:

```
dt = max(0, t - t_last(r))
P_coldstart(r, t) = 1 - exp(-dt / TAU)     # TAU = 300s (Cloud Run keepalive band)
```

Successful route resets `t_last(r)`.

## Carbon model

```
ci(r, t) = mean_ci(r) * (1 + amp(r) * sin(2*pi*(hour(t) - phase(r)) / 24)) + noise
```

Amplitude: `amp(asia-south1)=0.08`, `amp(us-west1)=0.45`, etc. (greener grids = larger swing).

## API surface

### Backend (`greenscale-backend`)

- `GET  /v1/regions` → list of all regions with current carbon/cold/latency-from-default
- `POST /v1/route` body `{user_lat, user_lon, weights?}` → `{chosen, baseline, candidates[], reasoning, carbon_saved_g, latency_overhead_ms}`
- `POST /v1/demo-request` body `{user_lat, user_lon}` → routes + persists decision
- `GET  /v1/decisions/recent?limit=50` → last N decisions (proxy to DB)
- `GET  /v1/stats` → `{total_requests, total_carbon_saved_g, avg_latency_overhead_ms, requests_per_region}`
- `GET  /healthz`

### DB (`greenscale-db`)

- `POST /decisions` body `{...row...}` → `{id}`
- `GET  /decisions?limit=N` → `[{...},...]`
- `GET  /stats` → aggregations
- `GET  /healthz`

### Frontend (`greenscale-frontend`)

- `GET  /` → dashboard (live map, decision feed, stats, manual demo button)
- `GET  /pitch` → arrow-key slide deck
- `GET  /report` → full capstone report (HTML render of the docx template)
- `GET  /api/*` → reverse-proxied to backend by nginx

## Persistence (zero idle cost)

DB instance scales to zero. On cold start: pulls `db.sqlite` from `gs://greenscale-state/db.sqlite` if present, else seeds. On every write: also writes a delta row. Every 30s (if alive): pushes full file back to GCS. On SIGTERM: final push. RPO ≤ 30s.

## Auth (MVP)

Public read endpoints. Demo POSTs are rate-limited (10/min per IP) at the backend. No PII. Not in scope: tenant isolation, JWT — these are future work documented in the report.

## Deploy targets

- Project: `dmjone`
- Region: `asia-south1` (closest to user)
- Service names: `greenscale-frontend`, `greenscale-backend`, `greenscale-db`
- All `--min-instances=0`, `--max-instances=5`, `--cpu=1`, `--memory=256Mi`/`512Mi`/`256Mi`
