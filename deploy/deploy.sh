#!/usr/bin/env bash
# GreenScale - Cloud Run deploy script.
#
# Deploys three services in dependency order: db, backend, frontend.
# Each service is created with --min-instances=0 so idle cost is zero.
#
# Required env vars (or defaults shown):
#   PROJECT     = dmjone
#   REGION      = asia-south1
#   GCS_BUCKET  = greenscale-state
#
# Usage:
#   bash deploy/deploy.sh                # deploys all three
#   bash deploy/deploy.sh db             # deploy just db
#   bash deploy/deploy.sh backend
#   bash deploy/deploy.sh frontend

set -euo pipefail

PROJECT="${PROJECT:-dmjone}"
REGION="${REGION:-asia-east1}"
GCS_BUCKET="${GCS_BUCKET:-greenscale-state}"
DOMAIN="${DOMAIN:-greenscale.dmj.one}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DB_SVC="greenscale-db"
BE_SVC="greenscale-backend"
FE_SVC="greenscale-frontend"

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[36m%s\033[0m\n' "$*"; }

require_apis() {
    blue "==> ensuring required APIs are enabled"
    gcloud services enable \
        run.googleapis.com \
        cloudbuild.googleapis.com \
        artifactregistry.googleapis.com \
        storage.googleapis.com \
        --project="$PROJECT" >/dev/null
}

ensure_bucket() {
    if ! gsutil ls -b "gs://$GCS_BUCKET" >/dev/null 2>&1; then
        blue "==> creating GCS bucket gs://$GCS_BUCKET"
        gsutil mb -p "$PROJECT" -l "$REGION" "gs://$GCS_BUCKET"
        # uniform bucket-level access (best-practice)
        gsutil ubla set on "gs://$GCS_BUCKET"
    else
        green "    bucket gs://$GCS_BUCKET exists"
    fi
}

grant_bucket_access() {
    local svc="$1"
    local sa
    sa="$(gcloud run services describe "$svc" --region "$REGION" --project "$PROJECT" --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
    if [[ -z "$sa" ]]; then
        sa="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
    fi
    blue "    granting roles/storage.objectAdmin on bucket to $sa"
    gsutil iam ch "serviceAccount:${sa}:roles/storage.objectAdmin" "gs://$GCS_BUCKET" >/dev/null
}

regen_static() {
    blue "==> regenerating report.docx + report.html from JSON"
    python3 "$ROOT/build/generate_report.py"
    python3 "$ROOT/build/generate_html_report.py"
}

deploy_db() {
    blue "==> deploying $DB_SVC"
    gcloud run deploy "$DB_SVC" \
        --source "$ROOT/database" \
        --region "$REGION" --project "$PROJECT" \
        --allow-unauthenticated \
        --memory 256Mi --cpu 1 \
        --min-instances 0 --max-instances 3 \
        --timeout 60 \
        --port 8080 \
        --set-env-vars "GCS_BUCKET=$GCS_BUCKET,PUSH_EVERY_SEC=30" \
        --quiet
    grant_bucket_access "$DB_SVC"
    DB_URL="$(gcloud run services describe "$DB_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
    green "    $DB_SVC deployed: $DB_URL"
    echo "$DB_URL" > /tmp/greenscale-db.url
}

deploy_backend() {
    if [[ ! -s /tmp/greenscale-db.url ]]; then
        DB_URL="$(gcloud run services describe "$DB_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
    else
        DB_URL="$(cat /tmp/greenscale-db.url)"
    fi
    if [[ -z "${DB_URL:-}" ]]; then red "DB_URL not set; deploy db first"; exit 1; fi

    blue "==> deploying $BE_SVC (DB_URL=$DB_URL)"
    gcloud run deploy "$BE_SVC" \
        --source "$ROOT/backend" \
        --region "$REGION" --project "$PROJECT" \
        --allow-unauthenticated \
        --memory 512Mi --cpu 1 \
        --min-instances 0 --max-instances 5 \
        --timeout 60 \
        --port 8080 \
        --set-env-vars "DB_URL=$DB_URL" \
        --quiet
    BE_URL="$(gcloud run services describe "$BE_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
    green "    $BE_SVC deployed: $BE_URL"
    echo "$BE_URL" > /tmp/greenscale-be.url
}

deploy_frontend() {
    if [[ ! -s /tmp/greenscale-be.url ]]; then
        BE_URL="$(gcloud run services describe "$BE_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
    else
        BE_URL="$(cat /tmp/greenscale-be.url)"
    fi
    if [[ -z "${BE_URL:-}" ]]; then red "BE_URL not set; deploy backend first"; exit 1; fi

    regen_static

    blue "==> deploying $FE_SVC (BACKEND_URL=$BE_URL)"
    gcloud run deploy "$FE_SVC" \
        --source "$ROOT/frontend" \
        --region "$REGION" --project "$PROJECT" \
        --allow-unauthenticated \
        --memory 256Mi --cpu 1 \
        --min-instances 0 --max-instances 5 \
        --timeout 30 \
        --port 8080 \
        --set-env-vars "BACKEND_URL=$BE_URL" \
        --quiet
    FE_URL="$(gcloud run services describe "$FE_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
    green "    $FE_SVC deployed: $FE_URL"
    echo "$FE_URL" > /tmp/greenscale-fe.url
}

smoke_test() {
    DB_URL="$(cat /tmp/greenscale-db.url 2>/dev/null || gcloud run services describe "$DB_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || echo)"
    BE_URL="$(cat /tmp/greenscale-be.url 2>/dev/null || gcloud run services describe "$BE_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || echo)"
    FE_URL="$(cat /tmp/greenscale-fe.url 2>/dev/null || gcloud run services describe "$FE_SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || echo)"

    blue "==> smoke test"
    set +e
    fail=0
    for u in "$DB_URL/health" "$BE_URL/health" "$FE_URL/health"; do
        local code
        code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$u" || echo 000)"
        if [[ "$code" == "200" ]]; then green "    OK   $u"
        else red "    FAIL $u (code=$code)"; fail=1
        fi
    done
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$BE_URL/v1/regions" || echo 000)"
    [[ "$code" == "200" ]] && green "    OK   $BE_URL/v1/regions" || { red "    FAIL $BE_URL/v1/regions ($code)"; fail=1; }

    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$FE_URL/" || echo 000)"
    [[ "$code" == "200" ]] && green "    OK   $FE_URL/" || { red "    FAIL $FE_URL/ ($code)"; fail=1; }
    set -e

    if [[ "$fail" -ne 0 ]]; then red "smoke test failed"; exit 1; fi

    yellow ""
    yellow "================================================================"
    yellow "  GreenScale is live."
    yellow "    Dashboard: $FE_URL/"
    yellow "    Pitch    : $FE_URL/pitch"
    yellow "    Report   : $FE_URL/report"
    yellow "    Backend  : $BE_URL"
    yellow "    DB       : $DB_URL"
    yellow "================================================================"
}

