# RmapDifyChatbot

RmapDifyChatbot is a production-oriented Python project for operating a Dify-based
academic assistant with explicit metadata routing.

## Status Snapshot (2026-06-19)

1. Two-turn workflow validated end-to-end on all 6 Dieterich papers (Turn 1: 79 s, Turn 2: 214 s).
2. Turn 2 uses a single Metadata LLM call for all papers (Paper Map LLM removed from iteration).
3. `doc_id` is now propagated through the full Turn-1 → Turn-2 pipeline, eliminating O(N) title lookups.
4. Paper fetch reduced to 0.4–0.9 s/paper (was ~25 s/paper with title-based pagination).
5. Structured-output extractor handoff is robust; final answer sanitizer strips `<think>` leakage.
6. `Fetch Full Paper` uses a dynamic text budget: total 48 000 chars divided equally among all papers in the iteration (`48 000 // paper_count`), so fewer papers automatically get more context (min 4 000 chars/paper).

## Overview

The project has two responsibilities:

1. Main use-case: deploy and operate a metadata-aware Dify chatbot workflow.
2. Secondary service: extract metadata from papers and upload documents into Dify datasets.

Current routing workflow (`config/RMAP Chatbot Meta Routing.yml`):

```mermaid
flowchart LR
		A[Start] --> B[Query Rewriter]
		B --> C{Question Classifier}

		C -->|Knowledge Route| D[Knowledge Retrieval]
		D --> E[Knowledge LLM]
		E --> H[Answer]

		C -->|Metadata Route| F[Parameter Extractor]
		F --> G[Metadata Router Code]
		G --> I[Metadata LLM]
		I --> H
```

Current iterative retrieval workflow (`config/RMAP Chatbot Iterative Retrieval.yml`):

20 nodes · 20 edges · Dify DSL v0.6.0 · `advanced-chat` mode · model: `gpt-oss` (Ollama, 128k context)

### Architecture

```mermaid
flowchart TD
    Start([Start]) --> QR[Query Rewriter]
    QR --> JME[JSON Metadata Extractor]
    JME --> PEP[Parse Extractor Paper List]
    PEP --> FMS[Follow-up Memory Subset]
    FMS --> RPL[Resolve Paper List]
    RPL --> IF{Paper List\nEmpty?}

    IF -->|"Yes — no paper constraints\n(open knowledge question)"| KR[Knowledge Retrieval]
    KR --> KLLM[Knowledge LLM]
    KLLM --> SAN[Final Answer Sanitizer]

    IF -->|"No — paper constraints present\n(author / title / follow-up)"| IT["Paper Iterator\n(iterates paper_list)"]

    subgraph iter ["Iteration (per paper)"]
        ITS([Iteration Start]) --> QC2[Question Classifier 2]
        QC2 -->|"IS_COUNT_OR_LIST\n(list / count / filter)"| MQ[Metadata Query]
        QC2 -->|"IS_CONTENT\n(summarise / explain)"| FF[Fetch Full Paper]
        MQ --> VA[Variable Aggregator]
        FF --> VA
    end

    IT --> iter
    iter --> IT
    IT --> UPM[Update Paper Memory]
    UPM --> PPM[Persist Paper Memory]
    PPM --> MLLM[Metadata LLM]
    MLLM --> SAN
    SAN --> ANS([Answer])
```

### Node Reference

