# rmap-chatbot

Utility scripts for uploading documents to Dify knowledge datasets, applying metadata, and running ingestion diagnostics.

## Dify Auth (API-Key First)

For Dify console import automation, use `DIFY_CONSOLE_API_KEY` as the default auth mode.

Note: some self-hosted deployments expose only app API keys (for `/v1/...`) and no dedicated console API key for `/console/api/...`.
In that case, imports must use session cookie + CSRF fallback.

Example:

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_API_KEY="<console_api_key>" \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Meta Routing.yml" --app-id "<app_id>"
```

Cookie auth is still supported as an explicit fallback only:

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_COOKIE="..." \
DIFY_CSRF_TOKEN="..." \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Meta Routing.yml" --allow-cookie-auth
```

Draft routing debug (API key preferred):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_API_KEY="<console_api_key>" \
scripts/debug_route_draft.sh \
	--app-id "<app_id>" \
	--query "What are the main methods and findings of Sci-ModoM?" \
	--query "Wie viele Papiere hat Christoph Dieterich veroeffentlicht?" \
	--query "Which papers have been (co-) authored by Christoph Dieterich?"
```

## Run

poetry run dify-upload

## CLI

Show help:

poetry run dify-upload --help

Run default workflow:

poetry run dify-upload default

Run two-pass workflow with explicit file:

poetry run dify-upload two-pass --file "RMaP papers first funding period/your-file.pdf"

Run A/B/C diagnostics:

poetry run dify-upload abc-test --file "RMaP papers first funding period/your-file.pdf"

Preview extracted metadata:

poetry run dify-upload metadata --file "RMaP papers first funding period/your-file.pdf"

Run only selected authors (default: Mark Helm, Christoph Dieterich):

poetry run dify-upload selected-authors

Run full bulk upload for all PDFs with hybrid metadata extraction:

poetry run dify-upload bulk-two-pass --folder "RMaP papers first funding period"

Override selected authors and folder:

poetry run dify-upload selected-authors --author "Mark Helm" --author "Christoph Dieterich" --folder "RMaP papers first funding period"

Create an author extraction quality CSV report:

poetry run dify-upload author-quality --folder "RMaP papers first funding period"

Limit number of files and custom output path:

poetry run dify-upload author-quality --folder "RMaP papers first funding period" --max-files 30 --output reports/author_quality_report_30.csv

## Hybrid Author Extraction (Regex + BAML)

The extractor in `dify_uploader/author_extraction.py` now uses a hybrid strategy:

1. Fast regex/heuristic extraction.
2. If the result looks low-confidence (e.g. too noisy, too few/many names), fallback to BAML structured output.

### BAML setup

Set runtime environment (example local defaults):

export BAML_OLLAMA_BASE_URL="http://127.0.0.1:11434/v1"
export BAML_OLLAMA_MODEL="qwen3:32b"
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="true"

Generate BAML Python client from `dify_uploader/baml_src`:

./scripts/generate_baml_client.sh

### Run quality report with hybrid extraction

AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK=true poetry run dify-upload author-quality --folder "RMaP papers first funding period" --output reports/author_quality_report_with_baml.csv

### Slurm (start Ollama + run report)

Submit:

sbatch slurm/author-extraction-baml-qwen32.sbatch

The job script will:

1. Start `ollama serve` on a per-job port.
2. Pull `qwen3:32b`.
3. Generate BAML client.
4. Run the author-quality report with LLM fallback enabled.

Example runner/wrapper command:

poetry run dify-upload-selected
