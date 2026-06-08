#!/usr/bin/env bash
# Create Secret Manager secrets and deploy Phoenix MCP (Streamable HTTP) to Cloud Run.
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
SERVICE="${PHOENIX_MCP_SERVICE_NAME:-clinictrace-phoenix-mcp}"

SECRET_PHOENIX_API_KEY="${SECRET_PHOENIX_API_KEY:-clinictrace-phoenix-api-key}"
SECRET_MCP_SERVICE_KEY="${SECRET_MCP_SERVICE_KEY:-clinictrace-mcp-service-api-key}"

if [[ -z "${PROJECT}" ]]; then
  echo "Set GOOGLE_CLOUD_PROJECT in .env" >&2
  exit 1
fi
if [[ -z "${PHOENIX_API_KEY:-}" ]]; then
  echo "Set PHOENIX_API_KEY in .env" >&2
  exit 1
fi

PHOENIX_HOST="${PHOENIX_HOST:-${PHOENIX_COLLECTOR_ENDPOINT:-}}"
if [[ -z "${PHOENIX_HOST}" ]]; then
  echo "Set PHOENIX_COLLECTOR_ENDPOINT (or PHOENIX_HOST) in .env" >&2
  exit 1
fi

# Strip optional quotes from .env-sourced values.
PHOENIX_API_KEY="${PHOENIX_API_KEY%\'}"
PHOENIX_API_KEY="${PHOENIX_API_KEY#\'}"
PHOENIX_API_KEY="${PHOENIX_API_KEY%\"}"
PHOENIX_API_KEY="${PHOENIX_API_KEY#\"}"
PHOENIX_HOST="${PHOENIX_HOST%\'}"
PHOENIX_HOST="${PHOENIX_HOST#\'}"
PHOENIX_HOST="${PHOENIX_HOST%\"}"
PHOENIX_HOST="${PHOENIX_HOST#\"}"

if [[ -z "${MCP_SERVICE_API_KEY:-}" ]]; then
  if gcloud secrets describe "${SECRET_MCP_SERVICE_KEY}" \
    --project="${PROJECT}" >/dev/null 2>&1; then
    MCP_SERVICE_API_KEY="$(
      gcloud secrets versions access latest \
        --project="${PROJECT}" \
        --secret="${SECRET_MCP_SERVICE_KEY}"
    )"
    echo "Using existing ${SECRET_MCP_SERVICE_KEY} from Secret Manager."
  else
    MCP_SERVICE_API_KEY="$(openssl rand -hex 24)"
    echo "Generated MCP_SERVICE_API_KEY — save to .env for Agent Engine clients:"
    echo "  MCP_SERVICE_API_KEY=${MCP_SERVICE_API_KEY}"
    echo "  PHOENIX_MCP_SERVICE_KEY=${MCP_SERVICE_API_KEY}"
  fi
fi

upsert_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "${name}" --project="${PROJECT}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${name}" \
      --project="${PROJECT}" \
      --data-file=- >/dev/null
    echo "Updated secret: ${name}"
  else
    printf '%s' "${value}" | gcloud secrets create "${name}" \
      --project="${PROJECT}" \
      --replication-policy="automatic" \
      --data-file=- >/dev/null
    echo "Created secret: ${name}"
  fi
}

grant_secret_accessor() {
  local name="$1"
  local sa="$2"
  gcloud secrets add-iam-policy-binding "${name}" \
    --project="${PROJECT}" \
    --member="serviceAccount:${sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet >/dev/null
}

echo "Enabling APIs (Secret Manager, Cloud Run)..."
gcloud services enable secretmanager.googleapis.com run.googleapis.com \
  --project="${PROJECT}" >/dev/null

echo "Creating/updating secrets in Secret Manager..."
upsert_secret "${SECRET_PHOENIX_API_KEY}" "${PHOENIX_API_KEY}"
upsert_secret "${SECRET_MCP_SERVICE_KEY}" "${MCP_SERVICE_API_KEY}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "Granting ${RUNTIME_SA} access to secrets..."
grant_secret_accessor "${SECRET_PHOENIX_API_KEY}" "${RUNTIME_SA}"
grant_secret_accessor "${SECRET_MCP_SERVICE_KEY}" "${RUNTIME_SA}"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/clinictrace/${SERVICE}:latest"

echo "Building image ${IMAGE}..."
gcloud artifacts repositories describe clinictrace \
  --project="${PROJECT}" \
  --location="${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create clinictrace \
    --project="${PROJECT}" \
    --location="${REGION}" \
    --repository-format=docker \
    --description="ClinTrace containers" \
    --quiet

gcloud builds submit services/phoenix-mcp-http \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --tag="${IMAGE}" \
  --quiet

echo "Deploying Cloud Run service ${SERVICE}..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --allow-unauthenticated \
  --service-account="${RUNTIME_SA}" \
  --set-env-vars="PHOENIX_HOST=${PHOENIX_HOST},PHOENIX_PROJECT_NAME=${PHOENIX_PROJECT_NAME:-clinictrace}" \
  --set-secrets="PHOENIX_API_KEY=${SECRET_PHOENIX_API_KEY}:latest,MCP_SERVICE_API_KEY=${SECRET_MCP_SERVICE_KEY}:latest" \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo ""
echo "Deployed: ${URL}/mcp"
echo ""
echo "Add to .env and clintrace_agent/.agent_engine_config.json:"
echo "  PHOENIX_MCP_URL=${URL}/mcp"
echo "  PHOENIX_MCP_SERVICE_KEY=${MCP_SERVICE_API_KEY}"
echo ""
echo "Secret Manager (project ${PROJECT}):"
echo "  ${SECRET_PHOENIX_API_KEY}"
echo "  ${SECRET_MCP_SERVICE_KEY}"
