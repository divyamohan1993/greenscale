# GreenScale

A carbon, cold-start, latency and cost aware routing plane for multi-region serverless. Capstone project of **Tarun Kumar** (B.Tech CSE Cloud Computing, GF202214708). Mentor: Ms. Ishani Sharma, Shoolini University.

For the research framing, see [`docs/research-gaps.md`](docs/research-gaps.md). For the system design, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For the full report, run the system and visit `/report`.

## Live demo (after deploy)

| Page | What it shows |
|------|----------------|
| `/`       | Live dashboard - world map, region carbon levels, decision feed, demo button |
| `/pitch`  | Arrow-key slide deck (← / → / Home / End / 0-9, **F** for fullscreen) |
| `/report` | Full capstone report (HTML) with `Download .docx` link |

## Run it locally

```bash
# DB
( cd database && pip install -r requirements.txt && PORT=9001 GCS_BUCKET="" python3 main.py )

# Backend
( cd backend && pip install -r requirements.txt && PORT=9002 DB_URL=http://localhost:9001 python3 main.py )

# Frontend (without Docker, just open the file - or run the nginx container)
docker build -t gs-frontend ./frontend
docker run -p 9003:8080 -e BACKEND_URL=http://host.docker.internal:9002 gs-frontend
```

## Deploy to Google Cloud Run

```bash
# one-time
gcloud config set project dmjone
gcloud auth application-default login

# all three services, idempotent
bash deploy/deploy.sh
```

Or piecewise: `bash deploy/deploy.sh db`, `bash deploy/deploy.sh backend`, `bash deploy/deploy.sh frontend`.

All three services are created with `--min-instances=0`, so idle cost is zero rupees.

## Regenerate the report (after editing `build/report_content.json`)

```bash
python3 build/generate_report.py        # -> frontend/public/report.docx
python3 build/generate_html_report.py   # -> frontend/public/report.html
```

The deploy script regenerates both before each frontend deploy.

## Project layout

```
backend/        FastAPI router  (routing engine + carbon model + cold-start)
database/       FastAPI + SQLite + GCS round-trip persistence
frontend/       nginx + static HTML/CSS/JS (Leaflet, Chart.js)
build/          report content (single source) + generators (docx + html)
deploy/         Cloud Run deploy script
docs/           research-gaps.md (the two gaps and their evidence)
ARCHITECTURE.md design + contracts
```