| # | Node | Type | Purpose |
|---|---|---|---|
| 1 | **Start** | start | Entry point — receives user query and conversation context. |
| 2 | **Query Rewriter** | llm | Rewrites the query to be self-contained, resolving pronouns and references (e.g. "these papers") using `conversation.memory`. |
| 3 | **JSON Metadata Extractor** | llm | Extracts structured paper constraints (title, authors, year, journal) from the rewritten query into JSON. |
| 4 | **Parse Extractor Paper List** | code | Parses the LLM's JSON output into a clean `array[object]`. Tolerates both free-text and structured-output formats. |
| 5 | **Follow-up Memory Subset** | code | Reads `conversation.memory` and returns the relevant subset (all, newest, oldest, top-N) based on intent keywords in the query. Returns `[]` for first-turn queries. |
| 6 | **Resolve Paper List** | code | Merges `memory_subset` (follow-up) and `extracted_paper_list` (new query) into the final `paper_list`, preserving `doc_id`. |
| 7 | **IF/ELSE** | if-else | Routes to Turn-1 path (Knowledge Retrieval) if `paper_list` is empty, else to Turn-2 path (Paper Iterator). |
| 8 | **Knowledge Retrieval** | knowledge-retrieval | Hybrid vector+keyword retrieval (top-10, 70/30 weighting) against the Dify dataset. Turn-1 only. |
| 9 | **Knowledge LLM** | llm | Generates a grounded answer from retrieved chunks. Turn-1 only. |
| 10 | **Paper Iterator** | iteration | Iterates over `paper_list` items. Turn-2 only. Each item carries `{title, authors, year, journal, doc_id}`. |
| 11 | **Question Classifier 2** | question-classifier | Inside the iteration: classifies the intent as `IS_COUNT_OR_LIST` (listing/counting) or `IS_CONTENT` (summarise/explain). |
| 12 | **Metadata Query** | code | `IS_COUNT_OR_LIST` path. Searches the dataset by author/year/title metadata filters; returns a formatted `title \| authors \| year \| journal \| doc_id` string. |
| 13 | **Fetch Full Paper** | code | `IS_CONTENT` path. Uses `doc_id` directly from the iteration item for a single-call segment fetch (0.4–0.9 s/paper). Falls back to title-based lookup only if `doc_id` is absent. Applies a dynamic text budget: `chars_per_paper = max(4 000, 48 000 // paper_count)`, so the total context stays bounded at ~48 000 chars regardless of how many papers are in the iteration. |
| 14 | **Variable Aggregator** | variable-aggregator | Collects outputs from `Metadata Query` (`result_text`) and `Fetch Full Paper` (`paper_context`) into one string per iteration round. |
| 15 | **Update Paper Memory** | code | After the iteration: parses the aggregated output into structured paper objects and deduplicates them. |
| 16 | **Persist Paper Memory** | assigner | Writes the updated paper list to `conversation.memory` (scoped to the conversation, persisted across turns). |
| 17 | **Metadata LLM** | llm | Single combined LLM call for all papers. Given the aggregated paper texts, produces a global synthesis and per-paper summary (method / key finding / implication). `num_ctx=24576`, `max_tokens=4000`. |
| 18 | **Final Answer Sanitizer** | code | Strips `<think>…</think>` blocks from both Knowledge LLM and Metadata LLM outputs and concatenates them. |
| 19 | **Answer** | answer | Emits `cleaned_text` as the final conversational response. |

**Key design decisions**

- **`doc_id` passthrough**: `conversation.memory` stores `doc_id` alongside each paper entry (written by `Metadata Query` in Turn 1). `Follow-up Memory Subset` and `Resolve Paper List` preserve `doc_id` through `_clean_obj`, so `Fetch Full Paper` can call the segments API directly — no pagination, no title matching.
- **Single Metadata LLM call**: all paper texts are aggregated by the `Variable Aggregator` inside the iteration; one combined LLM call (outside the loop) produces the cross-paper synthesis and summaries, rather than one LLM call per paper.
- **Dynamic context budget**: `Resolve Paper List` outputs `paper_count`; `Fetch Full Paper` receives it as an input variable and computes `chars_per_paper = max(4 000, 48 000 // paper_count)`. The total text budget is fixed at 48 000 chars and distributed equally: 6 papers → 8 000 chars each, 3 papers → 16 000 chars each, 1 paper → 48 000 chars. System prompt + metadata ≈ 3 000 tokens; at 6 papers the total prompt is ~15 000 tokens, fitting comfortably in `num_ctx=24576`.

