#!/usr/bin/env python3
"""
Add IF/ELSE routing to bypass Metadata LLM for pre-formatted outputs.

After:  Persist Paper Memory (1778800001003)
            → IF/ELSE (list_mode?)
                ├─ set → Final Answer Sanitizer (direct passthrough)
                └─ else → Metadata LLM → Final Answer Sanitizer (existing)

Also adds result_text variable from Metadata Query to Sanitizer.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def migrate():
    input_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"
    output_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"

    print(f"Loading: {input_path}")
    with open(input_path, "r") as f:
        data = yaml.safe_load(f)

    nodes = data["workflow"]["graph"]["nodes"]
    edges = data["workflow"]["graph"]["edges"]

    # ── Find key nodes ──────────────────────────────────────────
    persist_mem = None
    metadata_llm = None
    sanitizer = None
    for n in nodes:
        t = n["data"].get("title", "")
        if t == "Persist Paper Memory" and n["id"] == "1778800001003":
            persist_mem = n
        elif t == "Metadata LLM":
            metadata_llm = n
        elif t == "Final Answer Sanitizer":
            sanitizer = n

    if not all([persist_mem, metadata_llm, sanitizer]):
        print("ERROR: Could not find required nodes")
        return 1

    # ── Build IF/ELSE node ──────────────────────────────────────
    if_else_id = "1778800001040"
    
    # Check if already exists, clean up
    for n in nodes:
        if n["id"] == if_else_id:
            print("Removing existing IF/ELSE node...")
            edges[:] = [
                e for e in edges
                if e["id"] not in (
                    f"{persist_mem['id']}-source-{if_else_id}-target",
                    f"{if_else_id}-set-{sanitizer['id']}-result_text",
                    f"{if_else_id}-false-{metadata_llm['id']}-target",
                )
            ]
            nodes[:] = [n for n in nodes if n["id"] != if_else_id]
            break

    pos = persist_mem["position"]
    if_else = {
        "id": if_else_id,
        "type": "custom",
        "position": {"x": pos["x"] + 260, "y": pos["y"]},
        "positionAbsolute": {"x": pos["x"] + 260, "y": pos["y"]},
        "sourcePosition": "right",
        "targetPosition": "left",
        "width": 242,
        "height": 124,
        "selected": False,
        "data": {
            "type": "if-else",
            "title": "Metadata LLM Bypass",
            "selected": False,
            "cases": [
                {
                    "case_id": "set",
                    "conditions": [
                        {
                            "id": "list-mode-is-set",
                            "varType": "string",
                            "variable_selector": ["1778800001033", "list_mode"],
                            "comparison_operator": "is not",
                            "value": "",
                        }
                    ],
                    "id": "set",
                    "logical_operator": "and",
                }
            ],
        },
    }
    nodes.append(if_else)

    # ── Remove old edge: Persist → Metadata LLM ─────────────────
    old_edge_id = f"{persist_mem['id']}-source-{metadata_llm['id']}-target"
    edges[:] = [e for e in edges if e["id"] != old_edge_id]
    print(f"Removed edge: {old_edge_id}")

    # ── Add new edges ───────────────────────────────────────────
    # Persist Paper Memory → IF/ELSE
    edges.append({
        "id": f"{persist_mem['id']}-source-{if_else_id}-target",
        "source": persist_mem["id"],
        "sourceHandle": "source",
        "target": if_else_id,
        "targetHandle": "target",
        "type": "custom",
        "data": {"isInLoop": False, "sourceType": "assigner", "targetType": "if-else"},
    })

    # IF/ELSE (list_mode set) → Sanitizer (direct result_text passthrough)
    edges.append({
        "id": f"{if_else_id}-set-{sanitizer['id']}-result_text",
        "source": if_else_id,
        "sourceHandle": "set",
        "target": sanitizer["id"],
        "targetHandle": "result_text",
        "type": "custom",
        "data": {"isInLoop": False, "sourceType": "if-else", "targetType": "code"},
    })

    # IF/ELSE (false) → Metadata LLM (existing LLM path)
    edges.append({
        "id": f"{if_else_id}-false-{metadata_llm['id']}-target",
        "source": if_else_id,
        "sourceHandle": "false",
        "target": metadata_llm["id"],
        "targetHandle": "target",
        "type": "custom",
        "data": {"isInLoop": False, "sourceType": "if-else", "targetType": "llm"},
    })

    # ── Add result_text variable to Sanitizer ───────────────────
    svars = sanitizer["data"].get("variables", [])
    svars = [v for v in svars if v.get("variable") != "result_text"]
    svars.append({
        "variable": "result_text",
        "value_selector": ["17786780698570", "result_text"],
        "value_type": "string",
    })
    sanitizer["data"]["variables"] = svars

    print(f"Added result_text variable to Sanitizer")
    print(f"Nodes: {len(nodes)} (was {len(nodes) - 1})")
    print(f"Edges: {len(edges)}")

    # ── Write output ────────────────────────────────────────────
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✅ Migration complete!")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
