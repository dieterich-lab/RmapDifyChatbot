# Release Notes: milestone-routing-stable-v1

Date: 2026-05-18

## Highlights

- Stabilized two-path query routing in Dify advanced-chat workflow.
- Restored and validated intended graph:
  - `Start -> Query Rewriter -> Question Classifier`
  - Class 1: `Knowledge Retrieval -> Knowledge LLM -> Answer`
  - Class 2: `Parameter Extractor -> Metadata Router (Code) -> Metadata LLM -> Answer`
- Fixed metadata query routing regressions for author/count/list requests.
- Hardened metadata filtering logic for author names (full name vs initials).

## Routing Behavior (Validated)

- Content question (methods/findings) routes to `Knowledge Route`.
- Metadata count/list/filter questions route to `Metadata Route`.

## Key Fixes

- Classifier tuning:
  - stronger metadata intent patterns,
  - deterministic tie-break toward metadata for ambiguous count/list/filter queries,
  - input switched to raw `sys.query`.
- Parameter extractor tuning:
  - schema relaxed to avoid failure on optional fields,
  - improved author extraction instructions for patterns like `authored by`, `co-authored by`, `von`.
- Metadata router code fixes:
  - indentation/runtime fixes,
  - robust `author_match` for initials and surname matching,
  - stable dataset metadata filtering and output formatting.

## Tooling Improvements

- `scripts/import_dify_dsl.sh`
  - API-key-first mode,
  - clearer fallback behavior for deployments without console API key support.
- `scripts/debug_route_draft.sh`
  - reusable draft-run diagnostics script for route verification and output inspection.

## Repository Cleanup

- Removed generated caches and redundant local artifacts.
- Added `.gitignore` coverage for:
  - Python caches,
  - virtual env/editor artifacts,
  - mypy cache,
  - report outputs,
  - slurm log files,
  - local raw paper corpus.

## Notes

- Some self-hosted Dify deployments expose app API keys for `/v1/...` but not console API keys for `/console/api/...`.
- In such setups, console draft operations may require cookie + CSRF session auth.