---

### Two-Turn Evaluation (2026-06-19)

**Setup:** Dify app `16d50bee-bc86-4bda-bb56-a861743f3ddb` · draft run via `scripts/debug_route_draft.sh` · model `gpt-oss` on Ollama

#### Turn 1 — List all papers by Christoph Dieterich

> **Query:** "Zeige mir alle Papiere von Christoph Dieterich in der Datenbank."

**Route:** IF/ELSE (paper_list = [{authors: "Christoph Dieterich"}], not empty) → Paper Iterator → **Metadata Query** (IS_COUNT_OR_LIST)

**Time: 79 s**

**Answer:**
```
Gesamtzahl der Publikationen von Christoph Dieterich: 6

1. APOBEC2 safeguards skeletal muscle cell fate through binding chromatin and regulating
   transcription of non-muscle genes during myoblast differentiation | 2024 | PNAS
2. PEPseq quantifies transcriptome-wide changes in protein occupancy and reveals selective
   translational repression after translational stress | 2023 | Nucleic Acids Res
3. Detection of queuosine and queuosine precursors in tRNAs by direct RNA sequencing
   | 2023 | Nucleic Acids Res
4. Adaptive sampling for nanopore direct RNA-sequencing | 2023 | RNA
5. Detecting m6A at single-molecular resolution via direct RNA sequencing and realistic
   training data | 2024 | Nat Commun
6. Sci-ModoM: a quantitative database of transcriptome-wide high-throughput RNA
   modification sites | 2025 | Nucleic Acids Res
```

#### Turn 2 — Summarise all six papers

> **Query:** "Fasse jedes dieser Papiere kurz zusammen."

**Route:** IF/ELSE (paper_list = 6 items from conversation.memory, not empty) → Paper Iterator → **Fetch Full Paper** (IS_CONTENT) → Metadata LLM

**Time: 214 s** | Fetch Full Paper ×6: 0.4–0.9 s/paper | Metadata LLM: 15 260 prompt tokens · 1 388 completion tokens

**Answer:**

> **Global synthesis**
> Alle sechs Arbeiten befassen sich mit der Analyse von RNA-Biologie mittels moderner Sequenzierungstechniken, insbesondere nanopore-basierten direkten RNA-Sequenzierung und ergänzenden Methoden zur Erkennung von Protein-RNA-Interaktionen sowie epitranskriptomischen Modifikationen. Gemeinsam zeigen sie, wie gezielte Techniken (PEPseq, adaptive sampling, mAFiA) neue Einblicke in die Transkriptionsregulation, translationalen Stressantworten und tRNA-Modifikationslandschaften ermöglichen und diese Daten anschließend in zugänglichen Ressourcen (Sci-ModoM) zusammenführen.
>
> **1. APOBEC2 safeguards skeletal muscle cell fate …**
> - *Method:* Chromatin immunoprecipitation, RNA-seq, HDAC interaction assays in C2C12 cells.
> - *Key finding:* APOBEC2 binds specific promoter motifs of non-muscle genes and recruits histone deacetylase complexes to repress their transcription during muscle differentiation.
> - *Implication:* Demonstrates a novel transcriptional regulatory role for APOBEC2 that safeguards skeletal muscle cell fate.
>
> **2. PEPseq quantifies transcriptome-wide changes in protein occupancy …**
> - *Method:* 4-thiouridine labeling, NHS chemistry to pull down RNA–protein complexes, followed by sequencing (PEPseq).
> - *Key finding:* Arsenite-induced translational stress increases protein interactions on coding regions of ribosomal protein mRNAs while translation remains repressed during recovery.
> - *Implication:* Provides an unbiased platform to study post-transcriptional regulation under stress conditions.
>
> **3. Detection of queuosine and queuosine precursors in tRNAs …**
> - *Method:* Direct nanopore RNA sequencing combined with JACUSA2 analysis of synthetic, yeast, and bacterial tRNAs.
> - *Key finding:* Queuosine (Q) and its precursors preQ0/preQ1 are detectable with high accuracy on position 34 of specific tRNAs.
> - *Implication:* Enables high-throughput detection of Q modifications, advancing understanding of tRNA biology.
>
> **4. Adaptive sampling for nanopore direct RNA-sequencing**
> - *Method:* Real-time adaptive sampling (Read Until) applied to direct RNA sequencing of poly(A)+ samples from human cardiomyocytes and mouse heart.
> - *Key finding:* Efficient depletion (~2.5–2.8×) of abundant mitochondrial transcripts, improving coverage of lowly expressed RNAs.
> - *Implication:* Demonstrates the utility of adaptive sampling for targeted enrichment/depletion in transcriptome studies.
>
> **5. Detecting m6A at single-molecular resolution …**
> - *Method:* Synthetic RNA oligos with controlled m6A sites, ligated into longer molecules; trained mAFiA algorithm using RODAN features.
> - *Key finding:* Accurate single-read detection of m6A and quantitative stoichiometry in HEK293 mRNA, outperforming existing methods on synthetic benchmarks.
> - *Implication:* Provides a robust tool for high-resolution, quantitative m6A profiling in biological samples.
>
> **6. Sci-ModoM: a quantitative database …**
> - *Method:* Curated integration of >156 datasets with site-level stoichiometry and confidence scores into a FAIR-compliant database.
> - *Key finding:* Offers over six million quantified modification sites across diverse organisms and technologies.
> - *Implication:* Facilitates comparative epitranscriptomics research and promotes data interoperability.

