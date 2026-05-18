#!/bin/bash

#SBATCH --job-name=author-baseline
#SBATCH --output=/home/pwiesenbach/rmap-chatbot/slurm/%x_%j.log
#SBATCH --partition=medium
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G

set -euo pipefail

cd /home/pwiesenbach/rmap-chatbot

export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="false"
export TITLE_EXTRACTION_ENABLE_LLM_FALLBACK="false"

echo "[run] author quality report baseline (regex only)"
poetry run python -m dify_uploader author-quality \
  --folder "RMaP papers first funding period" \
  --output "reports/author_quality_report_baseline_${SLURM_JOB_ID:-local}.csv"

echo "[done] baseline report created"
