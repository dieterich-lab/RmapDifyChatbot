# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-08 · v0.4.3 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb` · Model `qwen2.5:14b`

## Übersicht

| Intent | Status | Präzision | Recall | Prompt reif? |
|--------|--------|-----------|--------|-------------|
| `author_lookup` | ✅ fertig | 100% (7/7 korrekt) | ~27% (7/26) | ✅ stabil |
| `entity_lookup` | ✅ fertig | ⚠️ sauber, aber nur 6 Entities | ⚠️ ~6/38+ mods | ✅ stabil (v0.4.2 Prompt) |
| `knowledge_retrieval` | ⚠️ braucht Metadata-Refresh | ⚠️ 4/5 Citations sauber | ⚠️ miCLIP/MeRIP fehlen | ⚠️ akzeptabel |

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

### Verifikation (2026-07-07, grep gegen Original-PDFs)

Query: *"Who has worked on tRNA modifications or queuosine detection?"*

| # | Paper | Autoren (PDF) | Quote (PDF) | Status |
|---|-------|---------------|-------------|--------|
| 1 | Detection of queuosine… (Nucleic Acids Res, 2023) | 5/5 ✅ | ✅ | `Ehrenhofer-Murray AE, Sun Y, 2023` |
| 2 | Functional integration… (Nucleic Acids Res, 2022) | 10/10 ✅ | ✅ | `Helm M, Bessler L, 2022` |
| 3 | Queuosine‐tRNA promotes… (EMBO J, 2023) | 16/16 ✅ | ✅ | `Tuorto, F, Cirzi C, 2023` |
| 4 | Spectral libraries… (Rapid Comm Mass Spectrom, 2024) | 6/6 ✅ | ✅ | `Sabido E, Espadas G, 2024` |
| 5 | Lost in translation… (BioEssays, 2024) | 3/3 ✅ | ✅ | `Tuorto F, Guo W, 2024` |
| 6 | General Principles… (Acc Chem Res, 2024) | 2/2 ✅ | ✅ | `Helm M, Motorin Y, 2024` (neu in v0.4.3) |
| 7 | Interplay Between tRNA Mods… (J Mol Biol, 2025) | 2/2 ✅ | ✅ | `Tuorto F, Peschek J, 2025` (neu in v0.4.2) |

**Fazit:** 100% Präzision – alle Autor:innen-Nennungen und Zitate in den PDFs belegt. v0.4.3: 5→7 Papers dank PubMed-Metadaten.

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

| Kriterium | author_lookup | entity_lookup | knowledge_retrieval |
|-----------|:------------:|:------------:|:-------------------:|
| Präzision (keine Halluzinationen) | ✅ 100% | ✅ sauber | ✅ 100% |
| Recall (Vollständigkeit) | ⚠️ 27% (7/26) | ⚠️ 6 Entities | ⚠️ miCLIP/MeRIP fehlen |
| Autoren-Vollständigkeit | ✅ ALLE (PubMed!) | ✅ aus Headern | ✅ 4/5 korrekt |
| "and colleagues"-Frei | ✅ | ✅ | ✅ |
| Quote-Verifikation (PDF) | ✅ 7/7 | – | ⚠️ 3/5 sauber |
| Prompt-Stabilität | ✅ v3 final | ✅ v0.4.2 | ⚠️ akzeptabel |
| Metadata-Qualität | ✅ 83% PubMed | ✅ | ⚠️ 2/5 Filename-Fallback |

---

## Nächste Schritte

1. **Metadata-Rest**: Die 14 nicht-PubMed Papers manuell oder via LLM nachziehen
2. **knowledge_retrieval** mit sauberen Metadaten neu testen
3. **top_k-Erhöhung**: Dify `TOP_K_MAX_VALUE` auf 100 setzen (größter Recall-Hebel)
4. **Embedding-Model**: `nomic-embed-text-v2-moe` → biomedizinisches Model evaluieren
5. **LLM-Upgrade**: qwen2.5:14b → 32b für bessere Comprehensiveness (entity_lookup)

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