## Installation

### Requirements

1. Python 3.11+
2. Poetry

### Setup

```bash
poetry install
poetry run dify-upload --help
```

Optional local environment file (for import/debug scripts):

```bash
source .secrets/dify_console_session.env
```

Optional persistent login secrets (for `--auto-login`):

```bash
cat > .secrets/dify_console_login.env <<'EOF'
DIFY_CONSOLE_EMAIL="you@example.org"
# Option A (recommended): base64-encoded password string
DIFY_CONSOLE_PASSWORD_B64="<base64_password>"
# Option B (alternative): plaintext password
# DIFY_CONSOLE_PASSWORD="<plaintext_password>"
DIFY_CONSOLE_LOGIN_LANGUAGE="en-US"
DIFY_CONSOLE_REMEMBER_ME="true"
EOF
chmod 600 .secrets/dify_console_login.env
```

Notes:

1. Both `scripts/import_dify_dsl.sh` and `scripts/debug_route_draft.sh` auto-load `.secrets/dify_console_login.env` when present.
2. `.secrets/` is git-ignored in this repo, so this file is not committed.
3. Prefer `DIFY_CONSOLE_PASSWORD_B64`; it avoids shell quoting pitfalls but is not cryptographic protection.

### API credential map

Use different keys for different endpoint families:

1. `DIFY_APP_API_KEY` (prefix `app-`): app runtime endpoints under `/v1` (for example `/v1/chat-messages`, `/v1/meta`).
2. `DIFY_DATASET_API_KEY` (prefix `dataset-`): dataset upload/metadata endpoints under `/v1/datasets/...` used by `dify-upload`.
3. `DIFY_CONSOLE_API_KEY`: console-management endpoints under `/console/api/...` (workflow import, draft run).
4. Cookie fallback (`DIFY_CONSOLE_COOKIE` + `DIFY_CSRF_TOKEN`): only for deployments where console API keys are not accepted.

Notes:

1. The uploader currently supports `DIFY_API_KEY` as a backward-compatible alias for `DIFY_DATASET_API_KEY`.
2. In this deployment, app keys are valid for `/v1` but not for `/console/api`.

## Main Use-Case: Set Up The Meta Routing Chatbot

### 1. Import workflow DSL into Dify

