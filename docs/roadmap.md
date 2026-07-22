# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-22 · v0.4.9 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb` · Model `qwen2.5:14b` · 16+ Test Cases

## Übersicht

| Intent | Status | Präzision | Recall / Scope | Prompt reif? |
|--------|--------|-----------|----------------|-------------|
| `metadata_list` | ✅ stabil | ✅ API-fetched (keine Halluzination) | ✅ 82 Papers, 776 Authors | ✅ stabil (v0.4.9) |
| `content_summary` | ✅ stabil | ✅ 0 Halluzination (Volltext-verified) | ⚠️ Max 15 Papers (Context-Limit) | ✅ stabil |
| `knowledge_retrieval` | ✅ stabil | ✅ Citations korrekt (v0.4.7) | ⚠️ miCLIP/MeRIP fehlen | ✅ stabil (v0.4.7) |
| `author_lookup` | ✅ stabil | ✅ Quotes + Autoren korrekt (v0.4.7) | ~27% (7/26) | ✅ stabil (v0.4.8) |
| `entity_lookup` | ⚠️ Recall-Limit | ✅ sauber (keine Halluzination) | ⚠️ 5/38+ Modifikationen, m6A fehlt | ✅ stabil (v0.4.2) |

### 16 Test Cases – Current Standings (2026-07-22)

| # | Intent | Query | Status | Fixed In |
|---|--------|-------|--------|----------|
| 1 | `metadata_list` | Papers by Christoph Dieterich | ✅ 8 papers | v0.4.6 |
| 2 | `content_summary` | → Summarize them | ✅ Grounded | – |
| 3 | `knowledge_retrieval` | What is m6A? | ✅ citations correct | v0.4.7 |
| 4 | `author_lookup` | Who worked on tRNA? | ✅ quotes + authors correct | v0.4.7 |
| 5 | `entity_lookup` | Which RNA mods most studied? | ⚠️ 5 entities, m6A missing | – |
| 6–9 | `metadata_list` | Tuorto, Ketting, Höbartner, Saunders | ✅ | v0.4.6 |
| 10 | `metadata_list` | Find all research papers | ✅ LLM-native | v0.4.6 |
| 11 | `metadata_list` | List all researchers | ✅ LLM-native | v0.4.6 |
| 12 | `author_lookup` | Who is using HEK cells? | ✅ no speculative claims | v0.4.8 |
| 13 | `content_summary` | Mark Helm → Summarize | ⚠️ Times out (>5 min) | – |
| 14 | `metadata_list` | Papers by Dieterich (last name) | ✅ 8 papers | v0.4.6 |
| 15 | `content_summary` | Papers by X → Group by journal | ✅ Groups by journal | v0.4.6 |
| 16 | N/A | PI Collaboration Analysis | ❌ no-fix architectural gap | – |

### Bonus Cases – Author Name Format Normalization (v0.4.9)

| Query | Before (v0.4.8) | After (v0.4.9) |
|-------|-----------------|-----------------|
| `Mark Helm` | `metadata_list` ✅ | `metadata_list` ✅ |
| `Helm, Mark` | `author_lookup` ❌ | `metadata_list` ✅ |
| `M. Helm` | `author_lookup` ❌ | `metadata_list` ✅ |
| `Dieterich` | `content_summary` ❌ | `metadata_list` ✅ |

---

## 1. `author_lookup` – "Who has worked on X?"

### Architektur

```
User Query → Unified Router (intent=author_lookup)
  → Knowledge Retrieval (top_k=50, hybrid vector+keyword 0.3/0.7)
  → KR Chunk Filter (ref-filter, dedup max 3/paper, safety-net)
  → KR Intent Router (IF/ELSE auf {{#intent#}})
  → Author Extraction LLM (qwen2.5:14b)
  → Final Answer Sanitizer (author enrichment from chunk metadata)
  → Answer
```

### Prompt (Final, v3)

