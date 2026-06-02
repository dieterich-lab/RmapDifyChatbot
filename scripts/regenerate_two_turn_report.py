#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/pwiesenbach/rmap-chatbot")
REPORT = ROOT / "reports" / "two_turn_node_io_report.md"
AUDIT = ROOT / "reports" / "two_turn_node_io_audit.json"
TURN1_EVENTS = ROOT / "reports" / "two_turn_turn1_events.jsonl"
TURN2_EVENTS = ROOT / "reports" / "two_turn_turn2_events.jsonl"
TURN1_NODES = ROOT / "reports" / "two_turn_turn1_nodes.json"
TURN2_NODES = ROOT / "reports" / "two_turn_turn2_nodes.json"

DROP_KEYS = {
    "usage",
    "completion_price",
    "completion_price_unit",
    "completion_tokens",
    "completion_unit_price",
    "prompt_price",
    "prompt_price_unit",
    "prompt_tokens",
    "prompt_unit_price",
    "total_price",
    "total_tokens",
    "currency",
    "latency",
    "time_to_first_token",
    "time_to_generate",
    "finish_reason",
}
MAX_STRING = 4000


def first_conversation_id(events_path: Path) -> str:
    if not events_path.exists():
        return "unknown"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        cid = obj.get("conversation_id")
        if cid:
            return str(cid)
        data = obj.get("data") or {}
        cid = data.get("conversation_id")
        if cid:
            return str(cid)
    return "unknown"


def sanitize(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS:
                continue
            if k.startswith("sys."):
                if k == "sys.query":
                    key = "query"
                else:
                    continue
            elif k == "#context#":
                key = "context"
            else:
                key = k
            sv = sanitize(v)
            if sv in ({}, [], None, ""):
                continue
            out[key] = sv
        return out
    if isinstance(value, list):
        arr = [sanitize(v) for v in value]
        return [v for v in arr if v not in ({}, [], None, "")]
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            return value[:MAX_STRING] + " ... [truncated]"
        return value
    return value


def main() -> None:
    turn1_nodes = json.loads(TURN1_NODES.read_text(encoding="utf-8"))
    turn2_nodes = json.loads(TURN2_NODES.read_text(encoding="utf-8"))

    conversation_id = first_conversation_id(TURN1_EVENTS)
    meta = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turn1_http": "200",
        "turn2_http": "200",
        "conversation_id": conversation_id,
        "turn1_query": "Which papers have been (co-)authored by Christoph Dieterich",
        "turn2_query": "Please summarize those papers",
    }

    audit_payload = {
        "meta": meta,
        "turn1_nodes": turn1_nodes,
        "turn2_nodes": turn2_nodes,
    }
    AUDIT.write_text(
        json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = []
    lines.append("# Two-Turn Node I/O Audit (Cleaned)")
    lines.append("")
    lines.append(f"- Generated at: {meta['generated_at']}")
    lines.append(f"- Turn 1 HTTP: {meta['turn1_http']}")
    lines.append(f"- Turn 2 HTTP: {meta['turn2_http']}")
    lines.append(f"- Conversation ID: {meta['conversation_id']}")
    lines.append(f"- Turn 1 query: {meta['turn1_query']}")
    lines.append(f"- Turn 2 query: {meta['turn2_query']}")
    lines.append("")
    lines.append(f"- Turn 1 node count: {len(turn1_nodes)}")
    lines.append(f"- Turn 2 node count: {len(turn2_nodes)}")
    lines.append("")

    for turn_name, nodes in [("Turn 1", turn1_nodes), ("Turn 2", turn2_nodes)]:
        lines.append(f"## {turn_name} Nodes")
        for node in nodes:
            node_id = node.get("node_id", "")
            title = node.get("title", "")
            node_type = node.get("node_type", "")
            status = node.get("status", "")
            iteration_id = node.get("iteration_id")

            inputs = sanitize(node.get("inputs", {}))
            outputs = sanitize(node.get("outputs", {}))

            lines.append(f"### {title} ({node_id})")
            lines.append(f"- Type: {node_type}")
            lines.append(f"- Status: {status}")
            if iteration_id:
                lines.append(f"- Iteration ID: {iteration_id}")
            lines.append("Inputs:")
            lines.append("```json")
            lines.append(json.dumps(inputs, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("Outputs:")
            lines.append("```json")
            lines.append(json.dumps(outputs, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"UPDATED={REPORT}")
    print(f"UPDATED={AUDIT}")
    print(
        f"TURN1_NODES={len(turn1_nodes)} TURN2_NODES={len(turn2_nodes)} CID={conversation_id}"
    )


if __name__ == "__main__":
    main()
