# RMAP Chatbot – Lessons Learned

> Institutional knowledge from v0.4.0–v0.4.14. What worked, what failed, and why.

---

## Query Expansion

❌ **Regelbasiert**: Hardcodierte Lookup-Tabellen ("tRNA modification" → Synonyme). Nicht generalisierbar, biased auf Test-Queries.

❌ **LLM Keyword-Expander**: qwen2.5:14b produzierte unberechenbare Expansions, zerstörte entity_lookup (6→1 Entity).

✅ **Fazit**: Query Expansion ist für unseren Use-Case zu fragil. Die Retrieval-Qualität hängt zu stark von exakter Wortwahl ab. Besser: Metadata-Qualität + top_k erhöhen.

---

## Metadata-Qualität

✅ **PubMed via DOI**: 83% Coverage, autoritativ, kein LLM-Halluzinieren. Der größte Einzelgewinn an Antwortqualität.

✅ **In-Place Update**: Console-API Batch-Update spart Delete+Reupload (kein Re-Chunking, keine Downtime).

---

## Chunk-Filter Tuning

✅ **3→1 Chunk/Paper**: Verdoppelt Paper-Diversität. Entity-Lookup 3→6 Entities. Beste Einzeländerung für Recall.

✅ **`_metadata_looks_garbled()`**: Fängt Buchkapitel und defekte Extraktionen ab. Wird durch PubMed-Metadaten zunehmend obsolet.

---

## Author Name Normalization (v0.4.9)

✅ **Code-Level Guard > Prompt-Only**: Bare person names in various formats (`Mark Helm`, `Helm, Mark`, `M. Helm`) required a code-level override in `parse_router_output.py` – the LLM Router alone couldn't distinguish "M. Helm" (a person) from "What is m6A?" (a knowledge question). Pattern matching on comma-separated names, dot-initial formats, and 1–2 capitalized words without question markers proved more reliable than prompt engineering for this case.

✅ **Author Variant Expansion**: `_author_variants()` in `metadata_query.py` now normalizes "Last, First" → "First Last", always includes last-name-only fallback, and handles abbreviated first names. This fixed `Chr. Dieterich` not matching `Christoph Dieterich`.

---

## LLM Bypass for Deterministic Formatting (v0.4.14)

✅ **When the LLM can't follow instructions, bypass it.** For multi-author OR queries, qwen2.5:14b consistently interpreted comma-separated authors as AND logic — ignoring CRITICAL, PASSTHROUGH, VERBATIM, and explicit example instructions. Solution: `paper_count=0` routes through the Metadata LLM Bypass directly to Final Answer Sanitizer, which passes pre-formatted `result_text` from `metadata_query.py` through verbatim.

✅ **Pre-formatted output as defense-in-depth.** Rather than hoping the LLM passes through correctly, `metadata_query.py` produces complete Markdown-formatted output. The Final Answer Sanitizer's fallback logic picks this up when LLM outputs are empty.

✅ **Pattern: code-level guard → workflow bypass → pre-formatted output.** This three-layer pattern proved reliable where prompt engineering alone failed repeatedly.

---

## Embedding Model Evaluation (v0.4.14)

✅ **Test before switching, not after.** A full regression test across all 5 intents with the candidate model (bge-m3) revealed that retrieval quality was equivalent but latency was 48% worse. Without the test, we would have switched blindly.

✅ **metadata_list as control group.** Queries using the Dataset API are unaffected by embedding changes — natural A/B baseline.

✅ **Document the negative result.** `docs/embeddings.md` serves as a reference for defending the model choice. A documented negative result prevents redundant re-evaluation.
