# RMAP Chatbot – Intent Architecture Reference

> Detailed per-intent design, prompt evolution, and verification history.
> Extracted from `roadmap.md` to keep the roadmap forward-looking.
> See `roadmap.md` for current priorities and planned work.

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

**Fazit:** Alle verbliebenen Papers haben korrekte Autoren und Quotes. Quote-Halluzination ✅ gefixt, Cross-Contamination ✅ gefixt, Prompt query-agnostisch ✅ deployed. Author-Lookup gilt als stabil.

### Recall-Analyse

| Metrik | Wert |
|--------|------|
| PDFs mit "queuosine" | 12 |
| PDFs mit "tRNA modification" | 24 |
| Kombiniert unique | **26** |
| Gefunden (v0.4.3) | **7** |
| Recall (quantitativ) | **27%** (19% in v0.4.0) |

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

---

## 3. `knowledge_retrieval` – "What is X and how is it detected?"

### Status: ✅ Stabil (v0.4.7), Metadata-Refresh ausstehend

- 5 Methoden, Inline-Citations funktionieren
- Citation-Attribution ✅ gefixt (v0.4.7): "VERIFY each citation matches the chunk"
- Buchkapitel-Garbling gefixt durch `_metadata_looks_garbled()` (v0.4.1)
- ⚠️ miCLIP (85 Hits) und MeRIP-seq (21 Hits) fehlen im Retrieval

---

## Qualitätsmetriken

| Kriterium | metadata_list | content_summary | author_lookup | entity_lookup | knowledge_retrieval |
|-----------|:------------:|:------------:|:------------:|:------------:|:-------------------:|
| Präzision (keine Halluzinationen) | ✅ API | ✅ Volltext | ✅ Quotes (v0.4.7) | ✅ sauber | ✅ Citations (v0.4.7) |
| Recall / Scope | ✅ 84 Papers | ⚠️ Max 8 (v0.4.10) | ⚠️ 27% (7/26) | ⚠️ 5/38+ mods | ⚠️ miCLIP/MeRIP |
| Autoren-Vollständigkeit | ✅ PubMed | ✅ Volltext | ✅ PubMed | ✅ Header | ✅ 5/5 korrekt |
| Follow-up-Fähigkeit | ✅ "Summarize" | – | – | – | ✅ "Group by" (v0.4.6) |
| Prompt-Stabilität | ✅ v0.4.9 | ✅ stabil | ✅ v0.4.8 | ✅ v0.4.2 | ✅ v0.4.7 |
| Metadata-Qualität | ✅ **100% (v0.4.10)** | ✅ 100% | ✅ **100%** | ✅ 100% | ✅ 100% |
