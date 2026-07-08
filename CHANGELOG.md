# Changelog

## [0.4.2] - 2026-07-08

### Changed

- **Chunk-Filter Dedup**: max chunks/paper von 3→1 reduziert. Verdoppelt die maximale Paper-Diversität im Context (bis zu 50 unique Papers bei top_k=50). Entity-Lookup: 3→6 Entities, kein "Insufficient context" mehr.
- **Hybrid Weights**: keyword_weight 0.4→0.7, vector_weight 0.6→0.3. Bevorzugt exakte Term-Matches für präzisere Retrieval-Ergebnisse.

### Results (2026-07-08, qwen2.5:14b, top_k=50)

| Intent | Query | Result |
|--------|-------|--------|
| `entity_lookup` | Which RNA modifications are most studied? | ✅ 6 Entities (war 3), Entity-Gruppierung, kein "Insufficient context". Neue: RNA editing, tRNA modifications, RNA methylation. |
| `author_lookup` | Who has worked on tRNA modifications? | 5 Papers, alle Autoren + Quotes. ⚠️ Recall unverändert 19% – Retrieval-Ranking-Bottleneck. |
| `knowledge_retrieval` | What is m6A and detection methods? | 5 Methoden, Inline-Citations. ⚠️ 2/5 Paper-Metadaten suboptimal (Filename-Fallback). |

## [0.4.1] - 2026-07-07

### Fixed

- **"Critical Reviews"-Bug (entity_lookup)**: Journal-Section-Header "Critical Reviews and Perspectives" wurde als Autor geparst. Gefixt durch Prompt-Redesign: "Use EXACT 'From paper:' header" + "NEVER extract author names from chunk body".
- **Buchkapitel-Metadaten (knowledge_retrieval)**: "ComputationalEpigenomicsandEpitranscriptomics" by "Pedro H. Oliveira Editor, Ethods In, ..." – kaputte Dify-Metadaten für Buchkapitel (Methods Mol Biol). Gefixt durch `_metadata_looks_garbled()` im Chunk-Filter: erkennt titel ohne Leerzeichen, "Editor"/"Series" in authors, nicht-numerisches Jahr, Seitenzahlen als Journal → fällt auf Dateinamen-Parsing zurück.

### Changed

- **Entity Extraction LLM**: Komplettes Prompt-Redesign. "Be COMPREHENSIVE – NO word limit", Entity-Gruppierung über Papers, "Use EXACT 'From paper:' header", Entity-Typen aus Content ableiten statt hardcoden.
- **KR Extraction LLM**: "Never extract author names from the chunk body — use only the 'From paper:' header" als subtile Guard-Message (kein CRITICAL-Block, der Inline-Citations zerstört).
- **KR Chunk Filter**: `_metadata_looks_garbled()` erkennt defekte Metadaten (Buchkapitel, fehlgeschlagene Extraktion). Verbesserter Dateinamen-Fallback parst strukturierte Info aus "Authors, Year, Journal, ..."-Format.

### Results (2026-07-07, qwen2.5:14b, top_k=50)

| Intent | Query | Result |
|--------|-------|--------|
| `entity_lookup` | Which RNA modifications are most studied in epitranscriptomics? | ✅ Kein "Critical Reviews"-Bug, Entity-Gruppierung (m6A mit 4 Papers), saubere Header-Citations. ⚠️ LLM stoppt bei 3 Mods ("Insufficient context") – Modell-Limit. |
| `knowledge_retrieval` | What is m6A and which methods are used to detect it? | ✅ Kein Buchkapitel-Garbling, Inline-Citations funktionieren, 4/4 Methoden mit sauberen Author-Listen. ⚠️ Methode 3 zitiert falsches Paper (DNA Adenine methylation statt m6A antibody methods) – Retrieval-Issue. |

## [0.4.0] - 2026-07-06

### Added

- **3-LLM Intent Architecture**: Extraction LLM durch drei dedizierte, intent-geroutete LLMs ersetzt: `Author Extraction LLM`, `Entity Extraction LLM`, `KR Extraction LLM`. Routing via neuen `KR Intent Router` (IF/ELSE auf `{{#1778800001033.intent#}}`). Kein Mixed Output mehr, jeder Prompt ist single-purpose.
- **`migrate_to_3llm.py`**: Python-Script zur Transformation des YAML-Workflows von Single-LLM zu 3-LLM-Architektur.

### Changed

