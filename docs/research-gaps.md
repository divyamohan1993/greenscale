# Research Gaps in Recent Cloud Computing (2025-2026)

## Anchor Papers (Recent, peer-reviewed / arXiv)

| # | Paper | Date | Venue/ID | Contribution | What it does NOT do |
|---|-------|------|----------|--------------|---------------------|
| 1 | **Green or Fast? Learning to Balance Cold Starts and Idle Carbon in Serverless Computing (LACE-RL)** | 2026-02-27 | arXiv:2602.23935 | Deep-RL keep-alive tuner, 51.69% fewer cold starts, 77.08% less idle carbon | Single-region; tunes keep-alive only; black-box RL; per-platform |
| 2 | **Aceso: Carbon-Aware and Cost-Effective Microservice Placement for SMEs** | 2026-03-11 | arXiv:2603.10768 | Design-time placement optimizer for SMEs | Design-time; not per-request; not multi-region routing |
| 3 | **Cold-Start Anti-Patterns and Refactorings in Serverless Systems** | 2025-12-18 | arXiv:2512.16066 | Empirical taxonomy of cold-start anti-patterns | Catalogs problems; provides no runtime mitigation layer |
| 4 | **Spatio-Temporal Shifting to Reduce Carbon, Water, Land-Use Footprints** | 2025-12-09 | arXiv:2512.08725 | Time/space workload shifting for batch | Batch jobs; not interactive request paths |
| 5 | **Taming Cold Starts: Proactive Serverless Scheduling with MPC** | 2025-08-11 | arXiv:2508.07640 | Model-predictive proactive scheduling | Single-cluster; carbon not first-class |
| 6 | **Green by Design: Constraint-Based Adaptive Deployment in Cloud Continuum** | 2026-02-20 | arXiv:2602.18287 | Design-time constraint solver | Not runtime; not transparent / explainable |
| 7 | **Failure-Resilient and Carbon-Efficient Microservices over Cloud-Edge Continuum** | 2026-01-07 | arXiv:2601.04123 | Joint resilience + carbon placement | Topology-level; not per-request |

## Gap 1: No per-request, runtime, multi-region routing layer that **jointly** optimizes carbon + cold-start + latency + cost

**Evidence.** LACE-RL (#1) optimizes keep-alive *within one region*. Aceso (#2) and Green-by-Design (#6) optimize *placement* at design time. Spatio-Temporal Shifting (#4) is for *batch* workloads, not interactive request paths.

**Why it matters.** A user request hitting a multi-region serverless deployment is steered today by latency-only routing (e.g., GCLB latency-based, AWS Latency-Based Routing). The grid carbon intensity at each region varies 5x-10x at any moment (e.g., asia-south1 ~700 gCO2/kWh vs us-west1 ~80 gCO2/kWh). Cold-start probability also varies by region traffic. *Routing the request to a different region for the same call can cut emissions by an order of magnitude with often <50ms extra latency* — but no production tooling exposes this trade-off per request.

## Gap 2: Carbon-aware schedulers are research prototypes, **not deployable middleware**, and **not transparent**

**Evidence.** LACE-RL (#1) is a Knative/Kubernetes-internal RL agent — black-box decisions, requires platform-level access. Aceso (#2) targets SMEs but is a research framework, not an installable plane. The Anti-Patterns survey (#3) confirms the gap: practitioners catalog problems but lack drop-in fixes.

**Why it matters.** An SME, a student, or a small team running on Cloud Run / Lambda / Cloud Functions has *no path* to adopt carbon-aware routing without rebuilding the platform. Even when it works, decisions cannot be audited (e.g., for sustainability reporting under CSRD / India BRSR). The field needs a *transparent, provider-agnostic, drop-in routing plane* that lives in front of existing managed serverless deployments.

## Proposed Solution: GreenScale

A **transparent, deployable routing plane** for multi-region serverless that, *per request*:

1. Computes a **score per candidate region** combining four real signals:
   - **Latency** — Haversine distance + provider RTT model
   - **Carbon intensity** — live grid carbon (gCO2eq/kWh)
   - **Cold-start probability** — exponential decay since last hit
   - **Cost** — instance-hour pricing per region (Cloud Run pricing table)
2. **Routes** to the argmin region.
3. **Logs** the full reasoning (every weight, every score) into a queryable audit table.
4. **Exposes** the trade-off via a live dashboard — operators can re-tune `(w_lat, w_carbon, w_cold, w_cost)` without code change.

**Novelty over the state of the art**

| Property | LACE-RL | Aceso | Green-by-Design | **GreenScale** |
|----------|---------|-------|-----------------|---------------|
| Per-request | No | No | No | **Yes** |
| Multi-region | No | Partial | No | **Yes** |
| Runtime | Yes | No | No | **Yes** |
| Transparent / auditable | No (RL) | Heuristic | Constraint | **Yes (linear, logged)** |
| Drop-in (no platform mod) | No | No | No | **Yes** |
| Joint cold-start + carbon + latency + cost | Cold + carbon | Carbon + cost | Carbon + constraints | **All four** |

**Capstone Deliverable.** Three Cloud Run services (frontend, backend router, SQLite DB), six simulated regions with realistic carbon traces, live dashboard, and an arrow-key slide deck pitch + full HTML capstone report, all min-instances=0 (zero idle cost).
