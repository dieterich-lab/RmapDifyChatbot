#!/usr/bin/env python3
"""
Extract code from Dify DSL code nodes into separate Python files.

Usage:
    python scripts/extract_dsl_code.py

This reads the DSL YAML and extracts all code nodes into workflow_scripts/
for easier editing and version control.
"""

import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"
SCRIPTS_DIR = REPO_ROOT / "workflow_scripts"


def sanitize_filename(title: str) -> str:
    """Convert node title to a valid Python filename."""
    return title.lower().replace(" ", "_").replace("-", "_") + ".py"


def extract_code_nodes(dsl_path: Path, output_dir: Path) -> None:
    """Extract all code nodes from DSL to separate Python files."""

    print(f"Loading DSL from: {dsl_path}")
    with open(dsl_path, "r") as f:
        data = yaml.safe_load(f)

    nodes = data["workflow"]["graph"]["nodes"]
    code_nodes = [n for n in nodes if n["data"].get("type") == "code"]

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nExtracting {len(code_nodes)} code nodes to {output_dir}:")

    for i, node in enumerate(code_nodes, 1):
        node_id = node["id"]
        title = node["data"].get("title", "Untitled")
        code = node["data"].get("code", "")

        filename = sanitize_filename(title)
        filepath = output_dir / filename

        # Write with header comments for traceability
        with open(filepath, "w") as f:
            f.write(f"# Code Node: {title}\n")
            f.write(f"# Node ID: {node_id}\n\n")
            f.write(code)

        print(f"  {i}. {title:<30} -> {filename}")

    print(f"\n✅ Extracted {len(code_nodes)} files to {output_dir}/")


def main():
    dsl_path = CONFIG_DIR / "RMAP Chatbot Iterative Retrieval.yml"
    output_dir = SCRIPTS_DIR

    if not dsl_path.exists():
        print(f"❌ Error: DSL not found at {dsl_path}")
        return 1

    extract_code_nodes(dsl_path, output_dir)
    return 0


if __name__ == "__main__":
    exit(main())
