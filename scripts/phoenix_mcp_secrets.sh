#!/usr/bin/env bash
# Create or update Secret Manager secrets for Phoenix MCP (no Cloud Run deploy).
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

PHOENIX_API_KEY="${PHOENIX_API_KEY%\'}"
PHOENIX_API_KEY="${PHOENIX_API_KEY#\'}"
PHOENIX_API_KEY="${PHOENIX_API_KEY%\"}"
PHOENIX_API_KEY="${PHOENIX_API_KEY#\"}"

if [[ -z "${MCP_SERVICE_API_KEY:-}" ]]; then
  MCP_SERVICE_API_KEY="$(openssl rand -hex 24)"
  echo "Generated MCP_SERVICE_API_KEY=${MCP_SERVICE_API_KEY}"
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

gcloud services enable secretmanager.googleapis.com --project="${PROJECT}" >/dev/null
upsert_secret "${SECRET_PHOENIX_API_KEY}" "${PHOENIX_API_KEY}"
upsert_secret "${SECRET_MCP_SERVICE_KEY}" "${MCP_SERVICE_API_KEY}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for name in "${SECRET_PHOENIX_API_KEY}" "${SECRET_MCP_SERVICE_KEY}"; do
  gcloud secrets add-iam-policy-binding "${name}" \
    --project="${PROJECT}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet >/dev/null
done

echo "Secrets ready in project ${PROJECT} for Cloud Run SA ${RUNTIME_SA}"
