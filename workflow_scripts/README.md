# Workflow Code Scripts

Diese Directory enthält die Python-Code-Nodes aus dem Dify Workflow als separate Dateien.

## Problem

Dify DSL (YAML) speichert Python-Code direkt eingebettet in den Code-Nodes. Das macht es schwierig:
- Code zu editieren (schlechtes Syntax-Highlighting in YAML)
- Änderungen zu verfolgen (Git-Diffs sind unübersichtlich)
- Code zu testen (inline in YAML schwer testbar)

## Lösung

**Source of Truth:** Python-Files hier in `workflow_scripts/`

**Build-Pipeline:** Skripte injizieren den Code automatisch in die DSL

## Workflow

### 1. Code bearbeiten

Ändere die Python-Dateien hier:
- `final_answer_sanitizer.py`
- `metadata_query.py`
- `parse_extractor_paper_list.py`
- `follow_up_memory_subset.py`
- `resolve_paper_list.py`
- `update_paper_memory.py`
- `fetch_full_paper.py`

### 2. DSL rebuilden

```bash
python scripts/build_dsl.py
```

Dies injiziert den Code in `config/RMAP Chatbot Iterative Retrieval.yml`.

### 3. In Dify importieren

```bash
scripts/import_dify_dsl.sh "config/RMAP Chatbot Iterative Retrieval.yml" --app-id <app-id>
```

## Änderungen aus Dify extrahieren

Falls du Code direkt in Dify bearbeitet hast:

```bash
python scripts/extract_dsl_code.py
```

Dies überschreibt die lokalen Dateien mit dem Code aus der DSL.

## Node-Mapping

| Python-File | Dify Node Title |
|-------------|----------------|
| `final_answer_sanitizer.py` | Final Answer Sanitizer |
| `metadata_query.py` | Metadata Query |
| `parse_extractor_paper_list.py` | Parse Extractor Paper List |
| `follow_up_memory_subset.py` | Follow-up Memory Subset |
| `resolve_paper_list.py` | Resolve Paper List |
| `update_paper_memory.py` | Update Paper Memory |
| `fetch_full_paper.py` | Fetch Full Paper |

## Hinweise

- Die Header-Kommentare (`# Code Node: ...`, `# Node ID: ...`) werden beim Build automatisch entfernt
- YAML-Formatierung kann sich beim Build leicht ändern (Zeilenumbrüche), aber die Funktionalität bleibt gleich
- **Wichtig:** Bearbeite die DSL-Datei nicht manuell für Code-Änderungen — nutze die Python-Files hier
