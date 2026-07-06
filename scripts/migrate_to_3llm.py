#!/usr/bin/env python3
"""
Transform the iterative retrieval workflow from a single multi-intent
Extraction LLM to three dedicated, intent-routed LLMs.

Before:  Chunk Filter → Extraction LLM (all 3 intents in one prompt) → Sanitizer
After:   Chunk Filter → IF/ELSE (intent)
             ├─ author_lookup  → Author Extraction LLM   ─┐
             ├─ entity_lookup  → Entity Extraction LLM   ─┤→ Sanitizer
             └─ else           → KR Extraction LLM       ─┘
"""

import copy
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"

# ── Prompts ──────────────────────────────────────────────────────────

AUTHOR_PROMPT = (
    'Context (each chunk starts with "From paper:" followed by paper info):\n'
    "{{#context#}}\n\n"
    'You are answering: "{{#sys.query#}}"\n\n'
    "=== CRITICAL RULES ===\n"
    '1. ONLY extract authors from the "From paper:" headers.\n'
    '   Header format: "From paper: LastName1 Initials1, LastName2 Initials2, Year, Journal"\n'
    '2. ONLY list papers whose "From paper:" header appears in the context above.\n'
    "3. For each header, list EVERY author name found in it.\n"
    "4. Use the header's journal as the paper's journal.\n"
    "5. Derive a short paper topic from the chunk content as the title.\n"
    "6. Use a verbatim quote from the chunk as evidence of what they did.\n\n"
    "Format:\n"
    "**Paper Topic** (Journal)\n"
    '- FirstName LastName: "verbatim evidence quote from chunk"\n\n'
    'If no "From paper:" headers found: "Insufficient context."\n'
    'CRITICAL: NEVER list a paper or author NOT found in a "From paper:" header.\n'
    "NO fabricated names. NO <think>. Keep under 300 words."
)

ENTITY_PROMPT = (
    'Context (each chunk starts with "From paper:" followed by paper info):\n'
    "{{#context#}}\n\n"
    'You are answering: "{{#sys.query#}}"\n\n'
    "Scan ALL chunks and extract every named entity you can FIND IN THE CONTEXT:\n"
    "RNA modifications, methods, organisms, cell lines, proteins, tools.\n\n"
    "ONLY list entities that actually appear in the context.\n"
    "Format as a table:\n"
    "| Entity | Type | Paper |\n"
    "|--------|------|-------|\n\n"
    'If context lacks entities: "Insufficient context."\n\n'
    "CRITICAL: NEVER fabricate entities. NO <think>. Keep under 300 words."
)

KR_PROMPT = (
    'Context (each chunk starts with "From paper:" followed by paper info):\n'
    "{{#context#}}\n\n"
    'You are answering: "{{#sys.query#}}"\n\n'
    "Summarize using verbatim quotes from the context.\n"
    "Every sentence MUST contain words from the context.\n"
    'If context lacks information: "Insufficient context."\n\n'
    "CRITICAL: NEVER fabricate information. NO <think>. Keep under 300 words.\n"
    "Answer in the same language as the user."
)