- **3-LLM Prompts optimiert**: Alle drei Extraction-LLMs auf vollständige Autoren-Nennung optimiert.
  - `Author Extraction LLM`: "Authors: ... / Quote: ..." Format mit Few-Shot-Example. Listet ALLE Autoren (5-10 pro Paper).
  - `Entity Extraction LLM`: Paper-Spalte enthält jetzt "Title" by ALL authors (year).
  - `KR Extraction LLM`: Jede Behauptung wird mit Paper-Titel und ALLEN Autoren zitiert. "and colleagues" / "et al." explizit verboten.
- **Final Answer Sanitizer**: Autor-Anreicherung aus Chunk-Metadaten via neue Edge `KR Chunk Filter → Sanitizer`. `filtered_chunks` als Input (27 Edges).
- **KR Query Rewriter entfernt**: Query wird unverändert (pass-through) an Knowledge Retrieval weitergereicht. Der HyDE-style Rewriter produzierte keyword-dichte Queries, die überproportional Bibliographie-Sections matchten.
- **top_k: 50**: `TOP_K_MAX_VALUE=50` im Dify-Container gesetzt, DSL auf `top_k: 50`. Retrieval-Qualität signifikant verbessert (11 unique papers statt 2-3).
- **Extraction LLM → qwen2.5:14b**: `gpt-oss` halluzinierte Papers außerhalb des Korpus. `qwen2.5:14b` ist strikter grounded bei vergleichbarer Qualität.
- **Chunk Filter**: Reference-Filter mit Signal-Density (DOI, nummerierte Refs, Jahreszahlen), Doc-Deduplizierung, Safety-Net bei <3 überlebenden Chunks.
- **Final Answer Sanitizer**: Unterstützt jetzt `entity_text` Input (neben extraction/summary/knowledge/metadata_text).

### Fixed

- **Single-Author Bug**: Alle drei Extraction-LLMs nannten nur den Erstautor ("Yu Sun" statt aller 5). Gefixt durch Prompt-Optimierung (COUNT-Anweisung, Few-Shot-Example, "and colleagues"-Verbot) + Sanitizer-Enrichment aus Chunk-Metadaten.
- **Author-Halluzination**: Prompt hardened: „ONLY extract authors from \"From paper:\" headers". Keine halluzinierten Papers mehr.
- **top_k Glass Ceiling**: Dify-GUI limitierte auf 10 – via `TOP_K_MAX_VALUE` Env-Variable aufgehoben.
- **Doc-Name Suffix**: `__two_pass_1781511154` Upload-Suffixe werden zuverlässig gestrippt.

### Results (2026-07-06, qwen2.5:14b, top_k=50)

| Intent | Query | Result |
|--------|-------|--------|
| `author_lookup` | Who has worked on tRNA modifications or queuosine detection? | ✅ 5 papers, ALL authors listed (5–10 per paper), Authors:/Quote: format, no "and colleagues", 71s |
| `entity_lookup` | Which RNA modifications are most studied in epitranscriptomics? | ✅ Entity table with full paper citations (title + all authors + year), 62s |
| `knowledge_retrieval` | What is m6A and which methods are used to detect it? | ✅ 5 methods, each cited with paper title + ALL authors (2–7 per paper), no "and colleagues", 68s |

## [0.3.2] - 2026-06-29

### Added

- **KR Query Rewriter**: Neuer LLM-Node vor Knowledge Retrieval, der Such-Queries für hybrid vector+keyword Retrieval optimiert. Expandiert Akronyme, fügt technische Synonyme hinzu und konvertiert Meta-Fragen ("Who worked on X?") in Content-Queries.
- **KR Dataset Auto-Fix**: `import_dify_dsl.sh` stellt nach jedem Import automatisch das Knowledge Retrieval Dataset wieder her (aus `.secrets/kr_dataset_id.txt` oder Meta Routing Config).

### Changed

- **Parse Router Output Auto-Fallback**: Wenn `paper_list` leer ist aber der Intent `metadata_list`/`content_summary`, wird automatisch aus `conversation.memory` befüllt. Keine Abhängigkeit mehr vom `"use_memory"`-String.
- **3 KR-Routen über KR Query Rewriter**: Alle drei Knowledge Retrieval Pfade (`knowledge_retrieval`, `author_lookup`, `entity_lookup`) laufen jetzt durch den Query Rewriter für optimierte semantische Suche.

### Fixed

- **Dataset UUID**: `fiCgoIRC...` (API-Key) durch echte Dataset-UUID `5a231cec-...` ersetzt. PostgreSQL benötigt UUID-Format.
- **Final Answer Sanitizer**: Orphaned `content_text` Variable auf gelöschten Content LLM entfernt.
- **Paper Count in Parse Router Output**: `paper_count` Output fehlte – Fetch Full Paper bekam keinen Count.

## [0.3.1] - 2026-06-25

### Added

