# RMAP Chatbot – Technical Guide

> **Audience:** Developers taking over maintenance and extension of the chatbot.
> **Last updated:** 2026-07-28 · v0.4.15+ · App `<your-app-id>`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [API Keys & Environment Variables](#2-api-keys--environment-variables)
3. [DSL Build Pipeline](#3-dsl-build-pipeline)
4. [Draft vs. Runtime API](#4-draft-vs-runtime-api)
5. [Deployment Workflow](#5-deployment-workflow)
6. [Node Reference](#6-node-reference)
7. [Intent Routing Deep Dive](#7-intent-routing-deep-dive)
8. [Prompt Engineering Patterns](#8-prompt-engineering-patterns)
9. [Test Suite & Regression Testing](#9-test-suite--regression-testing)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Architecture Overview

```
User Query (HTTP/WebSocket)
        │
        ▼
┌──────────────────┐
│  Unified Router  │  LLM (qwen2.5:14b) – classifies intent + extracts constraints
│  (Node: 1031)    │
└──────┬───────────┘
       │ JSON: {intent, paper_list, list_mode, rewritten_query}
       ▼
┌──────────────────┐
│ Parse Router     │  Code Node – parses JSON, resolves paper_list from
│ Output (Node: 33)│  conversation.memory for follow-up turns
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Intent Dispatcher│  IF/ELSE – 5 branches based on intent field
│ (Node: 1032)     │
└──────┬───────────┘
       │
   ┌───┼───────────────────┬───────────────┬───────────────┐
   │   │                   │               │               │
   ▼   ▼                   ▼               ▼               ▼
metadata_list    content_summary    author_lookup   entity_lookup   knowledge_retrieval
   │                   │               │               │               │
   ▼                   ▼               └───────┬───────┘               │
Metadata Query    Paper Iterator              │                       │
(Node: 98570)     + Fetch Full Paper          ▼                       │
   │              (Node: 1035+1036)    Knowledge Retrieval             │
   ▼                   │              (Node: 38200, top_k=100)          │
Update Paper      Update Paper              │                       │
Memory            Memory                    ▼                       │
   │                   │              KR Chunk Filter                │
   ▼                   ▼              (Node: 1036)                   │
Persist Paper      Persist Paper           │                       │
Memory             Memory                  ▼                       │
   │                   │              KR Intent Router               │
   ▼                   ▼              (Node: 1039)                   │
Metadata LLM       Summary LLM         ┌───┼───┐                   │
(Node: 1027)       (Node: 1035)        │   │   │                   │
   │                   │              ▼   ▼   ▼                   │
   │                   │       Author   Entity   KR                │
   │                   │       Extract  Extract  Extract            │
   │                   │       (1034)   (1037)   (1038)             │
   │                   │          │       │       │                │
   └───────────────────┴──────────┴───────┴───────┴────────────────┘
                                    │
                                    ▼
                          Final Answer Sanitizer
                          (Node: 1013) – merges outputs, strips <think> tags
                                    │
                                    ▼
                                 Answer
```

**Key stats:**
- 23 nodes, 28 edges
- 5 query intents + collaboration analysis, 6 LLM nodes (all qwen2.5:14b via Ollama)
- 7 code nodes (Python, injected via build pipeline)
- 1 knowledge-retrieval node (hybrid keyword 0.7 + vector 0.3, top_k=100)
- Dataset: `<your-dataset-id>` (84 papers, 821 authors, nomic-embed-text-v2-moe)

---

## 2. API Keys & Environment Variables

### 2.1 Key Types and Their Roles

**Single source of truth:** All configuration lives in `.env`. All scripts (`export_dify_dsl.sh`, `import_dify_dsl.sh`, `restore_kr_dataset.sh`) read settings from there.

The chatbot uses three distinct API key types, each serving a different purpose:

| Key Type | Prefix | Purpose | Stored In |
|----------|--------|---------|-----------|
| **Dataset API Key** | `dataset-*` | Metadata Query code node reads documents from dataset | Dify App Environment Variables |
| **App API Key** | `app-*` | Runtime API calls (v1/chat-messages) | `.env` → `DIFY_APP_API_KEY` |
| **Console Session** | (token) | Console API calls (import, publish, draft run) – obtained via auto-login, not a persistent key | `.secrets/dify_console_session.env` |

**Note on Console Auth:** We do not use a persistent Console API Key. Instead, all admin scripts use **auto-login**: they POST email + base64-encoded password to `/console/api/login`, receive a session cookie + CSRF token, and store these in `.secrets/dify_console_session.env`. This session is automatically refreshed when it expires (HTTP 401 → re-login).

### 2.2 How Env Vars Reach the Code Nodes

The flow from `.env` to the running code node has three stages:

```
┌──────────┐    import_dify_dsl.sh     ┌─────────────────┐    variable binding    ┌──────────────┐
│  .env    │ ────────────────────────▶ │  Dify App Draft  │ ────────────────────▶ │  Code Node   │
│ (local)  │   sync_draft() reads      │  environment_    │   [env, DIFY_API_KEY] │  api_key =   │
│          │   DIFY_API_KEY +          │  variables       │   → api_key_input     │  api_key_    │
│          │   DIFY_DATASET_ID         │  (real values)   │                       │  input or     │
└──────────┘                          └─────────────────┘                       │  os.getenv()  │
                                                                                └──────────────┘
```

**Stage 1 — YAML (git-safe):** The DSL YAML stores only **placeholders** in `environment_variables`:
```yaml
environment_variables:
  - name: DIFY_API_KEY
    value: dataset-<your-dataset-key>    # ← placeholder, never real
  - name: DIFY_DATASET_ID
    value: <your-dataset-id>            # ← placeholder, never real
```

**Stage 2 — Import injection:** `import_dify_dsl.sh` → `sync_draft()` reads **real values** from `.env` and overwrites the placeholders before POSTing to the Dify draft endpoint. After import, the Dify draft always has real values.

**Stage 3 — Runtime injection:** Dify passes the app's `environment_variables` into code nodes via variable bindings:
```yaml
# In Metadata Query code node:
variables:
  - value_selector: [env, DIFY_API_KEY]     # ← reads from Dify app env vars
    variable: api_key_input
  - value_selector: [env, DIFY_DATASET_ID]
    variable: dataset_id_input
```

**Code node priority** (in `metadata_query.py` and `fetch_full_paper.py`):
```python
# Dify-injected value FIRST, container env SECOND, hardcoded fallback LAST
api_key    = api_key_input or os.getenv("DIFY_API_KEY") or ""
dataset_id = dataset_id_input or os.getenv("DIFY_DATASET_ID") or "5a231cec-..."
api_base   = os.getenv("DIFY_API_URL") or "http://rmap-chatbot-demo-dify/v1"
```

> **Key rule:** `.env` is the single source of truth. YAML has placeholders. `import_dify_dsl.sh` bridges the gap. No manual env var step needed after import.

### 2.3 Key Rotation Procedure

When the dataset API key expires:

```bash
# 1. Create new key in Dify UI: Datasets → RMAP Papers → API Access
# 2. Update .env (single source of truth):
sed -i 's/DIFY_DATASET_API_KEY=dataset-OLD_KEY/DIFY_DATASET_API_KEY=dataset-NEW_KEY/' .env

# 3. Re-import — injects new key into Dify draft + publishes:
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --skip-build --allow-cookie-auth --auto-login

# 4. Verify (direct API):
curl "http://rmap-chatbot-demo-dify/v1/datasets?page=1" \
  -H "Authorization: Bearer dataset-NEW_KEY"
```

> `import_dify_dsl.sh` → `sync_draft()` automatically reads the new key from `.env` and injects it. No manual env var step needed.

### 2.4 What Needs Hardcoded Fallbacks (and Why)

Only the Dify API base URL has a hardcoded fallback — the dataset ID and API key MUST come from `.env`:

| Value | Location | Why |
|-------|----------|-----|
| `http://rmap-chatbot-demo-dify/v1` | `metadata_query.py`, `fetch_full_paper.py` | Dify API base URL — internal Docker hostname, not a secret |

The dataset ID (`DIFY_DATASET_ID`) has **no hardcoded fallback**. If it's missing, the code returns an error telling you to run `import_dify_dsl.sh`. This ensures `.env` is always the single source of truth.

The priority chain for all values:
1. Dify-injected env var (`api_key_input`, `dataset_id_input`) — set by `import_dify_dsl.sh` from `.env`
2. Container environment (`os.getenv("DIFY_DATASET_ID")`) — if set in Docker
3. Error — if neither is available, fail loudly

### 2.5 Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Editing YAML env vars manually | Real keys in git! Keys leaked | Never edit `environment_variables` in the YAML — they're placeholders |
| Pasting real keys into Dify UI | Works, but overwritten on next import | Always use `import_dify_dsl.sh` — it auto-injects from `.env` |
| Forgetting to publish after import | Draft works, runtime doesn't | Run the full deploy cycle (§5.1) |
| `debug_route_draft.sh` returns empty | Draft has placeholder env vars | Run `import_dify_dsl.sh` first to inject real values |
| "No papers found" after key rotation | Old key still in Dify draft | Update `.env`, then re-run `import_dify_dsl.sh` |

> **Golden rule:** `.env` is the single source of truth. YAML has placeholders. `import_dify_dsl.sh` bridges the gap. Never edit env vars manually in Dify UI or YAML.

---

## 3. DSL Build Pipeline

### 3.1 The Two Representations

The workflow exists in two forms:

| Form | Location | Purpose |
|------|----------|---------|
| **Python source files** | `workflow_scripts/*.py` | Editable, version-controlled source of truth for code nodes |
| **DSL YAML** | `config/RMAP Chatbot Iterative Retrieval.yml` | Complete Dify workflow including LLM prompts, graph structure, variable bindings |

### 3.2 Build Process (`scripts/build_dsl.py`)

```
workflow_scripts/*.py          config/RMAP Chatbot...yml
        │                              │
        │  1. Read Python source       │  2. Load YAML template
        │     strip header comments    │     (contains LLM prompts,
        │                              │      graph structure,
        │                              │      variable bindings)
        │                              │
        └──────────┬───────────────────┘
                   │  3. For each code node in YAML:
                   │     find matching script by node title
                   │     inject code into node["data"]["code"]
                   ▼
           config/RMAP Chatbot...yml
           (final DSL, ready for import)
```

**Node-to-script mapping** (from `build_dsl.py` `NODE_TO_SCRIPT`):

| Dify Node Title | Python File |
|-----------------|-------------|
| Final Answer Sanitizer | `final_answer_sanitizer.py` |
| KR Chunk Filter | `kr_chunk_filter.py` |
| Metadata Query | `metadata_query.py` |
| Parse Router Output | `parse_router_output.py` |
| Parse Extractor Paper List | `parse_extractor_paper_list.py` |
| Follow-up Memory Subset | `follow_up_memory_subset.py` |
| Resolve Paper List | `resolve_paper_list.py` |
| Update Paper Memory | `update_paper_memory.py` |
| Fetch Full Paper | `fetch_full_paper.py` |

**Important:** Only code node logic is in `workflow_scripts/`. LLM prompts, graph topology, variable bindings, model config – all live directly in the YAML. Edit these in the YAML file (or via Dify UI, then export).

### 3.3 Export from Dify UI

If changes were made in the Dify UI (e.g., prompt tweaks, graph restructure):

```bash
bash scripts/export_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" --auto-login
```

This script:
1. Authenticates via `/console/api/login` (if `--auto-login`)
2. GETs `/console/api/apps/{id}/export?include_secret=false`
3. Patches the Knowledge Retrieval `dataset_ids` (Dify export strips these; restores from `DIFY_DATASET_ID` in `.env`)
4. Strips `zIndex` fields (Dify UI validator rejects them)
5. Writes the YAML to the config file

Then extract code nodes back to Python files:
```bash
python scripts/extract_dsl_code.py
```

### 3.4 Import to Dify

```bash
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --allow-cookie-auth --auto-login
```

What happens:
1. **Build**: `build_dsl.py` injects `workflow_scripts/*.py` into YAML
2. **Sanitize**: `build_dsl.py` replaces real API keys in `environment_variables` with placeholders (git-safe)
3. **Import**: POSTs YAML to `/console/api/apps/imports`
4. **Draft sync + env injection**: `sync_draft()` fetches the draft, reads **real** `DIFY_API_KEY` and `DIFY_DATASET_ID` from `.env`, injects them into `environment_variables`, and POSTs the updated draft
5. **KR dataset fix**: Restores `dataset_ids` on the Knowledge Retrieval node from `DIFY_DATASET_ID` in `.env` (Dify import sometimes strips it)

**After import, publish.** The draft already has real env vars from step 4 — no manual env var step needed. See §5.1 for the full deploy cycle.

---

## 4. Draft vs. Runtime API

### 4.1 Two Testing Modes

| Aspect | Draft API | Runtime API |
|--------|-----------|-------------|
| **Endpoint** | `/console/api/apps/{id}/advanced-chat/workflows/draft/run` | `/v1/chat-messages` |
| **Auth** | Cookie (`DIFY_CONSOLE_COOKIE` + `DIFY_CSRF_TOKEN`) | Bearer token (`app-*` key) |
| **Response** | SSE stream with per-node events | SSE stream or blocking JSON |
| **Debug info** | Node status, runtime per node, classifier output | None |
| **Uses** | Prompt debugging, node-level timing | Production testing, multi-turn |
| **Script** | `debug_route_draft.sh` | `debug_route_runtime.sh` |

### 4.2 Draft API Deep Dive

The draft API returns an SSE stream with detailed node execution events:

```
event: node_started
data: {"event":"node_started","data":{"node_id":"1778800001031","title":"Unified Router",...}}

event: node_finished
data: {"event":"node_finished","data":{"node_id":"1778800001031","outputs":{"intent":"metadata_list",...}}}

event: message
data: {"event":"message","answer":"8 papers\n1. **APOBEC2..."}
```

The `debug_route_draft.sh` script parses these events:
- Extracts `class_name` from the Question Classifier node (`1778150713944`)
- Extracts `answer` from `message` events
- Shows `Answer preview:` (first 20 lines)

**Authentication flow:**
```
┌─────────────┐     POST /console/api/login      ┌─────────────┐
│ debug_route │ ─────────────────────────────────▶│ Dify Console │
│ _draft.sh   │ ◀─────────────────────────────────│             │
│             │     Set-Cookie: access_token=...   └─────────────┘
│             │     Set-Cookie: csrf_token=...
└─────────────┘
       │
       │ Stores in .secrets/dify_console_session.env
       │ DIFY_CONSOLE_COOKIE="access_token=...; refresh_token=...; csrf_token=..."
       │ DIFY_CSRF_TOKEN="..."
       │
       ▼
POST /console/api/apps/{id}/advanced-chat/workflows/draft/run
Cookie: {DIFY_CONSOLE_COOKIE}
x-csrf-token: {DIFY_CSRF_TOKEN}
Body: {"inputs":{"sys.query":"..."},"response_mode":"streaming","user":"test"}
```

### 4.3 Runtime API

Used for production-like testing. Requires the app to be published with valid env vars.

```bash
DIFY_BASE_URL="http://<your-dify-host>" \
DIFY_APP_API_KEY="app-<your-app-key>" \
bash scripts/debug_route_runtime.sh \
  --query "Papers by Christoph Dieterich" \
  --query "Summarize them"
```

The runtime script maintains `conversation_id` across multi-turn queries, simulating a real user session.

---

## 5. Deployment Workflow

### 5.1 Full Deploy Cycle

```bash
# 1. Edit prompts in YAML or code in workflow_scripts/*.py

# 2. Build DSL
.venv/bin/python scripts/build_dsl.py

# 3. Import to Dify (env vars auto-injected from .env)
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --skip-build --allow-cookie-auth --auto-login

# 4. Publish (draft already has real env vars from step 3)
.venv/bin/python -c "
import json, os, requests
with open('.env') as f:
    env = {}
    for line in f:
        if '=' in line and not line.startswith('#'): k,v = line.split('=',1); env[k.strip()]=v.strip().strip('\"')
with open('.secrets/dify_console_session.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'): k,v = line.split('=',1); env[k.strip()]=v.strip().strip('\"')
r = requests.get(f'{env['DIFY_BASE_URL']}/console/api/apps/16d50bee-bc86-4bda-bb56-a861743f3ddb/workflows/draft',
    headers={'Cookie': env['DIFY_CONSOLE_COOKIE'], 'x-csrf-token': env['DIFY_CSRF_TOKEN']})
d = r.json()
requests.post(f'{env['DIFY_BASE_URL']}/console/api/apps/16d50bee-bc86-4bda-bb56-a861743f3ddb/workflows/publish',
    headers={'Cookie': env['DIFY_CONSOLE_COOKIE'], 'x-csrf-token': env['DIFY_CSRF_TOKEN'], 'Content-Type': 'application/json'},
    json={'graph': d['graph'], 'features': d.get('features',{}), 'environment_variables': d.get('environment_variables',[]),
          'conversation_variables': d.get('conversation_variables',[]), 'hash': d.get('hash','')})
print('Published')
"

# 5. Test
# Draft API:
bash scripts/debug_route_draft.sh --app-id <your-app-id> \
  --query "Who has worked on tRNA modifications?" --allow-cookie-auth

# Runtime API:
DIFY_BASE_URL="..." DIFY_APP_API_KEY="app-..." \
bash scripts/debug_route_runtime.sh --query "What is m6A?"

# 6. Commit + tag
git add -A && git commit -m "fix: ..." && git push
git tag -a v0.4.X -m "..." && git push --tags
gh release create v0.4.X --repo dieterich-lab/RmapDifyChatbot ...
```

### 5.2 Key Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/build_dsl.py` | Inject `workflow_scripts/*.py` into YAML |
| `scripts/extract_dsl_code.py` | Extract code from YAML back to `workflow_scripts/` |
| `scripts/import_dify_dsl.sh` | Build + import + draft sync + KR fix |
| `scripts/export_dify_dsl.sh` | Pull YAML from Dify UI → local |
| `scripts/debug_route_draft.sh` | Test via draft console API (SSE, per-node) |
| `scripts/debug_route_runtime.sh` | Test via published app API (multi-turn) |
| `scripts/fix_kr_dataset.sh` | Restore KR dataset after import strips it |
| `scripts/update_dify_metadata.py` | Bulk-update document metadata via PubMed |

---

## 6. Node Reference

### 6.1 Node Inventory

| # | Node ID | Type | Title | Function |
|---|---------|------|-------|----------|
| 1 | `1778800001031` | llm | **Unified Router** | Classifies intent, extracts paper constraints, writes standalone query |
| 2 | `1778800001033` | code | **Parse Router Output** | Parses router JSON, resolves `paper_list`, handles `<think>` tags |
| 3 | `1778800001032` | if-else | **Intent Dispatcher** | Routes to one of 5 branches based on `intent` field |
| 4 | `17785930638200` | knowledge-retrieval | **Knowledge Retrieval** | Hybrid search (keyword 0.7 + vector 0.3, top_k=100) |
| 5 | `1778800001036` | code | **KR Chunk Filter** | Reference filter, 1 chunk/paper dedup, metadata garbling detection |
| 6 | `1778800001039` | if-else | **KR Intent Router** | Routes chunks to Author/Entity/KR Extraction LLM |
| 7 | `1778800001034` | llm | **Author Extraction LLM** | Extracts all authors + verbatim quotes per paper |
| 8 | `1778800001037` | llm | **Entity Extraction LLM** | Extracts entities (modifications, methods, organisms) as table |
| 9 | `1778800001038` | llm | **KR Extraction LLM** | Knowledge synthesis with inline citations |
| 10 | `17786780698570` | code | **Metadata Query** | Queries Dify Dataset API with author/year/title/journal filters |
| 11 | `1778800001035` | iteration | **Paper Iterator** | Iterates over `paper_list`, fetches full-text chunks |
| 12 | `1778800001036` | code | **Fetch Full Paper** | Gets all segments via Dify API, dynamic text budget |
| 13 | `1778800001027` | llm | **Metadata LLM** | Formats metadata_list results: "Total count + numbered list" |
| 14 | `1778800001035` | llm | **Summary LLM** | Summarizes papers: "Global Synthesis + 3 bullets/paper" |
| 15 | `1778800001013` | code | **Final Answer Sanitizer** | Merges all outputs, strips `<think>` tags, fallback logic |
| 16-17 | (x2) | code | **Update Paper Memory** | Parses iteration/metadata output into conversation.memory |
| 18-19 | (x2) | assigner | **Persist Paper Memory** | Writes resolved papers to conversation variable |

### 6.2 Node Functions Illustrated by Test Cases

#### Unified Router (Node 1) — Intent Classification

**Test case #1:** `"Which papers are (co-) authored by Christoph Dieterich?"`
→ Routes to `metadata_list`, `paper_list: [{"authors": "Christoph Dieterich"}]`

**Test case #4:** `"Who has worked on tRNA modifications?"`
→ Routes to `author_lookup`, `paper_list: []`

**Test case #15 (Turn 2):** `"Group them by journal"`
→ Routes to `content_summary`, `paper_list: "use_memory"` — resolves pronoun "them" to prior-turn papers

**Key prompt rules:**
```
"Find papers by <name>" → metadata_list, paper_list: [{"authors": "<name>"}]
"Find all research papers" → metadata_list, paper_list: []
"List all researchers" → metadata_list, list_mode: "authors"
"Who has worked on X?" → author_lookup, paper_list: []
"Group/Sort/Filter them by X" → content_summary, paper_list: "use_memory"
```

#### Parse Router Output (Node 2) — JSON Parsing & Memory Resolution

```python
# Key behaviors:
- Strips <think> tags from LLM output before JSON parsing
- Reads list_mode from router JSON (papers | authors)
- Auto-fallback: if paper_list is empty AND intent is content_summary
  AND conversation.memory has papers → populate from memory
- MAX_PAPERS_FOR_SUMMARY = 15: caps paper count to prevent context overflow
- Fallback result: {"intent": "knowledge_retrieval", "paper_list": [],
                     "paper_count": 0, "list_mode": "papers"}
```

#### Author Extraction LLM (Node 7) — Evolution Through Test Cases

**v0.4.0-v0.4.5:** Had hardcoded rules about "tRNA modifications or queuosine"
→ Test case #4 showed fabricated quotes for Richter and Pichot

**v0.4.6 fix:** Anti-fabrication guard
→ Rule 5 amended: "If NO verbatim quotable sentence exists, write 'No verbatim quote available.' NEVER fabricate."

**v0.4.7 fix:** Cross-contamination prevention
→ Added: "Each paper entry gets its authors ONLY from its OWN header."

**v0.4.8 fix:** Generic query support
→ Rules 5/6 changed from "tRNA/queuosine" to "relevant to the user's query"
→ Test case #12 (HEK cells) no longer produces speculative claims

#### Metadata Query (Node 10) — Dataset API Integration

**Test case #6:** `"Find papers by Francesca Tuorto"` → queries dataset API with author filter "Francesca Tuorto", returns 6 matches

**Test case #9:** `"Find papers by Lauren Saunders"` → 0 matches, returns "Keine Dokumente gefunden" + search tips

**Test case #10:** `"Find all research papers"` → no filter (`list_mode="papers"`), returns all 81 papers

**Key code:**
```python
def main(year=None, authors=None, journal=None, title=None,
         paper_list=None, list_mode=None, api_key_input=None,
         dataset_id_input=None):
    api_key = os.getenv("DIFY_API_KEY") or api_key_input or ""
    # Collects all documents via paginated Dify API
    # Applies filters: _author_variants() for fuzzy name matching
    # Returns {"result": array_of_strings, "result_text": full_text}
```

#### KR Chunk Filter (Node 5) — Quality Control

- **Reference filter:** Detects bibliography sections by signal density (DOI patterns, numbered references, year clusters)
- **1 chunk/paper dedup:** Maximizes paper diversity (up to 50 unique papers at top_k=100)
- **Metadata garbling detection:** `_metadata_looks_garbled()` catches book chapters with broken titles (e.g., "ComputationalEpigenomicsandEpitranscriptomics")
- **30-element cap:** Dify array output limit

#### Final Answer Sanitizer (Node 15) — Output Merging

Merges outputs from all 5 paths into one answer:
```python
parts = []
for key in ("extraction_text", "entity_text", "summary_text",
            "knowledge_text", "metadata_text"):
    text = kwargs.get(key)
    if text:
        cleaned = _strip_think(text)  # removes <think>...</think> tags
        if cleaned:
            parts.append(cleaned)

# Fallback: use result_text from Metadata Query if LLM outputs are weak
rt = kwargs.get("result_text")
if rt and (not parts or all(is_weak(p) for p in parts)):
    parts = [cleaned_rt]
```

---

## 7. Intent Routing Deep Dive

### 7.1 The Five Intents

| Intent | Trigger Phrases | Data Source | Output LLM | Output Format |
|--------|----------------|-------------|------------|---------------|
| `metadata_list` | "Papers by X", "Find all papers", "List all researchers" | Dify Dataset API | Metadata LLM | "N papers" + numbered list |
| `content_summary` | "Summarize them", "Group them by X", "Compare papers" | Fetch Full Paper (segments) | Summary LLM | Global synthesis + 3 bullets/paper |
| `author_lookup` | "Who has worked on X?", "Who is using X?" | Knowledge Retrieval | Author Extraction LLM | Paper title + all authors + quote |
| `entity_lookup` | "Which X are most studied?", "What methods...?" | Knowledge Retrieval | Entity Extraction LLM | Entity table with paper references |
| `knowledge_retrieval` | "What is X?", "How does X work?" | Knowledge Retrieval | KR Extraction LLM | Knowledge summary with inline citations |

### 7.2 Routing Decision Tree

```
User Query
    │
    ▼
Does query contain "Group/Sort/Filter/Categorize them by X"?
    YES → content_summary, paper_list: "use_memory"
    NO  ↓
Does query contain "Find papers by <name>" / "Papers by <name>"?
    YES → metadata_list, paper_list: [{"authors": "<name>"}]
    NO  ↓
Does query contain "Find all research papers" / "List all researchers"?
    YES → metadata_list, paper_list: [] (or list_mode: "authors")
    NO  ↓
Does query contain "Who has worked on/experience with/synthesized X"?
    YES → author_lookup, paper_list: []
    NO  ↓
Does query contain "Which tRNAs/proteins/methods/entities"?
    YES → entity_lookup, paper_list: []
    NO  ↓
Does query contain "Summarize/Compare" with paper reference?
    YES → content_summary with paper_list
    NO  ↓
    Default → knowledge_retrieval (general topic question)
```

### 7.3 Follow-up Turn Memory Flow

```
Turn 1: "Papers by Christoph Dieterich"
  → metadata_list → Metadata Query finds 8 papers
  → Update Paper Memory formats them into conversation.memory
  → Persist Paper Memory writes to Dify conversation variable
  → Metadata LLM outputs "8 papers: 1. ... 2. ..."

Turn 2: "Summarize them"
  → Unified Router sees "them" → resolves to prior-turn papers
  → Sets intent=content_summary, paper_list="use_memory"
  → Parse Router Output detects paper_list="use_memory"
  → Reads conversation.memory → populates 8 paper identities
  → Paper Iterator iterates over 8 papers
  → Fetch Full Paper gets segments for each
  → Summary LLM produces per-paper synthesis
```

---

## 8. Prompt Engineering Patterns

### 8.1 Anti-Hallucination Guards

All LLM prompts follow a consistent pattern:

```
=== CRITICAL RULES ===
1. Use ONLY the provided context/headers.
2. Copy EXACTLY — no expansion, no paraphrasing.
3. If information is missing: say so explicitly.

CRITICAL: NEVER fabricate. NO <think>.

Format (use EXACTLY this format):
... specific output template ...
```

### 8.2 Quote Extraction Guard (Author Extraction LLM)

The most heavily iterated prompt. Evolution:

```
v0.4.0: "Use a verbatim quote from the chunk as evidence"
  → Problem: LLM fabricated quotes when no quotable sentence existed

v0.4.6: "If NO verbatim quotable sentence exists, write 'No verbatim quote available.'
         NEVER fabricate, paraphrase, or invent a quote."
  → Fix: Richter now says "No verbatim quote available." ✅

v0.4.7: "Each paper entry gets its authors ONLY from its OWN header.
         Do NOT copy authors from one header into another."
  → Fix: Biedenbander now lists correct 6 authors ✅

v0.4.8: Rules 5/6 changed from hardcoded "tRNA/queuosine" to
         "relevant to the user's query"
  → Fix: HEK cell query no longer produces speculative claims ✅
```

### 8.3 Citation Verification Guard (KR Extraction LLM)

```
"VERIFY each citation: the claim you cite MUST come from the SAME
chunk whose 'From paper:' header you use. If a claim appears in one
chunk but you cite a different paper, that is WRONG."
```

Before (v0.4.6): Cross-reactivity claim cited Chan et al. (wrong paper)
After (v0.4.7): Cross-reactivity claim cites Koch/Lyko (correct paper) ✅

### 8.4 Count Verification Guard (Metadata LLM)

```
"COUNT the items in your numbered list. Verify that the count you
state matches the actual number. If you list 8 papers, say '8 papers',
not '7 papers'. Double-check before output."
```

Before (v0.4.5): "7 out of 8 papers" (Sci-ModoM dropped)
After (v0.4.6): "8 papers" (all listed) ✅

### 8.5 YAML Single-Quote Escaping

All LLM prompts in the DSL YAML are single-quoted strings. Any apostrophe (`'`) within the prompt text must be escaped as `''`:

```yaml
# WRONG (breaks YAML parsing):
text: '...relevant to the user's query...'

# CORRECT:
text: '...relevant to the user''s query...'
```

---

### 8.6 Author Name Normalization Pattern (v0.4.9)

The Unified Router (qwen2.5:14b) cannot reliably distinguish person names from knowledge queries:

```
"Mark Helm" → metadata_list ✅
"Helm, Mark" → author_lookup ❌ (LLM misclassifies comma format)
"M. Helm" → author_lookup ❌ (LLM misclassifies dot-initial format)
"Dieterich" → content_summary ❌ (LLM misclassifies bare last name)
```

**Fix: Code-Level Guard > Prompt-Only.** Prompt engineering alone was insufficient — the LLM could not distinguish "M. Helm" (a person) from "What is m6A?" (a knowledge question). Solution: `parse_router_output.py` detects bare person names via pattern matching:

- **Comma format**: `"," in q and len(q.split(",")) == 2` → "Helm, Mark"
- **Dot-initial format**: `re.match(r"^[A-Z].\\s+\\w{2,}$", q)` → "M. Helm"
- **1–2 capitalized words without question markers**: no "who/what/which/how/why" etc. → "Dieterich", "Mark Helm"

When detected, the guard overrides `author_lookup`/`knowledge_retrieval` → `metadata_list` and populates `paper_list` with the author name.

**Complementary fix in `metadata_query.py`**: `_author_variants()` normalizes "Last, First" → "First Last", always includes last-name-only fallback, and handles abbreviated first names. `_matches_filters()` adds last-resort last-name substring check for edge cases like "Chr. Dieterich" vs "Christoph Dieterich".

### 8.7 LLM Bypass Pattern (v0.4.14)

**When the LLM can't follow instructions, bypass it.** For multi-author OR queries, qwen2.5:14b consistently interpreted comma-separated authors as AND logic — ignoring CRITICAL, PASSTHROUGH, VERBATIM instructions.

**Three-layer pattern:**

```
parse_router_output.py          metadata_query.py            Final Answer Sanitizer
┌─────────────────────┐    ┌──────────────────────────┐    ┌───────────────────────┐
│ Code-level guard     │    │ Pre-formatted Markdown    │    │ Falls back to          │
│ detects multi-author │───▶│ output from metadata      │───▶│ result_text when       │
│ → paper_count = 0    │    │ _render_result()          │    │ LLM outputs are empty  │
└─────────────────────┘    └──────────────────────────┘    └───────────────────────┘
```

1. **Code guard** detects multi-author queries and sets `paper_count=0`
2. **Metadata LLM Bypass** (`paper_count=0`) routes through directly to Sanitizer
3. **Pre-formatted output** from `metadata_query.py` passes through verbatim — no LLM formatting step

### 8.8 Multi-Author OR Matching (v0.4.14)

`_matches_filters()` in `metadata_query.py` now supports OR logic for comma-separated author names:

```python
# "Helm, Hengesbach" → paper matches if EITHER "Helm" OR "Hengesbach" appears
has_multi = any("," in a for a in author_inputs)
if has_multi:
    all_names = [part.strip() for a in author_inputs for part in a.split(",")]
    for name in all_names:
        if any(v in meta_authors.lower() for v in _author_variants(name)):
            break  # matched
    else:
        return False  # no name matched
```

The router recognizes queries like "Identify: Helm, Hengesbach" or "Papers by Helm, Hengesbach" as `metadata_list` with comma-separated author constraints.

### 8.9 Collaboration Analysis (v0.4.15)

Co-author pair computation via `metadata_query.py::_compute_collaborations()`. Triggered when `parse_router_output.py` detects collaboration keywords and sets `collaboration_mode`.

**Router patterns:**
- "Who has collaborated the most?" → `metadata_list`, `collaboration_mode: "all"`
- "Who has collaborated with X?" → `metadata_list`, `collaboration_mode: "X"`
- "Which co-authors has X published with?" → same as above

**Code guard** (in `parse_router_output.py`):
```python
collab_markers = ("collaborat", "co-author", "published together", "published with", ...)
if any(m in query for m in collab_markers):
    intent = "metadata_list"
    # Extract target author from "co-authors of X" / "collaborated with X"
    collaboration_mode = target if target else "all"
```

**Output:** Top 20 co-author pairs with paper titles. 3,253 unique pairs across 84 papers. Helm+Motorin: 10 papers (most frequent).

### 8.10 Embedding Model Evaluation Pattern (v0.4.14)

**Test before switching, not after.** When evaluating `bge-m3` as a replacement for `nomic-embed-text-v2-moe`:

1. Full regression across all 5 intents (not just a single query)
2. `metadata_list` as control group (unaffected by embedding, uses Dataset API)
3. Per-case latency measurement + quality assessment
4. Document the negative result → prevents redundant re-evaluation

Result: bge-m3 showed equivalent quality but 48% worse latency → nomic retained. See `docs/embeddings.md` for full methodology.

### 8.12 "What Else" Follow-Up Queries (v0.4.16+)

**Problem:** qwen2.5:14b ignores prompt rules for "what else" follow-ups, routing them as broad "find all papers" queries. "What else did he publish?" after "Papers by Dieterich from 2023" returned all 83 papers instead of Dieterich's 8.

**Fix: Code-Level Guard** (same pattern as §8.6, §8.7, §8.9):

```python
# parse_router_output.py
if sys_query:
    q = str(sys_query).strip().lower()
    is_what_else = (
        q.startswith("what else ")
        or q.startswith("anything else ")
        or "what else has " in q
        or "what else did " in q
    )
    if is_what_else and mem:
        # Extract author from conversation.memory (previous turn papers)
        prev_authors = set()
        for item in mem:
            if isinstance(item, dict):
                a = str(item.get("authors", "")).strip()
                if a:
                    prev_authors.add(a)
        if prev_authors:
            intent = "metadata_list"
            paper_list = [{"authors": list(prev_authors)[0], ...}]
```

**How it uses conversation memory:** The `mem` list contains the papers from the previous turn — each with `{title, authors, year, journal, doc_id}`. For "Papers by Dieterich from 2023", all 3 papers share the authors field containing "Dieterich, Christoph". The guard extracts this author name and re-runs `metadata_list` without the year filter, returning all 8 Dieterich papers.

**Defense in depth:** Router prompt also has a "what else" rule, but the code guard is the reliable layer (the 14B model ignores complex prompt rules, same pattern as multi-author OR and name normalization).

**Test case #21:** `docs/test-cases.md` — "Papers by Christoph Dieterich from 2023" → 3 papers → "What else did he publish?" → 8 papers (was: 83).

---

## 9. Test Suite & Regression Testing

### 9.1 Test Cases Overview

21 test cases in `docs/test-cases.md`, covering all 5 intents:

| Status | Count | Cases |
|--------|-------|-------|
| ✅ Passing | 19 | #1, #2, #3, #4, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #19, #20, Bonus |
| ⚠️ Known Issue | 2 | #5 (entity recall, LLM model limit), #21 ("what else" waiting for H100) |
| ❌ Known Limitation | 1 | #18 (external KB needed) |

### 9.2 Running Regression Tests

**Quick smoke test (draft API):**
```bash
bash scripts/debug_route_draft.sh --app-id <your-app-id> \
  --query "Which papers are (co-) authored by Christoph Dieterich?" \
  --allow-cookie-auth
# Expected: "8 papers" with all 8 listed including Sci-ModoM
```

**Full regression (runtime API):**
```bash
DIFY_BASE_URL="http://<your-dify-host>" \
DIFY_APP_API_KEY="app-<your-app-key>" \
bash scripts/debug_route_runtime.sh \
  --query "What is m6A?" \
  --query "Who has worked on tRNA modifications?" \
  --query "Which RNA modifications are most studied?" \
  --query "Who is using HEK cells?" \
  --query "Find papers by Francesca Tuorto"
```

### 9.3 Regression Checklist

Before each release, verify:

- [ ] #1: "Papers by Christoph Dieterich" → "8 papers" ✅
- [ ] #3: "What is m6A?" → Citations correct, no fabricated facts ✅
- [ ] #4: "Who has worked on tRNA modifications?" → Authors + Quotes, no cross-contamination ✅
- [ ] #6: "Find papers by Francesca Tuorto" → `metadata_list`, "6 papers" ✅
- [ ] #12: "Who is using HEK cells?" → No speculative claims, "No verbatim quote available" where appropriate ✅
- [ ] #14: "Find Papers by Dieterich" → "8 papers" (last name only) ✅
- [ ] #17: "Identify: Helm, Hengesbach" → "39 papers" (multi-author OR) ✅
- [ ] Bonus: "Mark Helm" / "Helm, Mark" / "M. Helm" → all `metadata_list` ✅

### 9.4 Running Full Regression

```bash
# Runtime API (published app, faster):
DIFY_BASE_URL="http://<your-dify-host>" \
DIFY_APP_API_KEY="app-..." \
python3 scripts/regression_test.py

# Draft API (per-node debug):
bash scripts/debug_route_draft.sh --app-id <your-app-id> \
  --auto-login --query "Papers by Christoph Dieterich" ...
```

---

## 10. Troubleshooting

### 10.1 "Output result is not an array, got <class 'str'>" (Runtime API)

**Cause:** Env vars not set in published app → Metadata Query returns error string instead of array.

**Fix:**
```bash
# Re-set env vars and publish (see §2.2)
```

### 10.2 Draft API Returns Empty Answer for metadata_list

**Cause:** Dataset API key expired or not set in draft env vars.

**Fix:** Rotate key (see §2.3) and re-set env vars.

### 10.3 YAML Parse Error After Prompt Edit

**Cause:** Unescaped `'` in YAML single-quoted string.

**Fix:** Replace `'` with `''` within prompt text (see §8.5).

### 10.4 "Summarize them" Times Out (>5 min)

**Cause:** Author with many papers (e.g., Mark Helm: 28). Fetch Full Paper takes ~0.5s/paper.

**Mitigation:** `MAX_PAPERS_FOR_SUMMARY = 8` in `parse_router_output.py` (v0.4.10). Tested at 194s for Mark Helm (28 papers → 8 summarized). Well under the 5 min draft timeout.

### 10.5 env vars Lost After Import (Fixed in v0.4.16+)

**Historical cause:** `import_dify_dsl.sh` replaced the draft graph, which cleared env vars.

**Fix:** `sync_draft()` now auto-injects `DIFY_API_KEY` and `DIFY_DATASET_ID` from `.env` on every import. See §2.2 for the complete flow. No manual step needed.

> If you suspect env vars are stale, just re-run `import_dify_dsl.sh` — `sync_draft()` will refresh them from `.env`.

### 10.6 Knowledge Retrieval Returns Wrong Dataset

**Cause:** `dataset_ids` stripped during import.

**Fix:** `import_dify_dsl.sh` auto-fixes via `fix_kr_dataset()`. If manual fix needed:
```bash
bash scripts/fix_kr_dataset.sh --app-id <your-app-id> --auto-login
```

### 10.7 Start Node Appears as White Bar / All Nodes "Not Connected"

**Cause:** YAML serializer truncated `type: "custom"` → `type: "custo"` on the start node. Dify fails to render the node and all downstream nodes appear disconnected. Publish returns HTTP 500.

**Fix:** Ensure the start node's top-level `type` field is `"custom"` (not `"custo"`):
```bash
grep -n "custo" config/RMAP\ Chatbot\ Iterative\ Retrieval.yml
# Should only match 'custom-iteration-start', NOT bare 'custo'
```

### 10.8 HTTP 400 / UnboundLocalError on Collaboration Queries

**Cause:** `import re` placed inside a function body that already uses `re` from module scope. Python treats `re` as local → `UnboundLocalError`.

**Fix:** Remove redundant `import re` inside function bodies. Use the module-level import.

### 10.9 "No papers found" / Metadata Queries Return Empty

**Cause:** Stale or missing env vars in Dify draft. The YAML stores only placeholders — real values come from `.env` via `import_dify_dsl.sh`.

**Fix:** Re-run import to inject current `.env` values:
```bash
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --skip-build --allow-cookie-auth --auto-login
```
Then publish. See §2.2 for the complete env var pipeline.

---

## 11. H100 LLM Upgrade Plan (2026-07-24)

### 11.1 Motivation

Current A2 GPU (16 GB VRAM) limits us to `qwen2.5:14b`. H100 (94 GB VRAM) enables larger models:

| Stufe | Modell | Größe | VRAM (mit Context) | Fokus |
|-------|--------|-------|---------------------|-------|
| 1 | `qwen3.5:35b` | 24 GB | ~30 GB (32K ctx) | Baseline: 2.5× größer. Testet `entity_lookup` m6A-Recall (#5), `author_lookup` Recall |
| 2 | `qwen3.5:122b` | 81 GB | ~90 GB (8K ctx) | Maximale Qualität. Braucht Context-Tuning |
| 3 | `qwen3-embedding` | ~8 GB | – | Embedding-Upgrade: ~4× nomic. Bessere Rankings für Methoden-Level-Konzepte |

### 11.2 Infrastructure

```bash
# Ollama auf H100 starten (Port 21434, GPU g5-1)
bash scripts/start_ollama.sh

# Modelle sind bereits gepullt und in Dify eingepflegt
```

### 11.3 Dify Provider Configuration

Die DSL YAML muss einen zweiten Ollama-Provider für H100 referenzieren:

```yaml
# Aktuell (A2):
provider: langgenius/ollama/ollama
# name: qwen2.5:14b

# Ziel (H100):
provider: langgenius/ollama/ollama  # oder custom H100 provider
# name: qwen3.5:35b
```

### 11.4 Test Plan

1. Provider im YAML konfigurieren und importieren
2. Vollständige Regression über alle 20 Test Cases
3. Fokus-Metriken: #5 m6A-Recall, `author_lookup` Recall, Comprehensiveness
4. Latenz-Vergleich: 14B (A2) vs. 35B (H100)
5. Bei Erfolg: 122B mit reduziertem Context testen

---

## Appendix A: File Reference

| File | Purpose |
|------|---------|
| `config/RMAP Chatbot Iterative Retrieval.yml` | Complete Dify DSL (prompts + graph + code) |
| `workflow_scripts/*.py` | Python source for code nodes |
| `scripts/build_dsl.py` | Inject code into YAML |
| `scripts/import_dify_dsl.sh` | Build + import + draft sync + KR fix |
| `scripts/export_dify_dsl.sh` | Export from Dify UI to local YAML |
| `scripts/debug_route_draft.sh` | Test via draft console API |
| `scripts/debug_route_runtime.sh` | Test via published app API |
| `scripts/fix_kr_dataset.sh` | Restore KR dataset after import |
| `scripts/update_dify_metadata.py` | Bulk metadata update via PubMed |
| `.env` | DIFY_API_KEY, DIFY_BASE_URL, DIFY_DATASET_ID, credentials – **single source of truth** for all config |
| `.secrets/dify_console_session.env` | Console auth tokens (cookie, csrf) |
| `docs/test-cases.md` | Living document: 20 test cases with status (✅ 19 · ⚠️ 1 · ❌ 0) |
| `docs/roadmap.md` | Feature roadmap & intent analysis |
| `docs/technical-guide.md` | This document |

## Appendix B: Common Commands

```bash
# Build DSL
.venv/bin/python scripts/build_dsl.py

# Import to Dify (+ draft sync + KR fix)
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --skip-build --allow-cookie-auth --auto-login

# Set env vars + publish (after import)
python3 -c "
import json, os, urllib.request
base = os.environ['DIFY_BASE_URL'].rstrip('/')
# ... (see §2.2 for full script)
"

# Test via draft API
bash scripts/debug_route_draft.sh \
  --app-id <your-app-id> \
  --query "What is m6A?" --allow-cookie-auth

# Test via runtime API
DIFY_BASE_URL="http://<your-dify-host>" \
DIFY_APP_API_KEY="app-<your-app-key>" \
bash scripts/debug_route_runtime.sh --query "What is m6A?"

# Export from Dify UI
bash scripts/export_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" --auto-login

# Extract code nodes from YAML
python scripts/extract_dsl_code.py

# Commit + release
git add -A && git commit -m "..." && git push
git tag -a v0.4.X -m "..." && git push --tags
gh release create v0.4.X --repo dieterich-lab/RmapDifyChatbot ...
```
