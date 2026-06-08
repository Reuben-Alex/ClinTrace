.PHONY: setup run run-adk ui lint clean verify verify-full download-nhamcs build-rvc-codebook stress-test prep-bq reload-bq phoenix-mcp-secrets deploy-phoenix-mcp deploy-agent deploy-ui deploy-all test test-integration

setup:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,verification,gcp]"

run:
	. .venv/bin/activate && python -m clintrace_agent.main

run-adk:
	. .venv/bin/activate && adk web .

ui:
	. .venv/bin/activate && uvicorn ui.app:app --reload --port 8080

download-nhamcs:
	. .venv/bin/activate && python scripts/download_nhamcs.py --years 2022

build-rvc-codebook:
	. .venv/bin/activate && python scripts/build_rvc_codebook.py

verify:
	. .venv/bin/activate && python -m verification.run_verification --n_samples 50 --output results_nhamcs_50.csv --run-evals --log-phoenix

verify-full:
	. .venv/bin/activate && python -m verification.run_verification --n_samples 200 --output results_nhamcs_200.csv --delay 1.5 --run-evals --run-diag-eval --log-phoenix

stress-test:
	. .venv/bin/activate && python -m verification.stress_test --n_samples 100

prep-bq:
	. .venv/bin/activate && python scripts/prep_for_bigquery.py

reload-bq: prep-bq
	bq load --replace \
	  --source_format=NEWLINE_DELIMITED_JSON \
	  --schema=data/bq_ready/schema.json \
	  black-tenure-439907-v8:clinictrace.ed_triage \
	  data/bq_ready/combined.ndjson

phoenix-mcp-secrets:
	chmod +x scripts/phoenix_mcp_secrets.sh && ./scripts/phoenix_mcp_secrets.sh

deploy-phoenix-mcp:
	chmod +x scripts/deploy_phoenix_mcp.sh && ./scripts/deploy_phoenix_mcp.sh

# Deploy ClinTrace to Vertex AI Agent Engine (same pattern as deploy-it-incident).
# Example:
#   make deploy-agent SET_ENV="PHOENIX_MCP_URL=https://....run.app/mcp,PHOENIX_MCP_FEEDBACK=true"
CLINICTRACE_DEPLOY_ENV ?= GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_PROJECT_ID=black-tenure-439907-v8,CLINICTRACE_VERTEX_LOCATION=global,CLINICTRACE_MODEL=gemini-3.5-flash,GEMINI_EVAL_MODEL=gemini-3.5-flash,INLINE_SKILLS=true,MERGE_TRIAGE_LLM_STEPS=true,FAST_TRIAGE=true,PHOENIX_MCP_FEEDBACK=true,DISABLE_PHOENIX_MCP=false,PHOENIX_PROJECT_NAME=clinictrace,PHOENIX_PROJECT_ID=UHJvamVjdDo0,PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/reubenalexa,PHOENIX_MCP_URL=https://clinictrace-phoenix-mcp-jqun66rm2a-uc.a.run.app/mcp
CLINICTRACE_DEPLOY_SECRETS ?= PHOENIX_API_KEY=clinictrace-phoenix-api-key:latest,PHOENIX_MCP_SERVICE_KEY=clinictrace-mcp-service-api-key:latest

deploy-ui:
	chmod +x scripts/deploy_ui.sh && ./scripts/deploy_ui.sh

deploy-all: deploy-phoenix-mcp deploy-agent deploy-ui

# Display name must be quoted in the recipe — parentheses break Make variable parsing.
deploy-agent:
	. .venv/bin/activate && \
	python -m clintrace_agent.app_utils.deploy \
		--display-name='ClinTrace Triage Agent (clintrace_agent)' \
		--source-packages=clintrace_agent \
		--entrypoint-module=clintrace_agent.agent_engine_app \
		--entrypoint-object=agent_engine \
		--requirements-file=clintrace_agent/requirements.txt \
		--set-env-vars="$(or $(SET_ENV),$(CLINICTRACE_DEPLOY_ENV))" \
		--set-secrets="$(or $(SECRETS),$(CLINICTRACE_DEPLOY_SECRETS))" \
		$(if $(AGENT_IDENTITY),--agent-identity) \
		$(if $(DRY_RUN),--dry-run)

lint:
	. .venv/bin/activate && ruff check .

test:
	. .venv/bin/activate && pytest tests/ -m "not integration" -q

test-integration:
	. .venv/bin/activate && pytest tests/ -m integration -q

clean:
	rm -rf .venv __pycache__ *.egg-info .pytest_cache agent_tmp*
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
