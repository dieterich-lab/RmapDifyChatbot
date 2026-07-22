#!/bin/bash
#SBATCH --job-name=rmap_meta_q32b
#SBATCH --output=/beegfs/homes/pwiesenbach/rmap-chatbot/reports/slurm/rmap_meta_q32b_%j.log
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodelist=gpu-g3-1
#SBATCH --mem=32G
#SBATCH --time=03:00:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
OUTPUT_FILE="$REPO_ROOT/reports/metadata_dump_2026-07-22_qwen32b.json"

OLLAMA_HOST="127.0.0.1:11434"
OLLAMA_MODEL="qwen3:32b"
OLLAMA_LOG_DIR="$REPO_ROOT/reports/slurm"
OLLAMA_LOG="$OLLAMA_LOG_DIR/ollama_meta_q32b_${SLURM_JOB_ID:-local}.log"

export BAML_OLLAMA_BASE_URL="http://${OLLAMA_HOST}/v1"
export BAML_OLLAMA_MODEL="$OLLAMA_MODEL"
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK=true
export TITLE_EXTRACTION_ENABLE_LLM_FALLBACK=true
export AUTHOR_EXTRACTION_TRACE=true
export PYTHONUNBUFFERED=1

mkdir -p "$(dirname "$OUTPUT_FILE")"
mkdir -p "$OLLAMA_LOG_DIR"
cd "$REPO_ROOT"

# ── Start local Ollama ──────────────────────────────────────────────
echo "Starting local ollama serve on ${OLLAMA_HOST}" 
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
for _ in {1..120}; do
  if curl --silent --fail --output /dev/null "http://${OLLAMA_HOST}/api/tags"; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "ERROR: local ollama server did not become ready at ${OLLAMA_HOST}"
  echo "ollama_log=$OLLAMA_LOG"
  exit 1
fi

echo "Pulling model: $OLLAMA_MODEL"
ollama pull "$OLLAMA_MODEL"

# ── Extract metadata ────────────────────────────────────────────────
echo "===== METADATA EXTRACTION (qwen3:32b) ====="
echo "folder=$FOLDER"
echo "output=$OUTPUT_FILE"
echo "ollama_model=$OLLAMA_MODEL"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')"

source "$REPO_ROOT/.venv/bin/activate"

python3 -c '
import json, os, sys, time
from collections import Counter
from dify_uploader.metadata import extract_metadata

folder = os.environ.get("FOLDER", "RMaP papers first funding period")
output_file = os.environ.get("OUTPUT_FILE", "reports/metadata_dump.json")

files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
print(f"PDFs found: {len(files)}")

results = []
errors = []
source_counts = Counter()
start = time.time()

for i, fn in enumerate(files):
    fp = os.path.join(folder, fn)
    meta = extract_metadata(fn, fp, use_hybrid_pipeline=True)
    
    # Determine source
    has_pmid = bool(meta.get("pmid"))
    has_doi = bool(meta.get("doi"))
    has_llm = not has_pmid and meta.get("title") != fn.replace(".pdf", "").strip()
    
    if has_pmid:
        src = "pubmed"
    elif has_doi:
        src = "crossref"
    elif has_llm:
        src = "llm_qwen32b"
    else:
        src = "fallback"
    
    source_counts[src] += 1
    meta["_filename"] = fn
    meta["_filepath"] = fp
    meta["_source"] = src
    results.append(meta)
    
    pad = len(str(len(files)))
    print(f"[{str(i+1).rjust(pad)}/{len(files)}] {src:15s} {fn[:60]}")
    print(f"  title: {meta.get('title','')[:100]}")
    print(f"  authors: {meta.get('authors','')[:100]}")

elapsed = time.time() - start
print()
print(f"Done in {elapsed:.0f}s ({elapsed/len(files):.1f}s per PDF)")
for src, count in source_counts.most_common():
    print(f"  {src}: {count}")

output = {
    "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "total": len(files),
    "successful": len(results),
    "errors": len(errors),
    "source_counts": dict(source_counts),
    "model": os.environ.get("BAML_OLLAMA_MODEL", "unknown"),
    "results": results,
    "error_details": errors,
}

os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Saved {len(results)} entries to {output_file}")
if errors:
    print(f"Errors: {len(errors)}")
    for e in errors[:10]:
        print(f"  - {e[\"filename\"]}: {e[\"error\"]}")
'

echo ""
echo "===== DONE ====="
echo "output=$OUTPUT_FILE"
echo "end=$(date '+%Y-%m-%d %H:%M:%S')"