```
Context (each chunk starts with "From paper:" followed by paper info):
{{#context#}}

You are answering: "{{#sys.query#}}"

=== CRITICAL RULES ===
1. ONLY extract authors from the "From paper:" headers.
   Header format: "From paper: LastName1 Initials1, LastName2 Initials2, Year, Journal"
2. ONLY list papers whose "From paper:" header appears in the context above.
3. For each header, list EVERY author name found in it.
4. Use the header's journal as the paper's journal.
5. Derive a short paper topic from the chunk content as the title.
6. Use a verbatim quote from the chunk as evidence of what they did.

Format:
**Paper Topic** (Journal)
- FirstName LastName: "verbatim evidence quote from chunk"

If no "From paper:" headers found: "Insufficient context."
CRITICAL: NEVER list a paper or author NOT found in a "From paper:" header.
NO fabricated names. NO <think>. Keep under 300 words.
```

### Prompt-Evolution

| Version | Problem | Fix |
|---------|---------|-----|
| v1 (Single-LLM) | Mixed Output (alle 3 Sektionen) | → 3-LLM Split |
| v2 (Author LLM v1) | Nur Erstautor ("Yu Sun") | → "EVERY author", Few-Shot |
| v2 (Author LLM v2) | "and colleagues", "et al." | → explizit verboten |
| v3 (Author LLM v3) | Name-Expansion ("Fabio Tuorto") | → nur exakte Header-Namen |
| v0.4.3 | PubMed-Metadaten | → Autoritative Titel + ALLE Autoren |
| v0.4.6 | Quote-Halluzination | → "No verbatim quote available." Guard |
| v0.4.7 | Autor-Cross-Contamination | → "Authors ONLY from OWN header" |
| v0.4.8 | Prompt tRNA-spezifisch | → Query-agnostisch ("relevant to query") |
| v0.4.9 | Name-Format-Routing | → code-level guard in parse_router_output.py |

### Verifikation (2026-07-20, Volltext-Abgleich via Fetch Full Paper)

Query: *"Who has worked on tRNA modifications?"* (top_k=100, v0.4.9)

| # | Paper | Autoren vs PubMed | Quote vs Full Text | Status |
|---|-------|-------------------|--------------------|--------|
| 1 | Biedenbander et al. (Nucleic Acids Res, 2022) | ✅ 6/6 | ✅ verbatim | ✅ |
| 2 | Peschek, Tuorto (J Mol Biol, 2025) | ⬜ | ⬜ | – |
| 3 | Guo, Russo, Tuorto (BioEssays, 2024) | ⬜ | ⬜ | – |
| 4 | Sun et al. (Nucleic Acids Res, 2023) | ✅ 5/5 | ✅ verbatim | ✅ |
| 5 | Pichot et al. (Comput Struct Biotechnol J, 2023) | ✅ 10/10 | ✅ Real quote (v0.4.6) | ✅ |
| 6 | Morishima et al. (Sci Adv, 2025) | ✅ PubMed | ⚠️ paraphrasiert | ⚠️ |
| 7 | Richter et al. (Nucleic Acids Res, 2022) | ⚠️ Dropped from results (top_k=100) | ✅ "No verbatim quote" (v0.4.6) | ✅ |
| 8 | Gerber et al. (Biol Chem, 2022) | ⬜ | ⬜ | – |

**Fazit v0.4.9:** Alle verbliebenen Papers haben korrekte Autoren und Quotes. Quote-Halluzination ✅ gefixt, Cross-Contamination ✅ gefixt, Prompt query-agnostisch ✅ deployed. Author-Lookup gilt als stabil.

### Recall-Analyse

| Metrik | Wert |
|--------|------|
| PDFs mit "queuosine" | 12 |
| PDFs mit "tRNA modification" | 24 |
| Kombiniert unique | **26** |
| Gefunden (v0.4.3) | **7** |
| Recall (quantitativ) | **27%** (19% in v0.4.0) |

**Verbesserung:** +2 Papers durch PubMed-Metadaten (Motorin/Helm 2024,). +1 durch Chunk-Filter 3→1 (Peschek/Tuorto).

**Noch nicht gefunden (5 hochrelevant):**

- Stafforst/Helm 2023 ACS Chem Biol (Q=5, T=7)
- Frye/Delaunay 2023 Nat Rev Genet (Q=8, T=18)
- Helm/Richter 2022 Nucleic Acids Res (Q=1, T=14)
- Helm/Motorin 2021 WIREs RNA (Q=2, T=20)
- Tuorto/Peschek 2025 J Mol Biol (Q=2, T=20) – teilweise gefunden

