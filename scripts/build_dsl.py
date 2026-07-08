#!/usr/bin/env python3
"""
Build Dify DSL by injecting code from workflow_scripts/ into the YAML template.

Usage:
    python scripts/build_dsl.py

This reads the base DSL, injects code from workflow_scripts/*.py into the
corresponding code nodes, and writes the result to config/.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "workflow_scripts"
CONFIG_DIR = REPO_ROOT / "config"

# Map node titles to script filenames
NODE_TO_SCRIPT = {
    "Final Answer Sanitizer": "final_answer_sanitizer.py",
    "KR Chunk Filter": "kr_chunk_filter.py",
    "Metadata Query": "metadata_query.py",
    "Parse Extractor Paper List": "parse_extractor_paper_list.py",
    "Follow-up Memory Subset": "follow_up_memory_subset.py",
    "Resolve Paper List": "resolve_paper_list.py",
    "Update Paper Memory": "update_paper_memory.py",
    "Fetch Full Paper": "fetch_full_paper.py",
    "Parse Router Output": "parse_router_output.py",
}


def strip_header_comments(code: str) -> str:
    """Remove the header comments we added during extraction."""
    lines = code.split("\n")
    clean_lines = []
    skip_header = True

    for line in lines:
        if skip_header and line.startswith("# "):
            continue
        if skip_header and line.strip() == "":
            continue
        skip_header = False
        clean_lines.append(line)

    return "\n".join(clean_lines)


def build_dsl(input_path: Path, output_path: Path) -> None:
    """Build the final DSL by injecting code from workflow_scripts/."""

    print(f"Loading base DSL from: {input_path}")
    with open(input_path, "r") as f:
        data = yaml.safe_load(f)

    nodes = data["workflow"]["graph"]["nodes"]
    code_nodes = [n for n in nodes if n["data"].get("type") == "code"]

    print(f"\nInjecting code into {len(code_nodes)} nodes:")

    for node in code_nodes:
        title = node["data"].get("title", "")

        if title not in NODE_TO_SCRIPT:
            print(f"  ⚠️  {title:<30} - no script mapping found, skipping")
            continue

        script_file = SCRIPTS_DIR / NODE_TO_SCRIPT[title]

        if not script_file.exists():
            print(f"  ❌ {title:<30} - script not found: {script_file}")
            continue

        with open(script_file, "r") as f:
            code = f.read()

        # Strip our header comments before injection
        code = strip_header_comments(code)

        node["data"]["code"] = code
        print(f"  ✅ {title:<30} - injected {len(code)} chars from {script_file.name}")

    print(f"\nWriting final DSL to: {output_path}")
    with open(output_path, "w") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

    print("✅ Build complete!")


def main():
    input_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"
    output_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"

    # Safety check: ensure workflow_scripts/ exists
    if not SCRIPTS_DIR.exists():
        print(f"❌ Error: {SCRIPTS_DIR} not found")
        print("   Run the extraction script first to create workflow_scripts/")
        sys.exit(1)

    build_dsl(input_path, output_path)


if __name__ == "__main__":
    main()
