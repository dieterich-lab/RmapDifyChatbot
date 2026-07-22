# Changelog

## [0.4.11] - 2026-07-22

### Fixed

- **Author Display in metadata_list**: Metadata LLM prompt output format changed from `title, year, journal` to `title, authors, year, journal`. Each paper in `metadata_list` results now shows its full author list. Verified with "Papers by Christoph Dieterich" (HTTP 200, 102s, 2901 chars).

### Added

- **Test Cases #17–20**: Multi-author filter (#17), Lauren Saunders hardcoded info (#18), Tamer Butto name-matching bug (#19), Michaela Frye retrieval gap (#20). 2 bugs, 2 out-of-scope documented.

## [0.4.10] - 2026-07-22

### Added

- **CrossRef Metadata Fallback**: `_fetch_crossref_metadata()` in `metadata.py` – queries `api.crossref.org` for papers with DOIs not indexed in PubMed.
- **LLM Metadata Extraction**: `_extract_metadata_llm()` in `metadata.py` – BAML-based title/author extraction from PDF headers using qwen3:32b (Ollama on H100/gpu-g5-1).
- **SLURM Extraction Script**: `scripts/slurm_extract_metadata_32b.sh` – reproducible metadata extraction pipeline with local Ollama on GPU node.
- **Push Script**: `scripts/push_metadata.py` – standalone script for pushing metadata JSON dumps to Dify dataset API.
- **Metadata Report**: `docs/metadata.md` – full coverage report with pipeline description, historical trend, and per-source breakdown.

### Changed

- **DOI Extraction**: `_extract_doi_from_text()` now returns the **longest** DOI match instead of the first – eliminates truncated DOIs from PDF line breaks. Result: 5 additional papers resolved via PubMed.
- **Metadata Pipeline**: `extract_metadata()` now tries **PubMed → CrossRef → LLM → filename** in sequence, achieving 100% coverage.

### Results

| Source | Papers | % |
|--------|--------|---|
| PubMed | 73 | 87% |
| CrossRef | 1 | 1% |
| LLM (qwen3:32b) | 10 | 12% |
| **Total** | **84** | **100%** |

82/84 documents updated in production dataset. 2 PDFs (Höfer 2023 Nature, Schaffrath 2025 NAR) were never uploaded to Dify – upload gap, not metadata gap. Full metadata for all 84 papers available in `reports/metadata_dump_32b.json`.

## [0.4.9] - 2026-07-21

### Fixed

- **Author Name Format Normalization**: `"Helm, Mark"` und `"M. Helm"` routeten fälschlich als `author_lookup` (Content-Suche mit Quotes) statt `metadata_list` (API-basierte Paper-Liste). Alle drei Namensformate (`Mark Helm`, `Helm, Mark`, `M. Helm`) sowie reine Nachnamen (`Dieterich`) routen jetzt konsistent zu `metadata_list`.
- **`_author_variants()` Robustheit**: "Last, First" → "First Last" Normalisierung, Last-Word-Fallback für alle Eingaben, Last-Resort-Nachname-Check in `_matches_filters()` für abgekürzte Vornamen (`Chr. Dieterich` → matcht `Christoph Dieterich`).

### Changed

- **`parse_router_output.py`**: Name-Only-Query-Guard erkennt bare person names (Komma-Format, Punkt-Initial-Format, 1–2 großgeschriebene Wörter ohne Frage-Marker) und overrided `author_lookup`/`knowledge_retrieval` → `metadata_list`.
- **Router Prompt**: Explizite Beispiele für alle drei Namensformate (`Mark Helm`, `Helm, Mark`, `M. Helm`).

### Test Results

| # | Query | v0.4.8 | v0.4.9 |
|---|-------|--------|--------|
| – | `Mark Helm` | ✅ `metadata_list` | ✅ `metadata_list` |
| – | `Helm, Mark` | ❌ `author_lookup` | ✅ `metadata_list` |
| – | `M. Helm` | ❌ `author_lookup` | ✅ `metadata_list` |
| – | `Dieterich` | ❌ `content_summary` | ✅ `metadata_list` |
| 1 | Papers by Christoph Dieterich | ✅ | ✅ 8 papers |
| 4 | Who worked on tRNA modifications? | ✅ | ✅ Authors + Quotes |
| 12 | Who is using HEK cells? | ✅ | ✅ No speculative claims |
| 14 | Find Papers by Dieterich | ✅ | ✅ 8 papers |

