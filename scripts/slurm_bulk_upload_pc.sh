#!/bin/bash
#SBATCH --job-name=rmap_bulk_pc
#SBATCH --output=logs/slurm/rmap_bulk_pc_%j.out
#SBATCH --partition=medium
#SBATCH --mem=4G

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/pwiesenbach/rmap-chatbot}"
FOLDER="${FOLDER:-$REPO_ROOT/RMaP papers first funding period}"
DATASET_ID="${DATASET_ID:-65b46261-2c5e-48e9-8de4-3ca0785281e3}"
SKIP_FILE="${SKIP_FILE:-Helm M, Motorin Y, 2021, WIREs RNA .pdf}"

cd "$REPO_ROOT"

echo "===== BULK UPLOAD TO PARENT-CHILD DATASET ====="
echo "dataset_id=$DATASET_ID"
echo "start=$(date '+%Y-%m-%d %H:%M:%S')"

count=0; total=0; errors=0

for pdf in "$FOLDER"/*.pdf; do
    total=$((total + 1))
    filename=$(basename "$pdf")
    [[ "$filename" == "$SKIP_FILE" ]] && { echo "[$total] SKIP: $filename"; continue; }
    echo "[$total] UPLOAD: $filename"
    count=$((count + 1))

    DATASET_ID="$DATASET_ID" \
    DIFY_API_URL="${DIFY_API_URL:-http://rmap-chatbot-demo-dify/v1}" \
    DIFY_DATASET_API_KEY="${DIFY_DATASET_API_KEY:-}" \
    "$REPO_ROOT/.venv/bin/python" -c "
import os, sys, json, requests, time

fp = sys.argv[1]; fn = sys.argv[2]
ds = os.environ['DATASET_ID']
au = os.environ['DIFY_API_URL'].rstrip('/')
ak = os.environ['DIFY_DATASET_API_KEY']
url = f'{au}/datasets/{ds}/document/create-by-file'
h = {'Authorization': f'Bearer {ak}'}

with open(fp, 'rb') as f:
    files = {
        'file': (fn, f, 'application/pdf'),
        'data': (None, json.dumps({
            'indexing_technique': 'high_quality',
            'doc_form': 'hierarchical_model',
            'process_rule': {
                'mode': 'custom',
                'rules': {
                    'pre_processing_rules': [
                        {'id': 'remove_extra_spaces', 'enabled': True},
                        {'id': 'remove_urls_emails', 'enabled': False},
                    ],
                    'segmentation': {
                        'separator': '\n\n',
                        'max_tokens': 1000,
                    },
                    'parent_mode': 'paragraph',
                    'subchunk_segmentation': {
                        'separator': '\n',
                        'max_tokens': 200,
                        'chunk_overlap': 50,
                    },
                },
            },
        }), 'text/plain'),
    }
    r = requests.post(url, headers=h, files=files, timeout=120)
    if r.status_code in (200, 201):
        doc = r.json().get('document', {})
        did = doc.get('id')
        print(f'  OK: doc_id={did}')
        time.sleep(3)
        # Poll until completed
        su = f'{au}/datasets/{ds}/documents/{did}'
        for _ in range(48):
            time.sleep(5)
            s = requests.get(su, headers=h, params={'metadata': 'all'}, timeout=60)
            if s.status_code != 200: continue
            d = s.json()
            st = d.get('indexing_status','')
            disp = d.get('display_status','')
            if st in ('completed','error','failed'):
                segs = d.get('segment_count', 0)
                err = d.get('error', '')
                print(f'  done: status={st}, display={disp}, segments={segs}' + (f', error={err}' if err else ''))
                break
            else:
                segs = d.get('segment_count', 0)
                print(f'  ... {st} (segments={segs})')
    else:
        print(f'  FAIL: HTTP {r.status_code} - {r.text[:200]}')
        sys.exit(1)
" "$pdf" "$filename" 2>&1 || { echo "  ERROR uploading $filename"; errors=$((errors + 1)); }
done

echo ""; echo "===== DONE ====="
echo "total=$total, uploaded=$count, errors=$errors"
echo "end=$(date '+%Y-%m-%d %H:%M:%S')"