Preferred mode (console API key):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_API_KEY="<console_api_key>" \
AUTO_CONFIRM=true \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Meta Routing.yml" --app-id "<app_id>"
```

Cookie fallback (for deployments without console API key support):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_COOKIE="..." \
DIFY_CSRF_TOKEN="..." \
AUTO_CONFIRM=true \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Meta Routing.yml" --app-id "<app_id>" --allow-cookie-auth
```

Auto-login (refresh short-lived console token via `/console/api/login`):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_EMAIL="you@example.org" \
DIFY_CONSOLE_PASSWORD_B64="<base64_password>" \
AUTO_CONFIRM=true \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Meta Routing.yml" --app-id "<app_id>" --auto-login
```

### 2. Validate routing behavior

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_COOKIE="..." \
DIFY_CSRF_TOKEN="..." \
scripts/debug_route_draft.sh \
	--app-id "<app_id>" \
	--allow-cookie-auth \
	--query "What are the main methods and findings of Sci-ModoM?" \
	--query "How many papers has Christoph Dieterich published?" \
	--query "Which papers have been (co-) authored by Christoph Dieterich?"
```

Or with console API key (if supported by your deployment):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_API_KEY="<console_api_key>" \
scripts/debug_route_draft.sh \
	--app-id "<app_id>" \
	--query "What are the main methods and findings of Sci-ModoM?"
```

Or with auto-login token refresh:

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_EMAIL="you@example.org" \
DIFY_CONSOLE_PASSWORD_B64="<base64_password>" \
scripts/debug_route_draft.sh \
	--app-id "<app_id>" \
	--auto-login \
	--query "What are the main methods and findings of Sci-ModoM?"
```

Expected routes:

1. Content questions -> `Knowledge Route`
2. Count/list/filter questions -> `Metadata Route`

### 3. Cookie-free runtime check (`/v1`, app key)

Use this when you want to test the published app without console cookie/token handling.

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_APP_API_KEY="<app_key_with_app_prefix>" \
scripts/debug_route_runtime.sh \
	--query "Which papers have been (co-)authored by Christoph Dieterich?" \
	--query "Please summarize those papers."
```

Notes:

1. `scripts/debug_route_runtime.sh` uses `/v1/meta` and `/v1/chat-messages` with `Authorization: Bearer <app-key>`.
2. `/v1` executes the published app configuration, not the console draft.
3. Use `DIFY_APP_API_KEY` (recommended). `DIFY_API_KEY` is only used as a backward-compatible fallback variable.

## Main Use-Case: Iterative Retrieval Chatbot

Import the iterative workflow config (also syncs the Dify Draft automatically):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_COOKIE="..." \
DIFY_CSRF_TOKEN="..." \
AUTO_CONFIRM=true \
scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
    --app-id "<app_id>" --allow-cookie-auth
```

Run the two-turn test against the draft (no publish required):

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_COOKIE="..." \
DIFY_CSRF_TOKEN="..." \
scripts/debug_route_draft.sh \
    --app-id "<app_id>" \
    --allow-cookie-auth \
    --classifier-node-id "17786780005730" \
    --query "Zeige mir alle Papiere von Christoph Dieterich in der Datenbank." \
    --query "Fasse jedes dieser Papiere kurz zusammen."
```

Auto-login alternative:

```bash
DIFY_BASE_URL="http://your-dify-host" \
DIFY_CONSOLE_EMAIL="you@example.org" \
DIFY_CONSOLE_PASSWORD_B64="<base64_password>" \
scripts/debug_route_draft.sh \
    --app-id "<app_id>" \
    --auto-login \
    --classifier-node-id "17786780005730" \
    --query "Zeige mir alle Papiere von Christoph Dieterich in der Datenbank." \
    --query "Fasse jedes dieser Papiere kurz zusammen."
