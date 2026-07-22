#!/bin/bash
#SBATCH --job-name=rmap_meta_32b
#SBATCH --output=/beegfs/homes/pwiesenbach/rmap-chatbot/reports/slurm/rmap_meta_32b_%j.log
#SBATCH --partition=gpu
#SBATCH --gres=gpu:hopper:1
#SBATCH --nodelist=gpu-g5-1
#SBATCH --mem=32G
#SBATCH --time=02:00:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
OUTPUT_FILE="$REPO_ROOT/reports/metadata_dump_32b_$(date '+%Y-%m-%d').json"

# Local Ollama for extraction
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_LOG_DIR="$REPO_ROOT/reports/slurm"
OLLAMA_LOG="$OLLAMA_LOG_DIR/ollama_meta_32b_${SLURM_JOB_ID:-local}.log"

export BAML_OLLAMA_BASE_URL="http://${OLLAMA_HOST}/v1"
export BAML_OLLAMA_MODEL="qwen3:32b"
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK=true
export TITLE_EXTRACTION_ENABLE_LLM_FALLBACK=true
export AUTHOR_EXTRACTION_TRACE=false
export PYTHONUNBUFFERED=1

mkdir -p "$(dirname "$OUTPUT_FILE")"
mkdir -p "$OLLAMA_LOG_DIR"
cd "$REPO_ROOT"

echo "===== METADATA EXTRACTION (32B) ====="
echo "job_id=${SLURM_JOB_ID:-local} node=$(hostname)"
echo "folder=$FOLDER"
echo "output=$OUTPUT_FILE"
echo "ollama_model=$BAML_OLLAMA_MODEL"
echo "ollama_log=$OLLAMA_LOG"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')"

# ── Start local Ollama ──────────────────────────────────────────────
echo "Starting local ollama serve..."
ollama serve > "$OLLAMA_LOG" 2>&1 &
OLLAMA_PID=$!

cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
    wait "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Wait for Ollama to be ready
READY=0
for _ in {1..90}; do
  if curl --silent --fail --output /dev/null "http://${OLLAMA_HOST}/api/tags"; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -ne 1 ]]; then
  echo "ERROR: ollama did not become ready"
  exit 1
fi

echo "Pulling model: $BAML_OLLAMA_MODEL"
ollama pull "$BAML_OLLAMA_MODEL"

# ── Run extraction ──────────────────────────────────────────────────
echo "Running extraction..."
"$REPO_ROOT/.venv/bin/python" -c '
import json, os, time
from dify_uploader.metadata import extract_metadata

folder = os.environ.get("FOLDER", "RMaP papers first funding period")
output_file = os.environ.get("OUTPUT_FILE", "reports/metadata_dump_32b.json")

files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
print(f"PDFs found: {len(files)}")

results = []
errors = []
pubmed = 0
crossref = 0
llm = 0
fallback = 0
start = time.time()

for i, fn in enumerate(files):
    fp = os.path.join(folder, fn)
    meta = extract_metadata(fn, fp, use_hybrid_pipeline=True)
    
    has_pmid = bool(meta.get("pmid"))
    has_doi = bool(meta.get("doi"))
    has_llm = meta.get("title") != fn.replace(".pdf", "").strip()
    
    if has_pmid:
        pubmed += 1
        src = "PUBMED"
    elif has_doi:
        crossref += 1
        src = "CROSSREF"
    elif has_llm and meta.get("authors") != "Unknown":
        llm += 1
        src = "LLM"
    else:
        fallback += 1
        src = "FALLBACK"
    
    meta["_filename"] = fn
    meta["_filepath"] = fp
    meta["_source"] = src
    results.append(meta)
    
    t = meta.get("title", "")[:80]
    a = meta.get("authors", "")[:80]
    print(f"[{i+1}/{len(files)}] {src} {fn[:50]}")
    print(f"  title: {t}")
    print(f"  authors: {a}")

elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s ({elapsed/len(files):.1f}s per PDF)")
print(f"PubMed: {pubmed}, CrossRef: {crossref}, LLM: {llm}, Fallback: {fallback}")

output = {
    "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "total": len(files),
    "successful": len(results),
    "errors": len(errors),
    "pubmed": pubmed,
    "crossref": crossref,
    "llm": llm,
    "fallback": fallback,
    "results": results,
    "error_details": errors,
}

os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"Saved to {output_file}")
'

echo ""
echo "===== DONE ====="
echo "output=$OUTPUT_FILE"
echo "end=$(date '+%Y-%m-%d %H:%M:%S')"