- **author_lookup & entity_lookup Intents**: Unified Router erkennt jetzt "Who has experience with X?" und "Which tRNAs/entities...?". Nutzt Knowledge Retrieval zur Inhaltssuche und Extraction LLM zur strukturierten Antwort.
- **Extraction LLM**: Neuer LLM-Node ersetzt Content LLM. Behandelt General Knowledge, Author Extraction und Entity Extraction in einem Prompt.
- **restore_kr_dataset.sh**: Script zum Wiederherstellen des Knowledge Retrieval Datasets nach Dify-Import (arbeitet um den Dify-Import-Bug herum).

### Changed

- **Final Answer Sanitizer**: Unterstützt jetzt extraction_text Input vom Extraction LLM.
- **Content LLM entfernt**: Durch Extraction LLM ersetzt (deckt alle KR-Pfade ab).

### Fixed

- Orphaned Edge auf gelöschten Content LLM entfernt (verursachte MISSING_NODE Fehler).

## [0.3.0] - 2026-06-24

### Added

- **Unified Router**: Ein LLM-Node ersetzt Query Rewriter, JSON Metadata Extractor, Parse Extractor, Paper List Resolver und Route by Intent. Klassifiziert Intent, extrahiert Paper-Constraints und schreibt Query in einem Durchlauf.
- **Intent Dispatcher**: IF/ELSE-Node routet anhand des `intent`-Felds zwischen Knowledge Retrieval, Metadata Query und Iterator.

### Changed

- **Entry Chain radikal vereinfacht**: 6 Nodes → 2 (Unified Router + Intent Dispatcher). Kein Regex mehr, keine konkurrierenden Memory-Auflösungen.
- **Parse Router Output**: Code-Node parst das LLM-JSON, behandelt `<think>`-Tags, füllt `paper_list` aus `conversation.memory` für Follow-up-Turns.
- **Content-Pfad Update Paper Memory**: Nutzt `conversation.memory` direkt statt Pipe-Parsing aus Iterator-Output.
- **Summary LLM**: `num_ctx` auf 65536 erhöht, Fetch Full Paper Text-Budget reduziert.

### Removed

- Query Rewriter, JSON Metadata Extractor, Parse Extractor Paper List, Paper List Resolver, Route by Intent, alter IF/ELSE (6 Nodes).

### Known Issue

- **Dify Import korrumpiert `dataset_ids`**: Nach YAML-Import muss das Knowledge Retrieval Dataset manuell in der Dify-UI neu zugewiesen werden. Mögliche Ursache: Reverse-Proxy-Konfiguration beschädigt große Payloads.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.4] - 2026-06-24

### Changed

- **Query Rewriter vereinfacht**: `{{#conversation.memory#}}` aus Prompt entfernt. Der Query Rewriter macht jetzt nur noch Pronomen-Auflösung ("them" → "the papers from the previous turn") ohne Paper-Identitäten zu resolven.
- **JSON Metadata Extractor fokussiert**: `{{#conversation.memory#}}` und Conversation-Window aus Prompt/Memory entfernt. Extrahiert nur noch explizite Constraints aus dem Query-Text. Prior-Turn-Referenzen werden nicht mehr im LLM aufgelöst.
- **Resolve Paper List → Paper List Resolver**: Neuer Code-Node mit klarer Priorisierung: 1) conversation.memory bei Follow-up-Intent → 2) extracted constraints → 3) Regex-Fallback → 4) empty (→ Knowledge Retrieval). Ist der einzige Ort, der `conversation.memory` auswertet.
- **Klare Trennung der Verantwortlichkeiten**: LLMs transformieren Text, Code-Nodes werten Memory aus – keine konkurrierenden Auflösungen mehr.

### Removed

- **Follow-up Memory Subset** (Code-Node `1778800001012`): Logik in Paper List Resolver integriert.

## [0.2.3] - 2026-06-24

### Changed

- **Pfade gesplittet – Converge Paths & Route LLM entfernt**: Die beiden Intent-Pfade (Metadata / Content) laufen jetzt getrennt bis zum jeweiligen LLM durch. `Converge Paths`, die beiden Assigner-Nodes und `Route LLM` entfallen. Jeder Pfad hat eigene `Update Paper Memory` und `Persist Paper Memory` Nodes. Die Routing-Entscheidung ist damit implizit in der Graph-Topologie – kein redundanter `class_id`-Check mehr nötig.
- **Graph vereinfacht**: 4 Nodes entfernt (Converge Paths, 2× Assigner, Route LLM), 2 Nodes dupliziert (Update + Persist Paper Memory) → Netto −2 Nodes, linearere Pfade.

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
