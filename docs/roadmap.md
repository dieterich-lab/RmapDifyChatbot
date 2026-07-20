# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-20 · v0.4.6 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb` · Model `qwen2.5:14b` · 16 Test Cases

## Übersicht

| Intent | Status | Präzision | Recall / Scope | Prompt reif? |
|--------|--------|-----------|----------------|-------------|
| `metadata_list` | ✅ stabil | ✅ API-fetched (keine Halluzination) | ✅ 82 Papers, 776 Authors | ✅ stabil (v0.4.6) |
| `content_summary` | ✅ stabil | ✅ 0 Halluzination (Volltext-verified) | ⚠️ Max 15 Papers (Context-Limit) | ✅ stabil |
| `knowledge_retrieval` | ⚠️ akzeptabel | ⚠️ 4/5 Citations korrekt | ⚠️ miCLIP/MeRIP fehlen | ⚠️ akzeptabel |
| `author_lookup` | ⚠️ Quote-Bug | ❌ 6/8 Quotes korrekt, 2/8 hallucinated | ~27% (7/26) | ⚠️ braucht Prompt-Hardening |
| `entity_lookup` | ⚠️ Recall-Limit | ✅ sauber (keine Halluzination) | ⚠️ 5/38+ Modifikationen, m6A fehlt | ✅ stabil (v0.4.2) |

### 16 Test Cases – Current Standings (2026-07-20)

| # | Intent | Query | Status |
|---|--------|-------|--------|
| 1 | `metadata_list` | Papers by Christoph Dieterich | ⚠️ "7 of 8" miscount |
| 2 | `content_summary` | → Summarize them | ✅ Grounded |
| 3 | `knowledge_retrieval` | What is m6A? | ⚠️ 1 citation swap |
| 4 | `author_lookup` | Who worked on tRNA? | ❌ 2/8 quotes hallucinated |
| 5 | `entity_lookup` | Which RNA mods most studied? | ⚠️ 5 entities, m6A missing |
| 6–9 | `metadata_list` | Tuorto, Ketting, Höbartner, Saunders | ✅ |
| 10 | `metadata_list` | Find all research papers | ✅ LLM-native |
| 11 | `metadata_list` | List all researchers | ✅ LLM-native |
| 12 | `author_lookup` | Who is using HEK cells? | ⚠️ context drift |
| 13 | `content_summary` | Mark Helm → Summarize | ✅ Fixed (v0.4.6) |
| 14 | `metadata_list` | Papers by Dieterich (last name) | ⚠️ same #1 miscount |
| 15 | `content_summary` | Papers by X → Group by journal | ❌ lists ALL 81 |
| 16 | `knowledge_retrieval` | PI Collaboration Analysis | ❌ beyond architecture |

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
| v3 (v0.4.3) | PubMed-Metadaten | → Autoritative Titel + ALLE Autoren |

### Verifikation (2026-07-16, Volltext-Abgleich via Fetch Full Paper)

Query: *"Who has worked on tRNA modifications?"*

| # | Paper | Autoren vs PubMed | Quote vs Full Text | Status |
|---|-------|-------------------|--------------------|--------|
| 1 | Biedenbander et al. (Nucleic Acids Res, 2022) | ✅ 6/6 | ✅ verbatim | – |
| 2 | Peschek, Tuorto (J Mol Biol, 2025) | ⬜ | ⬜ | – |
| 3 | Guo, Russo, Tuorto (BioEssays, 2024) | ⬜ | ⬜ | – |
| 4 | Sun et al. (Nucleic Acids Res, 2023) | ✅ 5/5 | ✅ verbatim | – |
| 5 | Pichot et al. (Comput Struct Biotechnol J, 2023) | ✅ 10/10 | ❌ **Fabricated!** | 🔴 Priorität 1 |
| 6 | Morishima et al. (Sci Adv, 2025) | ✅ PubMed | ⚠️ paraphrasiert | – |
| 7 | Richter et al. (Nucleic Acids Res, 2022) | ❌ Falsche Autoren | ❌ **Fabricated!** | 🔴 Priorität 1 |
| 8 | Gerber et al. (Biol Chem, 2022) | ⬜ | ⬜ | – |

**Fazit v0.4.6:** 6/8 Paper korrekt, aber 2/8 mit fabricateten Quotes – **keine 100% Präzision** wie zuvor angenommen. Prompt-Hardening nötig.

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
- [x] ~~Garbled author names ("Tuorto, F, Cirzi C")~~ → ✅ Gefixt (v0.4.3 PubMed)
- [ ] **🔴 Quote-Halluzination beheben**: 2/8 Papers (Pichot, Richter) haben fabricatete Quotes. Prompt-Hardening: "If no verbatim quotable sentence found → write 'No verbatim quote available.' NEVER fabricate." (~15 Min Fix)
- [ ] **Recall weiter verbessern**: top_k erhöhen (Dify-Limit), besseres Embedding-Model

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