## [0.4.8] - 2026-07-20

### Fixed

- **#12 HEK cells (author_lookup)**: Author Extraction prompt de-tRNA-fied. Rules 5/6 changed from "tRNA/queuosine" to "relevant to the user's query". Speculative language eliminated.
- **Science Journals AAAS metadata**: "Science Journals — AAAS" → "Post-transcriptional modifications in mitochondrial tRNA..." via dataset API metadata update.

### Test Results

| # | v0.4.7 | v0.4.8 |
|---|--------|--------|
| 12 | ⚠️ | ✅ |
| AAAS metadata | ⚠️ | ✅ |

## [0.4.7] - 2026-07-20

### Fixed

- **#3 Citation Attribution (knowledge_retrieval)**: KR Extraction LLM: "VERIFY each citation: claim MUST come from SAME chunk as header. Match each claim to the correct header carefully." Cross-reactivity claim now cites Koch/Lyko (was Chan et al.).
- **#4 Author Cross-Contamination (author_lookup)**: Author Extraction LLM: "Each paper entry gets its authors ONLY from its OWN header. Do NOT copy authors from one header into another." Biedenbander now lists correct 6 authors.
- **top_k: 100**: DSL YAML aligned with Dify GUI setting (was already 100 in GUI).

### Changed

- ⚠️ Cases reduced from 6 to 4 after #3 and #4 fixes.

### Test Results (2026-07-20)

| # | Intent | Query | v0.4.6 → v0.4.7 |
|---|--------|-------|-------------------|
| 3 | `knowledge_retrieval` | What is m6A? | ⚠️ citation error → ✅ fixed |
| 4 | `author_lookup` | Who worked on tRNA? | ⚠️ cross-contamination → ✅ fixed |

## [0.4.6] - 2026-07-20

### Fixed

- **#4 Quote-Halluzination (author_lookup)**: Author Extraction LLM Prompt gehärtet: "If no verbatim quotable sentence exists in context, write 'No verbatim quote available.' NEVER fabricate." Richter et al. sagt jetzt "No verbatim quote available." (war fabriciert).
- **#1 / #14 7-vs-8 Miscount (metadata_list)**: Metadata LLM Prompt erweitert: "COUNT items in list. Verify count matches. Double-check before output." "Papers by Dieterich" zeigt jetzt "8 papers" (war "7 out of 8").
- **#15 Group-by Pronoun (content_summary)**: Unified Router Prompt: "Group/Sort/Filter/Categorize them by X → content_summary, paper_list: 'use_memory'". "Group them by journal" routet korrekt.
- **#6 "Find papers by \<name\>" routing (metadata_list)**: Explizite Router-Regel: "Find papers by X → metadata_list, paper_list: [{'authors': 'X'}]" mit Beispiel "Find papers by Francesca Tuorto".
- **Mark Helm "Summarize them" → "\*\*"**: `paper_count` in `_fallback_result()`, `MAX_PAPERS_FOR_SUMMARY = 15`, Paper Parser 3-5 Part Format.
- **Memory-Leakage bei Broad Queries**: Auto-Fallback nur noch für `content_summary`.

### Changed

- **Regex-freies Broad-Query-Routing**: `list_mode`-Feld, LLM-native "Find all papers" / "List all researchers".
- **Infrastruktur**: Env-Variablen (`DIFY_API_KEY`, `DIFY_DATASET_ID`) in Dify App gesetzt. API-Key rotiert auf `dataset-<your-dataset-key>`.

### Known Issues