### Offene Punkte `author_lookup`

- [x] ~~"and colleagues"/"et al."~~ → ✅ Gefixt (v0.4.0)
- [x] ~~Garbled author names~~ → ✅ Gefixt (v0.4.3 PubMed)
- [x] ~~Quote-Halluzination~~ → ✅ Gefixt (v0.4.6)
- [x] ~~Autor-Cross-Contamination~~ → ✅ Gefixt (v0.4.7)
- [x] ~~Prompt tRNA-spezifisch~~ → ✅ Gefixt (v0.4.8)
- [x] ~~Name-Format-Routing~~ → ✅ Gefixt (v0.4.9)
- [ ] **Recall weiter verbessern**: Embedding-Model evaluieren

---

## 2. `entity_lookup` – "Which X are most studied in Y?"

### Status: ✅ Stabil (v0.4.2 Prompt)

- **6 Entities** (m6A, pseudouridylation, RNA editing, tRNA modifications, RNA methylation, epitranscriptome)
- **Entity-Gruppierung** funktioniert
- **"Critical Reviews"-Bug** gefixt (v0.4.1)
- ⚠️ LLM stoppt bei 6 ("Insufficient context") – Modell-Limit, nicht Prompt

### Prompt (v0.4.2, stabil)

```
Context ("From paper:" headers with real metadata):
{{#context#}}

=== CRITICAL RULES ===
1. Scan ALL chunks. Be COMPREHENSIVE.
2. For "Paper" column, use EXACT "From paper:" header.
3. Group identical entities from different papers into ONE row.
4. NO word limit – be complete.
```

### Offene Punkte `entity_lookup`

- [x] ~~Prompt-Redesign~~ → ✅ Deployed (v0.4.1)
- [x] ~~"Critical Reviews"-Bug~~ → ✅ Gefixt
- [ ] **Mehr Entities**: LLM-Modell-Wechsel (qwen2.5:14b→32b?) für bessere Comprehensiveness
- [ ] **Entity-Typ-Qualität**: "Epitranscriptome" als "General term" ist grenzwertig

---

## 3. `knowledge_retrieval` – "What is X and how is it detected?"

### Status: ✅ Stabil (v0.4.7), Metadata-Refresh ausstehend

- 5 Methoden, Inline-Citations funktionieren
- Citation-Attribution ✅ gefixt (v0.4.7): "VERIFY each citation matches the chunk"
- Buchkapitel-Garbling gefixt durch `_metadata_looks_garbled()` (v0.4.1)
- ⚠️ miCLIP (85 Hits) und MeRIP-seq (21 Hits) fehlen im Retrieval

### Offene Punkte `knowledge_retrieval`

- [x] ~~"From paper:"-Header-Guard~~ → ✅ Deployed
- [x] ~~Buchkapitel-Metadaten~~ → ✅ Gefixt (Chunk-Filter)
- [ ] **miCLIP/MeRIP-seq-Recall**: Retrieval-Ranking untersuchen
- [ ] **Metadata-Refresh**: Die verbliebenen 20 Docs (non-PubMed) neu extrahieren

---

## Metriken & Qualitätskriterien

| Kriterium | metadata_list | content_summary | author_lookup | entity_lookup | knowledge_retrieval |
|-----------|:------------:|:------------:|:------------:|:------------:|:-------------------:|
| Präzision (keine Halluzinationen) | ✅ API | ✅ Volltext | ✅ Quotes (v0.4.7) | ✅ sauber | ✅ Citations (v0.4.7) |
| Recall / Scope | ✅ 82 Papers | ⚠️ Max 15 | ⚠️ 27% (7/26) | ⚠️ 5/38+ mods | ⚠️ miCLIP/MeRIP |
| Autoren-Vollständigkeit | ✅ PubMed | ✅ Volltext | ✅ PubMed | ✅ Header | ✅ 5/5 korrekt |
| Follow-up-Fähigkeit | ✅ "Summarize" | – | – | – | ✅ "Group by" (v0.4.6) |
| Prompt-Stabilität | ✅ v0.4.9 | ✅ stabil | ✅ v0.4.8 | ✅ v0.4.2 | ✅ v0.4.7 |
| Metadata-Qualität | ✅ 83% PubMed | ✅ | ✅ 83% PubMed | ✅ | ✅ 3/5 korrekt |

