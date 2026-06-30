#!/bin/bash
#SBATCH --job-name=rmap_meta_extract
#SBATCH --output=logs/slurm/rmap_meta_extract_%j.out
#SBATCH --partition=gpu
#SBATCH --gres=gpu:hopper:1
#SBATCH --nodelist=gpu-g5-1
#SBATCH --mem=32G

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
OUTPUT_FILE="${OUTPUT_FILE:-$REPO_ROOT/reports/metadata_dump_$(date '+%Y-%m-%d').json}"

# Local Ollama for title extraction via baml
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_START_LOCAL="${OLLAMA_START_LOCAL:-true}"
OLLAMA_PULL="${OLLAMA_PULL:-true}"
OLLAMA_LOG_DIR="${OLLAMA_LOG_DIR:-$REPO_ROOT/logs/slurm}"
OLLAMA_LOG="$OLLAMA_LOG_DIR/ollama_meta_extract_${SLURM_JOB_ID:-local}.log"

BAML_OLLAMA_BASE_URL="${BAML_OLLAMA_BASE_URL:-http://${OLLAMA_HOST}/v1}"
BAML_OLLAMA_MODEL="${BAML_OLLAMA_MODEL:-qwen3:32b}"
AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="${AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK:-true}"
TITLE_EXTRACTION_ENABLE_LLM_FALLBACK="${TITLE_EXTRACTION_ENABLE_LLM_FALLBACK:-true}"
AUTHOR_EXTRACTION_TRACE="${AUTHOR_EXTRACTION_TRACE:-true}"

export OLLAMA_HOST BAML_OLLAMA_BASE_URL BAML_OLLAMA_MODEL
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK TITLE_EXTRACTION_ENABLE_LLM_FALLBACK AUTHOR_EXTRACTION_TRACE
export PYTHONUNBUFFERED=1

mkdir -p "$(dirname "$OUTPUT_FILE")"
mkdir -p "$OLLAMA_LOG_DIR"
cd "$REPO_ROOT"

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
  echo "ERROR: python interpreter not found at $REPO_ROOT/.venv/bin/python"
  exit 1
fi

# ── Start local Ollama ──────────────────────────────────────────────
OLLAMA_PID=""
if [[ "$OLLAMA_START_LOCAL" == "true" ]]; then
  echo "Starting local ollama serve on ${OLLAMA_HOST}" | tee -a "$OUTPUT_FILE.log"
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
  echo "ERROR: local ollama server did not become ready at ${OLLAMA_HOST}"
  exit 1
fi

if [[ "$OLLAMA_PULL" == "true" ]]; then
  echo "Ensuring model is available: $BAML_OLLAMA_MODEL"
  ollama pull "$BAML_OLLAMA_MODEL"
fi

# ── Extract metadata for all PDFs ───────────────────────────────────
echo "===== METADATA EXTRACTION ====="
echo "folder=$FOLDER"
echo "output=$OUTPUT_FILE"
echo "ollama_model=$BAML_OLLAMA_MODEL"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')"

"$REPO_ROOT/.venv/bin/python" -c '
import json, os, sys, time
from dify_uploader.metadata import extract_metadata

folder = os.environ.get("FOLDER", "RMaP papers first funding period")
output_file = os.environ.get("OUTPUT_FILE", "reports/metadata_dump.json")

files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
print(f"PDFs found: {len(files)}")

results = []
errors = []
start = time.time()

for i, fn in enumerate(files):
    fp = os.path.join(folder, fn)
    print(f"[{i+1}/{len(files)}] {fn}")
    try:
        meta = extract_metadata(fn, fp, use_hybrid_pipeline=True)
        meta["_filename"] = fn
        meta["_filepath"] = fp
        results.append(meta)
        t = meta.get("title", "")
        a = meta.get("authors", "")
        y = meta.get("year", "")
        j = meta.get("journal", "")
        print("  title:", t[:100])
        print("  authors:", a[:100])
        print(f"  year: {y}, journal: {j}")
    except Exception as e:
        print(f"  ERROR: {e}")
        errors.append({"filename": fn, "error": str(e)})

elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s ({elapsed/len(files):.1f}s per PDF)")

output = {"extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(files),
          "successful": len(results), "errors": len(errors),
          "results": results, "error_details": errors}

os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Saved {len(results)} metadata entries to {output_file}")
if errors:
    print(f"Errors: {len(errors)}")
    for e in errors:
        print(f"  - {e['filename']}: {e['error']}")
' 2>&1 | tee "$OUTPUT_FILE.log"

echo ""
echo "===== DONE ====="
echo "output=$OUTPUT_FILE"
echo "end=$(date '+%Y-%m-%d %H:%M:%S')"