def build_3llm_yaml():
    input_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"
    output_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"

    print(f"Loading: {input_path}")
    with open(input_path, "r") as f:
        data = yaml.safe_load(f)

    nodes = data["workflow"]["graph"]["nodes"]
    edges = data["workflow"]["graph"]["edges"]

    # ── Find existing nodes ─────────────────────────────────────────
    extraction_llm = None
    chunk_filter = None
    sanitizer = None
    for n in nodes:
        title = n["data"].get("title", "")
        if title == "Extraction LLM":
            extraction_llm = n
        elif title == "KR Chunk Filter":
            chunk_filter = n
        elif title == "Final Answer Sanitizer":
            sanitizer = n

    if not all([extraction_llm, chunk_filter, sanitizer]):
        print("ERROR: Could not find required nodes")
        return 1

    # ── Build the three LLM nodes ────────────────────────────────────
    base_llm = copy.deepcopy(extraction_llm)
    base_pos = base_llm["position"]

    # Author Extraction LLM — keep original ID & position
    author_llm = base_llm
    author_llm["data"]["title"] = "Author Extraction LLM"
    author_llm["data"]["prompt_template"][0]["text"] = AUTHOR_PROMPT
    author_llm["data"]["prompt_template"][0]["id"] = "author-extraction-prompt"

    # Entity Extraction LLM — new ID, offset position
    entity_llm = copy.deepcopy(base_llm)
    entity_llm["id"] = "1778800001037"
    entity_llm["data"]["title"] = "Entity Extraction LLM"
    entity_llm["data"]["prompt_template"][0]["text"] = ENTITY_PROMPT
    entity_llm["data"]["prompt_template"][0]["id"] = "entity-extraction-prompt"
    entity_llm["position"] = {"x": base_pos["x"], "y": base_pos["y"] + 120}
    entity_llm["positionAbsolute"] = {"x": base_pos["x"], "y": base_pos["y"] + 120}

    # KR Extraction LLM — new ID, offset position
    kr_llm = copy.deepcopy(base_llm)
    kr_llm["id"] = "1778800001038"
    kr_llm["data"]["title"] = "KR Extraction LLM"
    kr_llm["data"]["prompt_template"][0]["text"] = KR_PROMPT
    kr_llm["data"]["prompt_template"][0]["id"] = "kr-extraction-prompt"
    kr_llm["position"] = {"x": base_pos["x"], "y": base_pos["y"] + 240}
    kr_llm["positionAbsolute"] = {"x": base_pos["x"], "y": base_pos["y"] + 240}

    # ── Build IF/ELSE node ───────────────────────────────────────────
    if_else = {
        "id": "1778800001039",
        "type": "custom",
        "position": {"x": chunk_filter["position"]["x"] + 260, "y": base_pos["y"]},
        "positionAbsolute": {
            "x": chunk_filter["position"]["x"] + 260,
            "y": base_pos["y"],
        },
        "sourcePosition": "right",
        "targetPosition": "left",
        "width": 242,
        "height": 200,
        "selected": False,
        "data": {
            "type": "if-else",
            "title": "KR Intent Router",
            "selected": False,
            "cases": [
                {
                    "case_id": "author_lookup",
                    "conditions": [
                        {
                            "id": "intent-is-author",
                            "varType": "string",
                            "variable_selector": ["1778800001033", "intent"],
                            "comparison_operator": "is",
                            "value": "author_lookup",
                        }
                    ],
                    "id": "author_lookup",
                    "logical_operator": "and",
                },
                {
                    "case_id": "entity_lookup",
                    "conditions": [
                        {
                            "id": "intent-is-entity",
                            "varType": "string",
                            "variable_selector": ["1778800001033", "intent"],
                            "comparison_operator": "is",
                            "value": "entity_lookup",
                        }
                    ],
                    "id": "entity_lookup",
                    "logical_operator": "and",
                },
            ],
        },
    }

    # ── Remove old nodes, add new ones ───────────────────────────────
    # Remove old Extraction LLM (it's now replaced by author_llm at same ID)
    nodes[:] = [n for n in nodes if n["id"] not in ("1778800001034",)]
    # Add the three new LLMs and IF/ELSE
    nodes.extend([author_llm, entity_llm, kr_llm, if_else])

    # ── Update edges ─────────────────────────────────────────────────
    # Remove old edges
    edges[:] = [
        e
        for e in edges
        if e["id"]
        not in (
            "1778800001036-source-1778800001034-target",  # Chunk Filter → old Extraction LLM
            "1778800001034-source-1778800001013-target",  # old Extraction LLM → Sanitizer
        )
    ]

    # Chunk Filter → IF/ELSE
    edges.append(
        {
            "id": "1778800001036-source-1778800001039-target",
            "source": "1778800001036",
            "sourceHandle": "source",
            "target": "1778800001039",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "code", "targetType": "if-else"},
        }
    )

    # IF/ELSE → Author Extraction LLM (author_lookup case)
    edges.append(
        {
            "id": "1778800001039-author_lookup-1778800001034-target",
            "source": "1778800001039",
            "sourceHandle": "author_lookup",
            "target": "1778800001034",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "if-else", "targetType": "llm"},
        }
    )

    # IF/ELSE → Entity Extraction LLM (entity_lookup case)
    edges.append(
        {
            "id": "1778800001039-entity_lookup-1778800001037-target",
            "source": "1778800001039",
            "sourceHandle": "entity_lookup",
            "target": "1778800001037",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "if-else", "targetType": "llm"},
        }
    )

    # IF/ELSE → KR Extraction LLM (else / false)
    edges.append(
        {
            "id": "1778800001039-else-1778800001038-target",
            "source": "1778800001039",
            "sourceHandle": "false",
            "target": "1778800001038",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "if-else", "targetType": "llm"},
        }
    )

    # Author Extraction LLM → Sanitizer
    edges.append(
        {
            "id": "1778800001034-source-1778800001013-target",
            "source": "1778800001034",
            "sourceHandle": "source",
            "target": "1778800001013",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "llm", "targetType": "code"},
        }
    )

    # Entity Extraction LLM → Sanitizer
    edges.append(
        {
            "id": "1778800001037-source-1778800001013-target",
            "source": "1778800001037",
            "sourceHandle": "source",
            "target": "1778800001013",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "llm", "targetType": "code"},
        }
    )

    # KR Extraction LLM → Sanitizer
    edges.append(
        {
            "id": "1778800001038-source-1778800001013-target",
            "source": "1778800001038",
            "sourceHandle": "source",
            "target": "1778800001013",
            "targetHandle": "target",
            "type": "custom",
            "zIndex": 0,
            "data": {"isInLoop": False, "sourceType": "llm", "targetType": "code"},
        }
    )

    # ── Update Sanitizer variable mappings ───────────────────────────
    # Replace the old extraction_text mapping, add entity + kr
    sanitizer_vars = sanitizer["data"].get("variables", [])
    sanitizer["data"]["variables"] = [
        v for v in sanitizer_vars if v.get("variable") != "extraction_text"
    ]
    sanitizer["data"]["variables"].extend(
        [
            {
                "value_selector": ["1778800001034", "text"],
                "value_type": "string",
                "variable": "extraction_text",
            },
            {
                "value_selector": ["1778800001037", "text"],
                "value_type": "string",
                "variable": "entity_text",
            },
            {
                "value_selector": ["1778800001038", "text"],
                "value_type": "string",
                "variable": "knowledge_text",
            },
        ]
    )

    # ── Write output ─────────────────────────────────────────────────
    print(f"Writing to: {output_path}")
    with open(output_path, "w") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

    print("✅ Migration complete!")
    print(f"Nodes: {len(nodes)} (was {len(nodes) - 2})")
    print(f"Edges: {len(edges)}")
    return 0


if __name__ == "__main__":
    sys.exit(build_3llm_yaml())