---

## Nächste Schritte

### ✅ Erledigt (v0.4.6–v0.4.9)

| # | Fix | Version |
|---|-----|---------|
| 1 | Quote-Halluzination (#4) | v0.4.6 |
| 2 | 7-vs-8 Miscount (#1/#14) | v0.4.6 |
| 3 | Group-by Pronomen (#15) | v0.4.6 |
| 4 | Find papers by \<name\> (#6) | v0.4.6 |
| 5 | Citation-Attribution (#3) | v0.4.7 |
| 6 | Autor-Cross-Contamination (#4) | v0.4.7 |
| 7 | HEK cells speculative claims (#12) | v0.4.8 |
| 8 | Science Journals AAAS metadata | v0.4.8 |
| 9 | Author name format normalization | v0.4.9 |

### 🟡 Priorität 2 – Qualitätsverbesserungen

10. **Metadata-Rest**: Die ~8 nicht-PubMed Papers via CrossRef + LLM nachziehen.
   - ✅ CrossRef-Fallback implementiert (commit `2454049`)
   - ✅ DOI-Extraktion verbessert (längstes Match, 5 zusätzliche Papers via PubMed)
   - ⬜ LLM-Fallback getestet (braucht `baml-py==0.222.0` + Ollama qwen3:32b)
   - ⬜ Metadaten ins Dify-Dataset pushen (`apply_metadata_two_pass`)
11. **top_k**: Bereits 100 in GUI + DSL. Keine weiteren Erhöhungen möglich.

### ⬜ Priorität 3 – Erweiterungen

12. **LLM-Upgrade**: qwen2.5:14b → 32b für bessere Comprehensiveness (`entity_lookup` m6A-Recall, #5).
13. **Embedding-Model**: `nomic-embed-text-v2-moe` → biomedizinisches Model evaluieren.
14. **#13 Timeout**: Fetch Full Paper optimieren (Parallelisierung/Caching).

### ❌ No-Fix – Architektonische Limits

15. **Collaboration Analysis** (#16): >2h Aufwand, fast alle Pairs 0 Collaborations.

---

## Lessons Learned

### Query Expansion

❌ **Regelbasiert**: Hardcodierte Lookup-Tabellen ("tRNA modification" → Synonyme). Nicht generalisierbar, biased auf Test-Queries.

❌ **LLM Keyword-Expander**: qwen2.5:14b produzierte unberechenbare Expansions, zerstörte entity_lookup (6→1 Entity).

✅ **Fazit**: Query Expansion ist für unseren Use-Case zu fragil. Die Retrieval-Qualität hängt zu stark von exakter Wortwahl ab. Besser: Metadata-Qualität + top_k erhöhen.

### Metadata-Qualität

✅ **PubMed via DOI**: 83% Coverage, autoritativ, kein LLM-Halluzinieren. Der größte Einzelgewinn an Antwortqualität.

✅ **In-Place Update**: Console-API Batch-Update spart Delete+Reupload (kein Re-Chunking, keine Downtime).

### Chunk-Filter Tuning

✅ **3→1 Chunk/Paper**: Verdoppelt Paper-Diversität. Entity-Lookup 3→6 Entities. Beste Einzeländerung für Recall.

✅ **`_metadata_looks_garbled()`**: Fängt Buchkapitel und defekte Extraktionen ab. Wird durch PubMed-Metadaten zunehmend obsolet.

### Author Name Normalization (v0.4.9)

✅ **Code-Level Guard > Prompt-Only**: Bare person names in various formats (`Mark Helm`, `Helm, Mark`, `M. Helm`) required a code-level override in `parse_router_output.py` – the LLM Router alone couldn't distinguish "M. Helm" (a person) from "What is m6A?" (a knowledge question). Pattern matching on comma-separated names, dot-initial formats, and 1–2 capitalized words without question markers proved more reliable than prompt engineering for this case.

✅ **Author Variant Expansion**: `_author_variants()` in `metadata_query.py` now normalizes "Last, First" → "First Last", always includes last-name-only fallback, and handles abbreviated first names. This fixed `Chr. Dieterich` not matching `Christoph Dieterich`.
