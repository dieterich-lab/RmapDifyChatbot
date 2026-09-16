# Workflow Code Scripts

This directory contains the Python code nodes from the Dify Workflow as separate files.

## Problem

Dify DSL (YAML) stores Python code directly embedded in Code Nodes. This makes it difficult to:
- Edit code (poor syntax highlighting in YAML)
- Track changes (Git diffs are hard to read)
- Test code (inline in YAML is hard to test)

## Solution

**Source of Truth:** Python files here in `workflow_scripts/`

**Build Pipeline:** Scripts inject the code automatically into the DSL

## Workflow

### 1. Edit code

Edit the Python files here (see Node-Mapping below for the full list).

### 2. Rebuild DSL

```bash
python scripts/build_dsl.py
```

This injects the code into `config/RMAP Chatbot Iterative Retrieval.yml`.

### 3. Import into Dify

```bash
scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" --app-id <app-id>
```

## Extract changes from Dify

If you edited code directly in Dify:

```bash
python scripts/extract_dsl_code.py
```

This overwrites the local files with the code from the DSL.

## Node-Mapping

| Python File | Dify Node Title |
|---|---|
| `parse_router_output.py` | Parse Router Output |
| `metadata_query.py` | Metadata Query |
| `kr_chunk_filter.py` | KR Chunk Filter |
| `kr_rrf.py` | KR RRF |
| `fetch_full_paper.py` | Fetch Full Paper |
| `final_answer_sanitizer.py` | Final Answer Sanitizer |
| `follow_up_memory_subset.py` | Follow-up Memory Subset |
| `parse_extractor_paper_list.py` | Parse Extractor Paper List |
| `resolve_paper_list.py` | Resolve Paper List |
| `update_metadata_paper_query.py` | Update Paper Memory (metadata branch) |
| `update_iterator_paper_memory.py` | Update Paper Memory (iterator branch) |

## Notes

- The header comments (`# Code Node: ...`, `# Node ID: ...`) are stripped automatically during build
- YAML formatting may change slightly during build (line breaks), but functionality stays the same
- **Important:** Do not manually edit the DSL file for code changes — use the Python files here
- Each code node runs in Dify's sandboxed execution environment — nodes cannot import shared modules