main() {
    local target="${1:-all}"
    require_apis
    ensure_bucket

    case "$target" in
        all)
            deploy_db
            deploy_backend
            deploy_frontend
            smoke_test
            map_domain
            ;;
        db)       deploy_db ;;
        backend)  deploy_backend ;;
        frontend) deploy_frontend ;;
        smoke)    smoke_test ;;
        domain)   map_domain ;;
        *)        red "unknown target: $target (use db|backend|frontend|all|smoke|domain)"; exit 2 ;;
    esac
}

map_domain() {
    if [[ -z "${DOMAIN:-}" ]]; then yellow "    no DOMAIN set, skipping mapping"; return 0; fi
    blue "==> mapping $DOMAIN to $FE_SVC"
    if gcloud beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" --project "$PROJECT" >/dev/null 2>&1; then
        green "    mapping already exists for $DOMAIN"
    else
        gcloud beta run domain-mappings create \
            --service "$FE_SVC" --domain "$DOMAIN" \
            --region "$REGION" --project "$PROJECT" --quiet 2>&1 | tail -10 || true
    fi
    yellow ""
    yellow "Required DNS record (set on $DOMAIN's authoritative DNS):"
    gcloud beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" --project "$PROJECT" \
        --format='value(status.resourceRecords)' 2>&1 || true
    yellow ""
    yellow "Certificate provisioning may take up to 24 hours after DNS resolves."
}

main "$@"
