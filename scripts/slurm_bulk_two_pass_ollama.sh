#!/bin/bash
#SBATCH --job-name=rmap_bulk_2pass
#SBATCH --output=/beegfs/homes/pwiesenbach/rmap-chatbot/reports/slurm/rmap_bulk_2pass_%j.log
#SBATCH --partition=gpu
#SBATCH --gres=gpu:hopper:1
#SBATCH --nodelist=gpu-g5-1
#SBATCH --mem=32G

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.secrets/dify_console.env}"
SESSION_FILE="${SESSION_FILE:-$REPO_ROOT/.secrets/dify_console_session.env}"

# Target dataset for the user-created test KB.
DATASET_ID="${DATASET_ID:-5a231cec-21bf-40b9-86c8-87b9d01bca74}"

# Force local Ollama runtime on the SLURM node for metadata/title extraction.
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_START_LOCAL="${OLLAMA_START_LOCAL:-true}"
OLLAMA_PULL="${OLLAMA_PULL:-true}"
OLLAMA_LOG_DIR="${OLLAMA_LOG_DIR:-$REPO_ROOT/reports/slurm}"
OLLAMA_LOG="$OLLAMA_LOG_DIR/ollama_rmap_bulk_${SLURM_JOB_ID:-local}.log"

BAML_OLLAMA_BASE_URL="${BAML_OLLAMA_BASE_URL:-http://${OLLAMA_HOST}/v1}"
BAML_OLLAMA_MODEL="${BAML_OLLAMA_MODEL:-qwen3:32b}"
AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="${AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK:-true}"
TITLE_EXTRACTION_ENABLE_LLM_FALLBACK="${TITLE_EXTRACTION_ENABLE_LLM_FALLBACK:-true}"
AUTHOR_EXTRACTION_TRACE="${AUTHOR_EXTRACTION_TRACE:-true}"

TRACE_LOG_DIR="${TRACE_LOG_DIR:-$REPO_ROOT/reports/slurm}"
TRACE_LOG="$TRACE_LOG_DIR/rmap_bulk_2pass_runtime_${SLURM_JOB_ID:-local}.log"

mkdir -p "$TRACE_LOG_DIR"
mkdir -p "$OLLAMA_LOG_DIR"
cd "$REPO_ROOT"

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
  echo "ERROR: python interpreter not found at $REPO_ROOT/.venv/bin/python"
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if [[ -f "$SESSION_FILE" ]]; then
  set -a
  source "$SESSION_FILE"
  set +a
fi

if [[ -n "${DIFY_DATASET_API_KEY:-}" ]]; then
  if [[ "${DIFY_DATASET_API_KEY}" != dataset-* ]]; then
    echo "ERROR: DIFY_DATASET_API_KEY must start with 'dataset-'."
    exit 1
  fi
elif [[ -n "${DIFY_API_KEY:-}" ]]; then
  if [[ "${DIFY_API_KEY}" == dataset-* ]]; then
    export DIFY_DATASET_API_KEY="$DIFY_API_KEY"
  else
    echo "WARN: Ignoring DIFY_API_KEY because it is not a dataset key."
    unset DIFY_API_KEY
  fi
fi

export DATASET_ID
export OLLAMA_HOST
export BAML_OLLAMA_BASE_URL
export BAML_OLLAMA_MODEL
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK
export TITLE_EXTRACTION_ENABLE_LLM_FALLBACK
export AUTHOR_EXTRACTION_TRACE
export PYTHONUNBUFFERED=1

OLLAMA_PID=""
if [[ "$OLLAMA_START_LOCAL" == "true" ]]; then
  echo "Starting local ollama serve on ${OLLAMA_HOST}" | tee -a "$TRACE_LOG"
  ollama serve > "$OLLAMA_LOG" 2>&1 &
  OLLAMA_PID=$!
fi

cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
    wait "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

READY=0
for _ in {1..90}; do
  if curl --silent --fail --output /dev/null "http://${OLLAMA_HOST}/api/tags"; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "ERROR: local ollama server did not become ready at ${OLLAMA_HOST}" | tee -a "$TRACE_LOG"
  echo "ollama_log=$OLLAMA_LOG" | tee -a "$TRACE_LOG"
  exit 1
fi

if [[ "$OLLAMA_PULL" == "true" ]]; then
  echo "Ensuring model is available: $BAML_OLLAMA_MODEL" | tee -a "$TRACE_LOG"
  ollama pull "$BAML_OLLAMA_MODEL" | tee -a "$TRACE_LOG"
fi

echo "===== RMAP BULK TWO-PASS =====" | tee -a "$TRACE_LOG"
echo "job_id=${SLURM_JOB_ID:-local} node=$(hostname)" | tee -a "$TRACE_LOG"
echo "folder=$FOLDER" | tee -a "$TRACE_LOG"
echo "dataset_id=$DATASET_ID" | tee -a "$TRACE_LOG"
echo "ollama_host=$OLLAMA_HOST" | tee -a "$TRACE_LOG"
echo "ollama_log=$OLLAMA_LOG" | tee -a "$TRACE_LOG"
echo "baml_base_url=$BAML_OLLAMA_BASE_URL" | tee -a "$TRACE_LOG"
echo "baml_model=$BAML_OLLAMA_MODEL" | tee -a "$TRACE_LOG"
echo "author_llm_fallback=$AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK" | tee -a "$TRACE_LOG"
echo "title_llm_fallback=$TITLE_EXTRACTION_ENABLE_LLM_FALLBACK" | tee -a "$TRACE_LOG"
echo "author_trace=$AUTHOR_EXTRACTION_TRACE" | tee -a "$TRACE_LOG"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$TRACE_LOG"

echo "===== PREFLIGHT: single-file metadata extraction =====" | tee -a "$TRACE_LOG"
"$REPO_ROOT/.venv/bin/python" - <<'PY' 2>&1 | tee -a "$TRACE_LOG"
import os
from dify_uploader.metadata import extract_metadata

folder = os.environ.get("PDF_FOLDER") or "./RMaP papers first funding period"
files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pdf')])
if not files:
    raise SystemExit("No PDF files found for preflight")

sample = files[0]
path = os.path.join(folder, sample)
print(f"PREFLIGHT_FILE={path}")
meta = extract_metadata(sample, path, use_hybrid_pipeline=True)
print("PREFLIGHT_METADATA=", meta)
PY

echo "===== BULK RUN =====" | tee -a "$TRACE_LOG"
"$REPO_ROOT/.venv/bin/python" -m dify_uploader bulk-two-pass --folder "$FOLDER" 2>&1 | tee -a "$TRACE_LOG"

echo "end=$(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$TRACE_LOG"
echo "runtime_log=$TRACE_LOG" | tee -a "$TRACE_LOG"
