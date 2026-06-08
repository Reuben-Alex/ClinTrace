#!/usr/bin/env bash
# Build and deploy the ClinTrace UI (FastAPI) to Cloud Run.
# Connects to Agent Engine via AGENT_ENGINE_RESOURCE_ID and Phoenix via secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PROJECT="${GOOGLE_CLOUD_PROJECT:-${GOOGLE_PROJECT_ID:-}}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${UI_SERVICE_NAME:-clinictrace-ui}"
SECRET_PHOENIX_API_KEY="${SECRET_PHOENIX_API_KEY:-clinictrace-phoenix-api-key}"

if [[ -z "${PROJECT}" ]]; then
  echo "Set GOOGLE_CLOUD_PROJECT in .env" >&2
  exit 1
fi

# Prefer deployment_metadata.json for the latest Agent Engine resource.
if [[ -f deployment_metadata.json ]]; then
  META_ID="$(python3 -c "
import json
with open('deployment_metadata.json') as f:
    print(json.load(f).get('remote_agent_engine_id', ''))
" 2>/dev/null || true)"
  if [[ -n "${META_ID}" ]]; then
    AGENT_ENGINE_RESOURCE_ID="${META_ID}"
  fi
fi

if [[ -z "${AGENT_ENGINE_RESOURCE_ID:-}" ]]; then
  echo "Set AGENT_ENGINE_RESOURCE_ID in .env or run: make deploy-agent" >&2
  exit 1
fi

PHOENIX_HOST="${PHOENIX_COLLECTOR_ENDPOINT:-}"
if [[ -z "${PHOENIX_HOST}" ]]; then
  echo "Set PHOENIX_COLLECTOR_ENDPOINT in .env" >&2
  exit 1
fi

grant_role() {
  local role="$1"
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="${role}" \
    --quiet >/dev/null 2>&1 || true
}

grant_secret_accessor() {
  local name="$1"
  gcloud secrets add-iam-policy-binding "${name}" \
    --project="${PROJECT}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet >/dev/null 2>&1 || true
}

echo "Enabling APIs (Cloud Run, Artifact Registry, BigQuery)..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  aiplatform.googleapis.com \
  --project="${PROJECT}" >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Granting ${RUNTIME_SA} IAM for Agent Engine, BigQuery, secrets..."
grant_role "roles/aiplatform.user"
grant_role "roles/serviceusage.serviceUsageConsumer"
grant_role "roles/bigquery.jobUser"
grant_role "roles/bigquery.dataViewer"
grant_secret_accessor "${SECRET_PHOENIX_API_KEY}"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/clinictrace/${SERVICE}:latest"

echo "Ensuring Artifact Registry repo clinictrace..."
gcloud artifacts repositories describe clinictrace \
  --project="${PROJECT}" \
  --location="${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create clinictrace \
    --project="${PROJECT}" \
    --location="${REGION}" \
    --repository-format=docker \
    --description="ClinTrace containers" \
    --quiet

echo "Building image ${IMAGE}..."
gcloud builds submit . \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --tag="${IMAGE}" \
  --quiet

BQ_TABLE="${BQ_NHAMCS_TABLE:-${PROJECT}:clinictrace.ed_triage}"
ENV_VARS="\
GOOGLE_PROJECT_ID=${PROJECT},\
GOOGLE_CLOUD_PROJECT=${PROJECT},\
GOOGLE_CLOUD_LOCATION=global,\
GOOGLE_GENAI_USE_VERTEXAI=true,\
CLINICTRACE_VERTEX_LOCATION=global,\
CLINICTRACE_MODEL=${CLINICTRACE_MODEL:-gemini-3.5-flash},\
GEMINI_EVAL_MODEL=${GEMINI_EVAL_MODEL:-gemini-3.5-flash},\
AGENT_ENGINE_RESOURCE_ID=${AGENT_ENGINE_RESOURCE_ID},\
AGENT_ENGINE_REGION=${AGENT_ENGINE_REGION:-us-central1},\
PHOENIX_COLLECTOR_ENDPOINT=${PHOENIX_HOST},\
PHOENIX_PROJECT_NAME=${PHOENIX_PROJECT_NAME:-clinictrace},\
PHOENIX_PROJECT_ID=${PHOENIX_PROJECT_ID:-},\
BQ_NHAMCS_TABLE=${BQ_TABLE},\
UI_SKIP_QUALITY_EVAL=${UI_SKIP_QUALITY_EVAL:-true},\
UI_INTAKE_LLM_QUALITY_EVAL=${UI_INTAKE_LLM_QUALITY_EVAL:-true},\
FAST_TRIAGE=${FAST_TRIAGE:-true}"

echo "Deploying Cloud Run service ${SERVICE}..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --allow-unauthenticated \
  --service-account="${RUNTIME_SA}" \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="${ENV_VARS}" \
  --set-secrets="PHOENIX_API_KEY=${SECRET_PHOENIX_API_KEY}:latest" \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo ""
echo "Deployed ClinTrace UI: ${URL}"
echo "Health: ${URL}/health"
echo ""
echo "Connected to Agent Engine:"
echo "  ${AGENT_ENGINE_RESOURCE_ID}"
echo ""
echo "Update .env (optional):"
echo "  CLINICTRACE_UI_URL=${URL}"
