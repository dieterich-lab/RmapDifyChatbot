#!/bin/bash

#SBATCH --job-name=author-baml-qwen32-g3
#SBATCH --output=/home/pwiesenbach/rmap-chatbot/slurm/%x_%j.log
#SBATCH --partition=gpu
#SBATCH --nodelist=gpu-g3-1
#SBATCH --gres=gpu:turing:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G

set -euo pipefail

cd /home/pwiesenbach/rmap-chatbot

MODEL="${OLLAMA_MODEL:-qwen3:32b}"
DEFAULT_OLLAMA_PORT=$((11434 + (${SLURM_JOB_ID:-0} % 1000)))
export OLLAMA_PORT="${OLLAMA_PORT:-$DEFAULT_OLLAMA_PORT}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:${OLLAMA_PORT}}"
export BAML_OLLAMA_BASE_URL="${BAML_OLLAMA_BASE_URL:-http://127.0.0.1:${OLLAMA_PORT}/v1}"
export BAML_OLLAMA_MODEL="${BAML_OLLAMA_MODEL:-$MODEL}"
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="true"

OLLAMA_LOG="/home/pwiesenbach/rmap-chatbot/slurm/ollama_${SLURM_JOB_ID:-local}.log"
OLLAMA_PID=""

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama command not found"
  exit 1
fi

ollama serve > "$OLLAMA_LOG" 2>&1 &
OLLAMA_PID=$!

cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
    echo "[cleanup] stopping ollama pid=$OLLAMA_PID"
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
    wait "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

ready=0
for i in {1..60}; do
  if curl --silent --fail --output /dev/null "http://${OLLAMA_HOST}/api/tags" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: ollama did not become ready in time"
  echo "see log: $OLLAMA_LOG"
  exit 1
fi

echo "[ollama] pulling model: $MODEL"
ollama pull "$MODEL"

echo "[baml] generating client"
./scripts/generate_baml_client.sh

echo "[run] author quality report with LLM fallback"
poetry run python -m dify_uploader author-quality \
  --folder "RMaP papers first funding period" \
  --output "reports/author_quality_report_with_baml_g3_${SLURM_JOB_ID:-local}.csv"

echo "[done] report created"
