# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-06-23

### Changed

- **Question Classifier aus Iterator herausgezogen**: Der Question Classifier (`Route by Intent`) sitzt jetzt nach dem IF/ELSE (false-Pfad) außerhalb des Iterators. Der Iterator enthält nur noch `Fetch Full Paper`.
- **Metadata Query außerhalb des Iterators**: `Metadata Query` ist nun ein eigenständiger Code-Node und akzeptiert `paper_list` direkt.
- **Separate LLMs für drei Pfade**: Statt eines überfrachteten `Metadata LLM` gibt es jetzt `Content LLM` (Knowledge Retrieval), `Metadata LLM` (IS_COUNT_OR_LIST) und `Summary LLM` (IS_CONTENT) – jeweils mit fokussiertem Prompt.
- **Route LLM IF/ELSE**: Neue IF/ELSE-Node nach `Persist Paper Memory`, die anhand der QC-`class_id` zwischen `Metadata LLM` und `Summary LLM` routet.
- **Converge Paths**: Neuer Code-Node, der die Outputs von `Metadata Query` und `Iterator` merged und an `Update Paper Memory` weitergibt – dadurch wird der Conversation Memory auch bei Metadata-Queries aktualisiert.

## [0.2.1] - 2026-06-23

### Fixed

- **Variable Aggregator removed**: The Variable Aggregator node inside the Paper Iterator was unnecessary and caused corrupted metadata in `Update Paper Memory` (mixed Metadata Query text with full paper context). The Iterator now outputs `Metadata Query.result` directly. ([339038b](https://github.com/dieterich-lab/RmapDifyChatbot/commit/339038b))
- **Update Paper Memory**: Now handles both flat pipe-separated strings and array-of-strings format from the iterator output. ([339038b](https://github.com/dieterich-lab/RmapDifyChatbot/commit/339038b))

[0.2.1]: https://github.com/dieterich-lab/RmapDifyChatbot/compare/v0.2.0...v0.2.1

## [0.2.0] - 2026-06-22

### Added

- **Workflow Code Extraction Pipeline**: Code nodes can now be maintained as separate Python files in `workflow_scripts/` with build/extract scripts for easier development ([01385ab](https://github.com/dieterich-lab/RmapDifyChatbot/commit/01385ab))
- **Auto-login Support**: Scripts now support `--auto-login` flag to refresh console tokens via `/console/api/login` for deployments without static API keys ([fd9849d](https://github.com/dieterich-lab/RmapDifyChatbot/commit/fd9849d))
- **Runtime Trace Logging**: SLURM jobs now log detailed runtime traces to separate log files for easier debugging ([e03d39c](https://github.com/dieterich-lab/RmapDifyChatbot/commit/e03d39c))
- **Zero-segment Detection**: Upload client now warns when Dify reports "completed" but produced zero searchable segments ([61f9c38](https://github.com/dieterich-lab/RmapDifyChatbot/commit/61f9c38))
- **DSL Export Script**: Added `export_dify_dsl.sh` for pulling workflow state from Dify ([faf671f](https://github.com/dieterich-lab/RmapDifyChatbot/commit/faf671f))
- **BAML Trace Logging**: Author extraction now supports `AUTHOR_EXTRACTION_TRACE` for debugging LLM calls ([61f9c38](https://github.com/dieterich-lab/RmapDifyChatbot/commit/61f9c38))

### Changed

- **GPU Node**: SLURM jobs switched from gpu-g4-1 (ampere) to gpu-g5-1 (hopper) for better availability ([e03d39c](https://github.com/dieterich-lab/RmapDifyChatbot/commit/e03d39c))
- **Turn-2 Pipeline**: Consolidated Turn-2 metadata extraction into single LLM call for efficiency ([aabee2f](https://github.com/dieterich-lab/RmapDifyChatbot/commit/aabee2f))
- **Fetch Full Paper**: Now uses dynamic text budget based on document token count ([0d667d3](https://github.com/dieterich-lab/RmapDifyChatbot/commit/0d667d3))
- **Auth Scripts**: Refactored for brevity, added cookie/CSRF extraction from auto-login responses ([c2821f3](https://github.com/dieterich-lab/RmapDifyChatbot/commit/c2821f3))

### Fixed

- **Import Script**: Now always syncs Dify Draft after import to prevent stale workflow state ([ed1b206](https://github.com/dieterich-lab/RmapDifyChatbot/commit/ed1b206))
- **Doc-ID Ambiguity**: Resolved doc-ID collision in Load Whole Paper Fallback node ([0ce5de1](https://github.com/dieterich-lab/RmapDifyChatbot/commit/0ce5de1))
- **Two-turn Pipeline**: Repaired broken iterative-retrieval logic ([b81e192](https://github.com/dieterich-lab/RmapDifyChatbot/commit/b81e192))
- **Dataset API Key**: Added normalization guard to prevent accidental use of app-keys for dataset endpoints ([f1e740f](https://github.com/dieterich-lab/RmapDifyChatbot/commit/f1e740f))

### Refactored

- Removed dead follow-up gate node and related artifacts ([b5bd244](https://github.com/dieterich-lab/RmapDifyChatbot/commit/b5bd244), [776d0ad](https://github.com/dieterich-lab/RmapDifyChatbot/commit/776d0ad), [4288252](https://github.com/dieterich-lab/RmapDifyChatbot/commit/4288252))
- Simplified Turn-2 by replacing KR chain with direct segments fetch ([b72e2ef](https://github.com/dieterich-lab/RmapDifyChatbot/commit/b72e2ef))
- Moved Paper Map LLM outside iteration for single combined call ([5e44692](https://github.com/dieterich-lab/RmapDifyChatbot/commit/5e44692))

### Documentation

- Updated iterative retrieval section with architecture diagrams and node references ([44ec3a8](https://github.com/dieterich-lab/RmapDifyChatbot/commit/44ec3a8))
- Fixed flowchart labels to reflect paper_list state accurately ([ea0d1c4](https://github.com/dieterich-lab/RmapDifyChatbot/commit/ea0d1c4))
- Documented auto-login setup and usage ([cab4184](https://github.com/dieterich-lab/RmapDifyChatbot/commit/cab4184))
- Added workflow_scripts/README.md for code maintenance workflow

## [0.1.0] - 2026-06-01

Initial release with core functionality:
- Dify advanced-chat workflow for iterative paper retrieval
- Hybrid metadata extraction (regex + LLM fallback)
- Bulk paper upload tooling
- SLURM integration for GPU-accelerated processing
- Console API authentication helpers

[0.2.0]: https://github.com/dieterich-lab/RmapDifyChatbot/compare/milestone-2026-06-01-pre-lean...v0.2.0
[0.1.0]: https://github.com/dieterich-lab/RmapDifyChatbot/releases/tag/milestone-2026-06-01-pre-lean