```

Notes:

1. `scripts/debug_route_draft.sh` runs against the Dify Draft via `POST /console/api/apps/{id}/advanced-chat/workflows/draft/run` — no publish step required.
2. `conversation_id` is reused automatically across multiple `--query` values in one run; use `--conversation-id "<uuid>"` to resume an existing conversation.
3. `conversation.memory` persists resolved paper entities (including `doc_id`) across turns so Turn-2 `Fetch Full Paper` can use direct segment lookup.
4. The `--classifier-node-id` flag extracts the routing decision from `Question Classifier 2` node events for debugging.

### Changelog

6. Milestone 2026-05-21 (Map/Reduce follow-up hardening):
	- Resolve Paper List now performs deterministic subset selection from `conversation.memory` for `first/top/newest/oldest` follow-ups.
	- Restored missing iteration Code node (`17786780698570`) to keep graph edges consistent and avoid draft runtime `MISSING_NODE` errors.
	- Verified two-turn flow for `Which paper have been published by Christoph Dieterich` -> `Please summarize the first two papers.` returns successfully (HTTP 200) in draft run.
7. Milestone 2026-05-22 (Boss demo stabilization):
	- Split overloaded paper resolution logic into staged nodes (extractor parser, follow-up intent gate, memory subset selector, slim resolver merge) to make two-turn behavior explainable and robust.
	- Added final answer sanitization node (`1778800001013`) and routed the Answer node through `cleaned_text` to strip `<think>...</think>` leakage reliably.
	- Hardened reduce prompt with authoritative requested identities/order from resolver output to keep section 1/2 mapped to the requested first two papers.
	- Fixed YAML import fragility in single-quoted prompt blocks (apostrophe handling) and re-validated import success (HTTP 200).
	- Enforced deterministic fixed-subset formatting (`**1.` / `**2.` headers) even under sparse text context, so demo checks remain stable.
	- Re-tested two-turn draft flow (`author list` -> `summarize first two`) with HTTP 200 on both turns, no `<think>` in final answer, and both section markers present.

8. Milestone 2026-05-29 (structured-output and sanitizer hardening):
	- JSON Metadata Extractor switched to structured output as primary machine-readable contract.
	- Parser node updated to accept both `extractor_text` and `extractor_structured_output`, with structured output taking precedence.
	- Extractor max token budget increased to reduce truncation risk in larger author-paper lists.
	- Metadata LLM max token budget increased (`768 -> 1200`) to improve long-answer completeness.
	- Final sanitizer hardened for both closed and unclosed `<think>` segments.
	- Validated two-turn runs with HTTP 200 on both turns and no `<think>` content in final answer.

10. Milestone 2026-06-19 (dynamic text budget for Fetch Full Paper):
	- `Resolve Paper List` now outputs `paper_count` (integer) alongside `paper_list`.
	- `Fetch Full Paper` accepts `paper_count` as an input variable and computes `chars_per_paper = max(4 000, 48 000 // paper_count)`.
	- Replaces the previous hard-coded 8 000 chars/paper limit; with fewer papers each paper gets proportionally more context.
	- **Verified:** 6-paper Turn-2 run: `paper_count=6` → 8 000 chars/paper, context lengths 8 161–8 456 chars, all 6 Fetch Full Paper nodes succeeded.

9. Milestone 2026-06-19 (Turn-2 consolidation — single LLM call + doc_id passthrough):
	- Removed `Paper Map LLM` node from inside the iteration (was 1 LLM call per paper).
	- `Fetch Full Paper` now returns `paper_context` (header + truncated text) directly to the `Variable Aggregator`.
	- A single `Metadata LLM` call outside the iteration synthesises all paper texts at once.
	- Fixed `_find_doc_id_by_title` O(N) pagination: uses `doc_metadata` field in the document list response (no per-document detail calls needed).
	- `doc_id` now propagates through the full pipeline: `conversation.memory` → `Follow-up Memory Subset` → `Resolve Paper List` → `Paper Iterator` item → `Fetch Full Paper`. `_clean_obj` in both code nodes updated to preserve `doc_id`.
	- Paper text limit reduced from 24 000 to 8 000 chars/paper; Metadata LLM `num_ctx` set to 24 576, `max_tokens` to 4 000.
	- `import_dify_dsl.sh` updated to always sync the Dify Draft after import (via `POST /workflows/draft`).
	- **Validated two-turn consolidation test (2026-06-19, app `16d50bee-bc86-4bda-bb56-a861743f3ddb`, draft run):**

| Turn | Query | Time |
|---|---|---|
| 1 | "Zeige mir alle Papiere von Christoph Dieterich in der Datenbank." | 79 s |
| 2 | "Fasse jedes dieser Papiere kurz zusammen." | 214 s |

Turn 1 — all 6 papers listed (Metadata Query path, IS_COUNT_OR_LIST):
```
Gesamtzahl der Publikationen: 6
1. APOBEC2 safeguards skeletal muscle cell fate ... | 2024 | PNAS
2. PEPseq quantifies transcriptome-wide changes ... | 2023 | Nucleic Acids Res
3. Detection of queuosine and queuosine precursors ... | 2023 | Nucleic Acids Res
4. Adaptive sampling for nanopore direct RNA-sequencing | 2023 | RNA
5. Detecting m6A at single-molecular resolution ... | 2024 | Nat Commun
6. Sci-ModoM: a quantitative database ... | 2025 | Nucleic Acids Res
```

Turn 2 — all 6 papers summarised (Fetch Full Paper path, IS_CONTENT):
- Fetch Full Paper ×6: **0.4–0.9 s/paper** (direct doc_id, no pagination)
- Metadata LLM: 15 260 prompt tokens · 1 388 completion tokens
- Output: global synthesis + 3-bullet-point summary per paper ✓

## Secondary Service: Metadata Extraction And Paper Upload

Use the CLI entrypoint:

```bash
poetry run dify-upload
```

If needed, provide dataset credentials via environment variables:

```bash
export DIFY_DATASET_API_KEY="dataset-..."
export DIFY_API_URL="http://your-dify-host/v1"
export DATASET_ID="<dataset_id>"
```

Common commands:

```bash
# Run default two-pass workflow
poetry run dify-upload default

# Run two-pass upload on one file
poetry run dify-upload two-pass --file "RMaP papers first funding period/your-file.pdf"

# Run diagnostics
poetry run dify-upload abc-test --file "RMaP papers first funding period/your-file.pdf"

# Preview extracted metadata
poetry run dify-upload metadata --file "RMaP papers first funding period/your-file.pdf"

# Process selected authors only
poetry run dify-upload selected-authors --author "Mark Helm" --author "Christoph Dieterich"

# Bulk processing
poetry run dify-upload bulk-two-pass --folder "RMaP papers first funding period"

# Quality report for extracted authors
poetry run dify-upload author-quality --folder "RMaP papers first funding period"
```

SLURM/GPU execution (recommended for full-folder runs with LLM fallback):

```bash
sbatch scripts/slurm_bulk_two_pass_ollama.sh
```

The SLURM script explicitly uses the Python module path to avoid wrapper ambiguity:

```bash
.venv/bin/python -m dify_uploader bulk-two-pass --folder "RMaP papers first funding period"
```

Hybrid extraction behavior in `dify_uploader/author_extraction.py`:

1. Fast regex and heuristics.
2. Optional LLM fallback via BAML for low-confidence cases.

BAML runtime example:

```bash
export BAML_OLLAMA_BASE_URL="http://app01.internal:21434/v1"
export BAML_OLLAMA_MODEL="qwen3:32b"
export AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK="true"
```

## Next Steps (Execution Plan)

1. Finish and verify the full 2-pass run for all PDFs in `RMaP papers first funding period` and capture success/failure counts in a run log.
2. Add a concise post-run summary artifact (processed files, retries, failures, elapsed time) under `reports/slurm/`.
3. Introduce a lightweight regression check for the two-turn path (`list papers` -> `summarize those papers`) after each workflow import.
4. Add a small acceptance checklist for stakeholder demos (HTTP status, sanitizer check, section mapping check).
