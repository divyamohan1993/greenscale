"""Static region catalog with realistic 2025 grid carbon intensity.

Sources for mean carbon intensity (gCO2eq/kWh, 2024-2025 averages):
- ember-energy.org grid intensity dataset
- Google Cloud public regional carbon disclosures
- electricitymaps.com historical 2024-2025 averages

Hourly Cloud Run cost (always-on, 1 vCPU + 512Mi) from cloud.google.com/run pricing.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Region:
    code: str
    display: str
    lat: float
    lon: float
    mean_ci: float        # gCO2eq/kWh (24h mean)
    amp: float            # diurnal amplitude (fraction of mean)
    phase_hour: float     # hour-of-day where ci is *minimum* (UTC)
    hourly_cost: float    # USD per instance-hour

REGIONS: list[Region] = [
    Region("asia-south1",         "Mumbai",       19.0760,  72.8777, 710, 0.08, 14.0, 0.0240),
    Region("asia-southeast1",     "Singapore",     1.3521, 103.8198, 480, 0.10,  6.0, 0.0240),
    Region("europe-west1",        "St-Ghislain",  50.4520,   3.9520, 165, 0.30, 12.0, 0.0240),
    Region("europe-north1",       "Hamina",       60.5693,  27.1878, 100, 0.25, 10.0, 0.0220),
    Region("us-central1",         "Iowa",         41.2619, -95.8608, 430, 0.20, 18.0, 0.0240),
    Region("us-west1",            "The Dalles",   45.5946,-121.1787,  90, 0.45, 20.0, 0.0240),
    Region("southamerica-east1",  "Sao Paulo",   -23.5505, -46.6333,  95, 0.15, 14.0, 0.0260),
]

REGIONS_BY_CODE = {r.code: r for r in REGIONS}
