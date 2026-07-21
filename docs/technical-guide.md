# RMAP Chatbot – Technical Guide

> **Audience:** Developers taking over maintenance and extension of the chatbot.
> **Last updated:** 2026-07-20 · v0.4.8 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb`

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
- 5 query intents, 6 LLM nodes (all qwen2.5:14b via Ollama)
- 7 code nodes (Python, injected via build pipeline)
- 1 knowledge-retrieval node (hybrid keyword 0.7 + vector 0.3, top_k=100)
- Dataset: `<your-dataset-id>` (82 papers, nomic-embed-text-v2-moe)

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

### 2.2 How the Dataset Key Reaches the Metadata Query Node

The most critical key flow is the dataset key → Metadata Query code node:

```
┌─────────────────────────────────────────────────────────────────┐
│  Dify App Environment Variables (set via console API)            │
│  ┌──────────────────────┬─────────────────────────────────────┐ │
│  │ DIFY_API_KEY         │ dataset-<your-dataset-key>    │ │
│  │ DIFY_DATASET_ID      │ <your-dataset-id>│ │
│  └──────────────────────┴─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
        │
        │ Dify runtime injects env vars into code node execution
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Metadata Query code node (workflow_scripts/metadata_query.py)   │
│                                                                  │
│  api_key = os.getenv("DIFY_API_KEY") or api_key_input or ""      │
│                                                                  │
│  api_key_input is mapped from the DSL variable binding:          │
│    - value_selector: [env, DIFY_API_KEY]                         │
│    - variable: api_key_input                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Critical detail:** The DSL YAML specifies variable bindings for each code node. For Metadata Query:

```yaml
variables:
  - value_selector: [env, DIFY_API_KEY]    # ← reads from Dify env vars
    value_type: string
    variable: api_key_input
  - value_selector: [env, DIFY_DATASET_ID]
    value_type: string
    variable: dataset_id_input
```

**After every `import_dify_dsl.sh` run, the env vars must be re-set** because the import replaces the draft graph (which includes the env vars). The fix script sets them via:

```python
# POST to /console/api/apps/{id}/workflows/draft with payload:
{
    "graph": ...,
    "environment_variables": [
        {"name": "DIFY_API_KEY", "value_type": "string",
         "value": "dataset-<your-dataset-key>", "description": "..."},
        {"name": "DIFY_DATASET_ID", "value_type": "string",
         "value": "<your-dataset-id>", "description": "..."}
    ],
    ...
}
```

Then the same payload is POSTed to `/console/api/apps/{id}/workflows/publish` to propagate to the published (runtime) app.

### 2.3 Key Rotation Procedure

When the dataset API key expires:

```bash
# 1. Create new key in Dify UI: Datasets → RMAP Papers → API Access
# 2. Update .env:
sed -i 's/DIFY_API_KEY=dataset-OLD_KEY/DIFY_API_KEY=dataset-NEW_KEY/' .env

# 3. Set in Dify app:
python3 -c "
# ... (POST to /console/api/apps/{id}/workflows/draft with new env vars)
# ... (POST to /console/api/apps/{id}/workflows/publish)
"

# 4. Verify:
curl "http://rmap-chatbot-demo-dify/v1/datasets?page=1" \
  -H "Authorization: Bearer dataset-NEW_KEY"
```

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
2. **Import**: POSTs YAML to `/console/api/apps/imports`
3. **Draft sync**: Fetches current draft hash, then POSTs `{graph, features, environment_variables, conversation_variables, hash}` to `/console/api/apps/{id}/workflows/draft`
4. **KR dataset fix**: Dify export/import sometimes strips `dataset_ids` from the Knowledge Retrieval node (id `17785930638200`). This step restores it from `DIFY_DATASET_ID` in `.env`. Still necessary as of v0.4.8.

**After import, always re-set env vars and publish** (see §2.2).

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
DIFY_BASE_URL="http://rmap-chatbot-demo-dify" \
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

# 3. Import to Dify
bash scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" \
  --skip-build --allow-cookie-auth --auto-login

# 4. Set env vars + publish (MUST do after every import!)
python3 -c "
import json, os, urllib.request
base = os.environ['DIFY_BASE_URL'].rstrip('/')
app_id = '16d50bee-bc86-4bda-bb56-a861743f3ddb'
# ... fetch draft, build payload with env vars, POST to draft + publish
"

# 5. Test
# Draft API:
bash scripts/debug_route_draft.sh --app-id 16d50bee-... \
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

## 9. Test Suite & Regression Testing

### 9.1 Test Cases Overview

16 test cases in `docs/test-cases.md`, covering all 5 intents:

| Status | Count | Cases |
|--------|-------|-------|
| ✅ Passing | 13 | #1, #2, #3, #4, #6, #7, #8, #9, #10, #11, #12, #14, #15 |
| ⚠️ Known Issue | 2 | #5 (entity recall, LLM model limit), #13 (Mark Helm timeout) |
| ❌ Known Limitation | 1 | #16 (PI collaboration, architectural gap) |

### 9.2 Running Regression Tests

**Quick smoke test (draft API):**
```bash
bash scripts/debug_route_draft.sh --app-id 16d50bee-... \
  --query "Which papers are (co-) authored by Christoph Dieterich?" \
  --allow-cookie-auth
# Expected: "8 papers" with all 8 listed including Sci-ModoM
```

**Full regression (runtime API):**
```bash
DIFY_BASE_URL="http://rmap-chatbot-demo-dify" \
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

- [ ] #1: "Which papers are (co-) authored by Christoph Dieterich?" → "8 papers" ✅
- [ ] #4: "Who has worked on tRNA modifications?" → No "Science Journals — AAAS", quotes present ✅
- [ ] #6: "Find papers by Francesca Tuorto" → metadata_list format, not content_summary ✅
- [ ] #12: "Who is using HEK cells?" → No "likely involved" / "could be implied" ✅
- [ ] #15 (Turn 2): "Group them by journal" → Groups by journal, not all 81 papers ✅

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

**Mitigation:** `MAX_PAPERS_FOR_SUMMARY = 15` in `parse_router_output.py`. Still slow for 15 papers + LLM processing.

### 10.5 env vars Lost After Import

**Cause:** `import_dify_dsl.sh` replaces the draft graph, which clears env vars.

**Fix:** Always re-set env vars and publish after every import (see §5.1 step 4).

### 10.6 Knowledge Retrieval Returns Wrong Dataset

**Cause:** `dataset_ids` stripped during import.

**Fix:** `import_dify_dsl.sh` auto-fixes via `fix_kr_dataset()`. If manual fix needed:
```bash
bash scripts/fix_kr_dataset.sh --app-id 16d50bee-... --auto-login
```

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
| `docs/test-cases.md` | Living document: 16 test cases with status |
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
  --app-id 16d50bee-bc86-4bda-bb56-a861743f3ddb \
  --query "What is m6A?" --allow-cookie-auth

# Test via runtime API
DIFY_BASE_URL="http://rmap-chatbot-demo-dify" \
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