- **author_lookup Autor-Cross-Contamination** (#4): Richter-Paper hat falsche Autoren (Corzilius/Furtig aus Paper #1). Quote-Fabrikation gefixt, Autor-Extraktion noch nicht.
- **entity_lookup Recall** (#5): Nur 5 Entities, m6A fehlt. LLM-Modell-Limit (qwen2.5:14b).
- **knowledge_retrieval Citation Attribution** (#3): 1/5 Citations falsch zugeordnet.
- **content_summary Timeout** (#13): "Summarize them" für Autoren mit >15 Papers timed out (>5 Min). Fetch Full Paper Geschwindigkeit ist Flaschenhals.
- **#16 PI Collaboration**: Known limitation – no fix. Architektonischer Gap, >2h Aufwand, niedriger ROI.

### Test Results (2026-07-20, qwen2.5:14b, top_k=50, all 16 cases re-verified)

| # | Intent | Query | Result |
|---|--------|-------|--------|
| 1 | `metadata_list` | Papers by Christoph Dieterich | ✅ 8 papers (war 7) |
| 2 | `content_summary` | Summarize them | ✅ Grounded, 0 Halluzination |
| 3 | `knowledge_retrieval` | What is m6A? | ⚠️ 1/5 citation error |
| 4 | `author_lookup` | Who worked on tRNA modifications? | ⚠️ Quote fixed, author cross-contamination |
| 5 | `entity_lookup` | Which RNA modifications most studied? | ⚠️ 5 entities, m6A missing |
| 6 | `metadata_list` | Find papers by Francesca Tuorto | ✅ 6 papers (routing fix) |
| 7 | `metadata_list` | Find papers by René Ketting | ✅ 1 paper |
| 8 | `metadata_list` | Find papers by Claudia Höbartner | ✅ 1 paper |
| 9 | `metadata_list` | Find papers by Lauren Saunders | ✅ 0 + tips |
| 10 | `metadata_list` | Find all research papers | ✅ 81 papers |
| 11 | `metadata_list` | List all researchers | ✅ 776 authors |
| 12 | `author_lookup` | Who is using HEK cells? | ⚠️ cites HEK, accuracy uncertain |
| 13 | `content_summary` | Mark Helm → Summarize | ⚠️ Times out (>5 min, 28 papers) |
| 14 | `metadata_list` | Papers by Dieterich (last name) | ✅ 8 papers |
| 15 | `content_summary` | Papers by X → Group by journal | ✅ Groups by journal |
| 16 | N/A | PI Collaboration | ❌ Known limitation – no fix |

## [0.4.5] - 2026-07-15

### Fixed

- **Array-Overflow in Metadata Query**: `result`-Array auf 30 Elemente gecapped (Dify-Limit). Behebt "The length of output variable must be less than 30 elements"-Fehler bei schmalen Queries mit vielen Matches.
- **Array-Overflow in KR Chunk Filter**: `doc_names`-Array auf 30 Elemente gecapped. Behebt gleichen Fehler bei breiten `knowledge_retrieval`-Queries.
- **Broad-Query-Guard**: Wenn keine Filter (Author/Year/Journal) gesetzt sind, gibt Metadata Query eine Hilfestellung statt alle 82 Docs zu matchen.
- **Zero-Result-Help**: "Keine Dokumente gefunden" enthält jetzt konkrete Suchtipps (Namen ausschreiben, Jahr angeben).
- **Empty-Answer-Fallback**: Final Answer Sanitizer gibt jetzt "I could not generate a meaningful answer" mit Beispiel-Queries zurück, wenn alle LLM-Outputs leer sind.

### Known Issues

- **Breite KR-Queries** ("Find all research papers", "List all researchers"): Unified Router routet diese als `knowledge_retrieval` statt `metadata_list`. Der KR Extraction LLM produziert bei breitem Context leeren Output. Workaround: spezifischere Queries verwenden (z.B. "Papers by <author>").
- **Metadata-LLM-Formatierung**: "Total count: 81." (fehlendes Newline) bei `gpt-oss`-Modell. Kosmetisch, Prompt-Tuning in Dify-UI nötig.

### Results (2026-07-15, qwen2.5:14b, top_k=50, nomic)

| # | Intent | Query | Result |
|---|--------|-------|--------|
| 1 | `metadata_list` | Papers by Christoph Dieterich | **8 Papers** ✅ |
| 2 | `content_summary` | Summarize them (Turn 2) | **8/8 Papers, 0× Insufficient** ✅ |
| 3 | `knowledge_retrieval` | What is m6A and detection methods? | Methoden mit Inline-Citations ✅ |
| 4 | `author_lookup` | Who has worked on tRNA modifications? | 9 Papers mit allen Autoren + Quotes ✅ |
| 5 | `entity_lookup` | Which RNA modifications are most studied? | Entity-Tabelle mit Paper-Zuordnung ✅ |
| 6 | `metadata_list` | Find papers by Francesca Tuorto | **6 Papers** ✅ |
| 7 | `metadata_list` | Find papers by René Ketting | 1 Paper (Sonderzeichen OK) ✅ |
| 8 | `metadata_list` | Find papers by Claudia Höbartner | 1 Paper ✅ |
| 9 | `metadata_list` | Find papers by Lauren Saunders | "Kein Ergebnis" + Suchtipps ✅ |
| 10 | `knowledge_retrieval` | Find all research papers | ⚠️ Leer (known issue) |
| 11 | `knowledge_retrieval` | List all researchers | ⚠️ Leer (known issue) |
| 12 | `author_lookup` | Who is using HEK cells? | 6 Papers mit Autoren ✅ |

## [0.4.4] - 2026-07-10

### Fixed

- **Metadata Query Regression**: `main()` extrahiert jetzt Filter (`year/authors/journal/title`) aus `paper_list[0]`, wenn Einzelfelder `None` sind. Behebt "The length of output variable `result` must be less than 30 elements"-Fehler bei `metadata_list`-Queries (alle 82 Docs wurden ungefiltert returned). `"Papers by Christoph Dieterich"` liefert jetzt 8 Papers (vorher: Workflow-Error).
- **Fetch Full Paper – Segments-Fallback**: Wenn `_fetch_all_segments` mit gegebenem `doc_id` leere Segments liefert (z.B. während Re-Indexierung), fällt jetzt auf Title-Lookup zurück. Verhindert "Insufficient textual context — only metadata available" in `content_summary`.

### Changed

- **Embedding-Model**: Zurück auf `nomic-embed-text-v2-moe`. BGE-M3-Test verschoben bis App 100% stabil läuft.

### Results (2026-07-10, qwen2.5:14b, top_k=50, nomic)

| Intent | Query | Result |
|--------|-------|--------|
| `metadata_list` | Papers by Christoph Dieterich | **8 Papers** (war: Fehler) |
| `content_summary` | Summarize them (Turn 2) | **8/8 Papers mit Method/Key Finding/Implication**, 0× "Insufficient textual context" |
| `knowledge_retrieval` | What is m6A and detection methods? | ✅ Methoden mit Inline-Citations |
| `author_lookup` | Who has worked on tRNA modifications? | ✅ 9 Papers mit allen Autoren + Quotes |
| `entity_lookup` | Which RNA modifications are most studied? | ✅ 5 Entity-Typen mit Paper-Zuordnung |

## [0.4.3] - 2026-07-08

### Added

- **PubMed-Metadaten-Extraktion**: `extract_metadata_pubmed()` extrahiert Titel, Autoren (FAU), Jahr (DP), Journal (JT) via DOI→PMID→MEDLINE (NCBI E-utilities). 83% Coverage (70/84 Papers). Kein LLM nötig.
- **Bulk-Metadata-Update**: `scripts/update_dify_metadata.py` updated Dify doc_metadata in-place via Console-API (`POST /datasets/{ds}/documents/metadata`). Batch-Update mit preserved Metadata-IDs.

### Changed

- **`extract_metadata()`**: PubMed-First-Strategie. Nur bei fehlendem DOI/PubMed-Eintrag Fallback auf LLM-Extraktion.

### Results (2026-07-08)

| Intent | Query | Result |
|--------|-------|--------|
| `author_lookup` | Who has worked on tRNA modifications? | **7 Papers** (war 5), Cirzi et al. jetzt mit ALLEN 16 Autoren, keine "Tuorto, F, Cirzi C"-Garbling mehr |

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
