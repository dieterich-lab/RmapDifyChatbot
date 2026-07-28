# v0.4.15 – Collaboration Analysis (#16) + Dual-Author Queries

## 🧑‍🤝‍🧑 #16 FIXED: Co-Author Collaboration Analysis

The chatbot can now answer questions about researcher collaborations — no new intent or LLM needed. Uses the Dataset API to compute co-author pair frequencies directly from paper metadata.

**Three query types:**

| Query | Example | Result |
|---|---|---|
| Global ranking | "Who has collaborated the most?" | Top 20 pairs: Helm+Motorin (10 papers) |
| Single-author | "Co-authors of Mark Helm" | 197 pairs involving Helm |
| Dual-author | "Papers co-authored by Helm and Motorin" | 11 shared papers with titles |

```
"Who has collaborated the most?"
→ Co-Author Collaboration Analysis
→ Dataset: 84 papers, 78 with ≥2 authors
→ Unique co-author pairs found: 3,253
→ Top: Mark Helm + Yuri Motorin — 10 papers
```

## 🔧 What changed

- **Computation mode in `metadata_list`**: `_compute_collaborations()` runs after document collection, before filter logic. Returns pre-formatted Markdown, bypasses LLM.
- **Collaboration query guards**: 12 markers (`collaborat`, `co-author`, `published together`, `share papers`, `co-autoren`…) detected in `parse_router_output.py`.
- **Dual-author regex**: 5 patterns ordered specific→generic to avoid false matches. Pipe-separated targets (`"Helm|Motorin"`) for exact pair matching.
- **Case-preserving extraction**: Names extracted from `q_orig` (not `q.lower()`) for correct display.
- **Curl payload fix**: `import_dify_dsl.sh` now uses `--data @tempfile` for 125KB DSL payloads.
- **Dify Publish fix**: Phantom validation checklist resolved in Dify UI.

## 🏗️ Architecture

```
parse_router_output.py          metadata_query.py
┌──────────────────────────┐    ┌──────────────────────────────────┐
│ Collaboration guard       │    │ _compute_collaborations()         │
│ detects collab markers    │───▶│ - LastName,FirstName → First Last │
│ extracts author name(s)   │    │ - Pairwise counting (Counter)     │
│ → collaboration_mode      │    │ - target_author / dual filter     │
│ → paper_list=[]           │    │ - Pre-formatted Markdown output   │
│ → multi_author_bypass=True│    │ - LLM bypassed                    │
└──────────────────────────┘    └──────────────────────────────────┘
```

## Why the bypass?

Same LLM bypass pattern as v0.4.14 — co-author pair data is computationally derived from metadata. No LLM synthesis needed; pre-formatted output goes directly to Final Answer Sanitizer.

## What didn't make it

- **`publication_timeline`**, **`journal_distribution`**, **`author_productivity`**: Noted as planned computation modes, but not yet implemented. The `_compute_collaborations()` function already has the document collection infrastructure — these modes only need formatting logic.

## Documentation

- `docs/technical-guide.md` §8.11: Collaboration Analysis with code patterns and query types
- `docs/lessons-learned.md`: Updated with collaboration computation pattern
- `docs/intent-architecture.md`: Collaboration as computation mode within `metadata_list`
- `docs/test-cases.md` #16: Updated from ❌ to ✅

## Regression Tally

✅ 18 · ⚠️ 1 (#5, m6A missing) · ❌ 1 (#18, Lauren Saunders out of scope)

#16 moved from ❌ (architectural gap) to ✅.

---

**Full Changelog**: [v0.4.14...v0.4.15](https://github.com/dieterich-lab/RmapDifyChatbot/compare/v0.4.14...v0.4.15)