### Status: ⚠️ Akzeptabel, Metadata-Refresh ausstehend

- 5 Methoden, Inline-Citations funktionieren
- "From paper:"-Header-Guard deployed (v0.4.1)
- Buchkapitel-Garbling gefixt durch `_metadata_looks_garbled()` (v0.4.1)
- ⚠️ 2/5 Citations nutzen noch Filename-Fallback (Metadata-Qualität)
- ⚠️ miCLIP (85 Hits) und MeRIP-seq (21 Hits) fehlen

### Offene Punkte `knowledge_retrieval`

- [x] ~~"From paper:"-Header-Guard~~ → ✅ Deployed
- [x] ~~Buchkapitel-Metadaten~~ → ✅ Gefixt (Chunk-Filter)
- [ ] **miCLIP/MeRIP-seq-Recall**: Retrieval-Ranking untersuchen
- [ ] **Metadata-Refresh**: Die verbliebenen 20 Docs (non-PubMed) neu extrahieren

---

## Metriken & Qualitätskriterien

| Kriterium | metadata_list | content_summary | author_lookup | entity_lookup | knowledge_retrieval |
|-----------|:------------:|:------------:|:------------:|:------------:|:-------------------:|
| Präzision (keine Halluzinationen) | ✅ API | ✅ Volltext | ❌ 6/8 Quotes | ✅ sauber | ⚠️ 4/5 Citations |
| Recall / Scope | ✅ 82 Papers | ⚠️ Max 15 | ⚠️ 27% (7/26) | ⚠️ 5/38+ mods | ⚠️ miCLIP/MeRIP |
| Autoren-Vollständigkeit | ✅ PubMed | ✅ Volltext | ✅ PubMed | ✅ Header | ✅ 4/5 korrekt |
| Follow-up-Fähigkeit | ✅ "Summarize" | – | – | – | ❌ "Group by" |
| Prompt-Stabilität | ✅ v0.4.6 | ✅ stabil | ⚠️ braucht Fix | ✅ v0.4.2 | ⚠️ akzeptabel |
| Metadata-Qualität | ✅ 83% PubMed | ✅ | ✅ 83% PubMed | ✅ | ⚠️ 2/5 Fallback |

---

## Nächste Schritte

### 🔴 Priorität 1 – Prompt-Fixes (~30 Min) ✅ Erledigt in v0.4.6

| # | Fix | Betroffener Intent | Status |
|---|-----|-------------------|--------|
| 1 | **Quote-Halluzination** (#4): "If no verbatim quotable sentence found, write 'No verbatim quote available.' NEVER fabricate." | `author_lookup` | ✅ Verified |
| 2 | **Group-by Pronomen** (#15): "Group/Sort/Filter them by X → content_summary, paper_list: 'use_memory'" | `content_summary` | ✅ Verified |
| 3 | **7-vs-8 Miscount** (#1/#14): "Count the items you listed – verify count matches." | `metadata_list` | ✅ Verified |
| 4 | **Find papers by \<name\>** (#6): "Find papers by X → metadata_list, paper_list: [{'authors': 'X'}]" | `metadata_list` | ✅ Verified |

### 🟡 Priorität 2 – Qualitätsverbesserungen

5. **Citation-Attribution** (#3): KR Extraction LLM: Verhindern, dass Zitate aus benachbarten Chunks vermischt werden.
6. **Metadata-Rest**: Die 14 nicht-PubMed Papers manuell oder via LLM nachziehen.
7. **top_k-Erhöhung**: Dify `TOP_K_MAX_VALUE` auf 100 setzen (größter Recall-Hebel).

### ⬜ Priorität 3 – Erweiterungen (nächster Sprint)

8. **LLM-Upgrade**: qwen2.5:14b → 32b für bessere Comprehensiveness (`entity_lookup` m6A-Recall).
9. **Embedding-Model**: `nomic-embed-text-v2-moe` → biomedizinisches Model evaluieren.

### ❌ No-Fix – Architektonische Limits

10. **Collaboration Analysis** (#16): Neuer Intent für Multi-Author-Co-Autorenschaft-Analyse. Nicht im Scope – >2h Aufwand, fast alle Pairs hätten 0 Collaborations bei nur 1 Paper/Author.

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
