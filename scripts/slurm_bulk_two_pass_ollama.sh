#!/bin/bash
#SBATCH --job-name=rmap_bulk_2pass
#SBATCH --output=/beegfs/homes/pwiesenbach/rmap-chatbot/reports/slurm/rmap_bulk_2pass_%j.log
#SBATCH --partition=gpu
#SBATCH --gres=gpu:ampere:1
#SBATCH --nodelist=gpu-g4-1
#SBATCH --mem=32G

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.secrets/dify_console.env}"
SESSION_FILE="${SESSION_FILE:-$REPO_ROOT/.secrets/dify_console_session.env}"

OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}"
OLLAMA_LOG_DIR="${OLLAMA_LOG_DIR:-$REPO_ROOT/reports/slurm}"
OLLAMA_LOG="$OLLAMA_LOG_DIR/ollama_rmap_bulk_${SLURM_JOB_ID:-local}.log"

# Model used by hybrid metadata extraction fallback.
BAML_OLLAMA_MODEL="${BAML_OLLAMA_MODEL:-qwen3:32b}"
AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="${AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK:-true}"
OLLAMA_PULL="${OLLAMA_PULL:-true}"

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

export OLLAMA_HOST
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-1h}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-128000}"

export BAML_OLLAMA_BASE_URL="http://${OLLAMA_HOST}/v1"
export BAML_OLLAMA_MODEL
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK

ollama serve > "$OLLAMA_LOG" 2>&1 &
OLLAMA_PID=$!

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
  echo "ERROR: ollama server did not become ready"
  echo "See: $OLLAMA_LOG"
  exit 1
fi

if [[ "$OLLAMA_PULL" == "true" ]]; then
  echo "Ensuring model is available: $BAML_OLLAMA_MODEL"
  ollama pull "$BAML_OLLAMA_MODEL"
fi

echo "===== RMAP BULK TWO-PASS (SLURM) ====="
echo "job_id=${SLURM_JOB_ID:-local} node=$(hostname)"
echo "folder=$FOLDER"
echo "ollama_host=$OLLAMA_HOST model=$BAML_OLLAMA_MODEL"
echo "llm_fallback=$AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')"

"$REPO_ROOT/.venv/bin/python" -m dify_uploader bulk-two-pass --folder "$FOLDER"

echo "end=$(date '+%Y-%m-%d %H:%M:%S')"
