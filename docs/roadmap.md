# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-07 · v0.4.0 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb` · Model `qwen2.5:14b`

## Übersicht

| Intent | Status | Präzision | Recall | Prompt reif? |
|--------|--------|-----------|--------|-------------|
| `author_lookup` | ✅ analysiert & verifiziert | 100% (5/5 korrekt) | ~19% (5/26) | ✅ stabil |
| `entity_lookup` | 🔬 analysiert | ⚠️ 1/4 Paper korrekt | ⚠️ ~4/38+ mods | ❌ braucht Redesign |
| `knowledge_retrieval` | 🔬 analysiert | ⚠️ 4/5 Citations sauber | ⚠️ miCLIP/MeRIP fehlen | ⚠️ braucht Header-Only-Guard |

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

### Verifikation (2026-07-07, grep gegen Original-PDFs)

Query: *"Who has worked on tRNA modifications or queuosine detection?"*

| # | Paper | Autoren (PDF) | Quote (PDF) | Status |
|---|-------|---------------|-------------|--------|
| 1 | Detection of queuosine… (Nucleic Acids Res, 2023) | 5/5 ✅ | ✅ | `Ehrenhofer-Murray AE, Sun Y, 2023` |
| 2 | Functional integration… (Nucleic Acids Res, 2022) | 10/10 ✅ | ✅ | `Helm M, Bessler L, 2022` |
| 3 | Queuosine‐tRNA promotes… (EMBO J, 2023) | 16/16 ✅ | ✅ | `Tuorto, F, Cirzi C, 2023` |
| 4 | Spectral libraries… (Rapid Comm Mass Spectrom, 2024) | 6/6 ✅ | ✅ | `Sabido E, Espadas G, 2024` |
| 5 | Lost in translation… (BioEssays, 2024) | 3/3 ✅ | ✅ | `Tuorto F, Guo W, 2024` |

**Fazit:** 100% Präzision – alle 40 Autor:innen-Nennungen und alle 5 Zitate in den PDFs belegt. Keine Halluzinationen.

### Recall-Analyse

| Metrik | Wert |
|--------|------|
| PDFs mit "queuosine" | 12 |
| PDFs mit "tRNA modification" | 24 |
| Kombiniert unique | **26** |
| Gefunden | **5** |
| Recall (quantitativ) | **19%** |

**Warum nur 19%?**

1. **top_k=50 + Chunk-Filter-Dedup** → max ~15 Papers im Context (3 Chunks/Paper)
2. **keyword_weight=0.7** begünstigt exakte Matches ("queuosine detection") über konzeptuelle ("tRNA modifications" als Feld)
3. **Query-Semantik**: "queuosine detection" ist spezifischer als "tRNA modifications" → Retrieval rankt queuosine-Papers höher

**Hoch relevant, nicht gefunden (6 Papers):**

- Tuorto/Peschek 2025 J Mol Biol (Q=2, T=20) – tRNA-Modifikationen
- Helm/Motorin 2021 WIREs RNA (Q=2, T=20) – tRNA-Review
- Stafforst/Helm 2023 ACS Chem Biol (Q=5, T=7)
- Frye/Delaunay 2023 Nat Rev Genet (Q=8, T=18)
- Helm/Richter 2022 Nucleic Acids Res (Q=1, T=14)
- Helm/Motorin 2024 Acc Chem Res (Q=2, T=2)

**Fazit:** Die 5 gefundenen Papers sind die präzisesten (Top-4 nach Queuosine-Hits). Recall-Probleme sind architekturbedingt (Retrieval-Limit), nicht prompt-bedingt.

### Offene Punkte `author_lookup`

- [ ] **Recall verbessern**: Query-Expansion für breite Suchbegriffe ("tRNA modification" → auch "tRNA maturation", "tRNA processing", "tRNA modification enzyme")
- [ ] **top_k-Tuning**: 50→100 testen (Dify-Limit? Ollama-Context-Limit?)
- [ ] **Chunk-Filter-Dedup**: Max 3 Chunks/Paper vs. mehr Papers mit weniger Chunks
- [ ] **"Insufficient context"**: Fallback-Logik für leere Ergebnisse

---

## 2. `entity_lookup` – "Which X are most studied in Y?"

### Architektur

```
User Query → Unified Router (intent=entity_lookup)
  → Knowledge Retrieval (top_k=50)
  → KR Chunk Filter
  → KR Intent Router → Entity Extraction LLM
  → Final Answer Sanitizer
  → Answer
```

### Prompt (Current – problematisch)

```
Context (each chunk starts with "From paper:" followed by paper info):
{{#context#}}

You are answering: "{{#sys.query#}}"

Scan ALL chunks and extract every named entity you can FIND IN THE CONTEXT:
RNA modifications, methods, organisms, cell lines, proteins, tools.

ONLY list entities that actually appear in the context.
Format as a table:
| Entity | Type | Paper |
|--------|------|-------|

If context lacks entities: "Insufficient context."

CRITICAL: NEVER fabricate entities. NO <think>. Keep under 300 words.
```

### Aktuelles Testergebnis (2026-07-07)

Query: *"Which RNA modifications are most studied in epitranscriptomics?"*

| Entity | Type | Paper |
|--------|------|-------|
| N6-methyladenosine (m6A) | RNA modification | "Helm M, Fischer TR, 2022" by **Critical Reviews**, Tim R. Fischer, ... |
| 2′-O-methylation (Nm) | RNA modification | Machine learning... Nm... (Pichot et al., 2022) ✅ |
| pseudouridylation | RNA modification | Pseudouridylation of EBER2... (Henry et al., 2022) ✅ |
| tRNA and rRNA | **RNA targets** ❌ | RNA nucleotide methylation... (Motorin, Helm, 2021) ✅ |
| *(Abbruch)* | | *"Insufficient context to list more specific entities"* |

### Gefundene Probleme

#### 🔴 P1: "Insufficient context"-Behauptung ist falsch

Der Korpus enthält **38+ Papers mit RNA-Modifikationen**. Top-Paper haben >500 m6A-Hits. Es gibt massiv Context – das LLM gibt zu früh auf.

**Ursache:** `"Keep under 300 words"` + `"If context lacks entities"` als Escape-Hatch.

#### 🔴 P2: Paper-Citation-Qualität – "Critical Reviews"-Bug

Das Paper "Chemical biology and medicinal chemistry of RNA methyltransferases" (Fischer/Helm 2022) erscheint als `"Helm M, Fischer TR, 2022" by Critical Reviews, ...`.

**Ursache:** Der Journal-Section-Header **"Critical Reviews and Perspectives"** wird vom LLM als Autor geparst. Der Prompt sagt nicht, dass die Paper-Spalte aus dem `"From paper:"`-Header stammen muss (anders als `author_lookup`).

#### 🔴 P3: Nur 4 Entities bei 38+ relevanten Papers

| Modifikation | Papers im Korpus | In Antwort? |
|---|---|---|
| m6A | 38 (Top: 507 hits) | ✅ |
| pseudouridine/Ψ | 26 (Top: 197) | ✅ |
| 2'-O-Me/Nm | ~12 | ✅ |
| m7G | 22 (Top: 41) | ❌ |
| m5C | ~15 | ❌ |
| ac4C | 8 | ❌ |
| queuosine/Q | 12 | ❌ |
| m1A | mehrere | ❌ |
| m6Am | mehrere | ❌ |
| hm5C | mehrere | ❌ |
| inosine/A-to-I | mehrere | ❌ |

#### 🟡 P4: Entity-Typen inkonsistent

| Prompt definiert | LLM antwortet |
|---|---|
| RNA modifications | ✅ genutzt |
| methods | ❌ fehlt |
| organisms | ❌ fehlt |
| cell lines | ❌ fehlt |
| proteins | ❌ fehlt |
| tools | ❌ fehlt |
| *(nicht definiert)* | ❌ "RNA targets" (tRNA/rRNA sind keine Modifikationen!) |

#### 🟡 P5: Paper-Deduplizierung fehlt

Motorin/Helm 2021 erscheint mehrfach für verschiedene Entities, aber ohne Gruppierung.

### Empfohlener Prompt (Redesign)

```
Context (each chunk starts with "From paper:" followed by paper info):
{{#context#}}

You are answering: "{{#sys.query#}}"

=== CRITICAL RULES ===
1. Scan ALL chunks and extract EVERY entity that matches the query.
2. Be COMPREHENSIVE – list ALL matching entities, not just the first few.
3. For the "Paper" column, use the EXACT "From paper:" header text.
   The header already contains paper title and all authors.
4. Derive the Entity Type from the chunk content.
5. Group identical entities from different papers into ONE row.
   List all papers for that entity, separated by ";".

Format:
| Entity | Type | Papers (from "From paper:" headers) |
|--------|------|--------------------------------------|

If NO relevant entities found: "Insufficient context."
CRITICAL: NEVER fabricate entities. NO <think>. NO word limit – be complete.
```

### Kernel-Änderungen zum Current Prompt

| Aspekt | Current | Proposed |
|--------|---------|----------|
| Vollständigkeit | "Keep under 300 words" | "NO word limit – be complete" |
| Paper-Format | nicht spezifiziert | "EXACT 'From paper:' header" |
| Entity-Typen | hardcoded (methods, organisms, ...) | LLM leitet aus Content ab |
| Deduplizierung | keine | "Group identical entities" |
| Escape-Hatch | "If context lacks entities" | "If NO relevant entities found" |
| Entity-Fokus | "every named entity" (zu breit) | "entities that match the query" |

### Offene Punkte `entity_lookup`

- [ ] Prompt-Redesign deployen & testen
- [ ] Recall gegen Korpus-Landschaft validieren (m7G, m5C, ac4C, etc.)
- [ ] Paper-Zuordnungen via PDF-Grep verifizieren
- [ ] Entity-Typ-Qualität prüfen (keine "RNA targets" o.ä.)

---

## 3. `knowledge_retrieval` – "What is X and how is it detected?"

### Architektur

```
User Query → Unified Router (intent=knowledge_retrieval)
  → Knowledge Retrieval (top_k=50)
  → KR Chunk Filter
  → KR Intent Router → KR Extraction LLM
  → Final Answer Sanitizer
  → Answer
```

### Prompt (Current – überwiegend gut)

```
Answer as a concise knowledge summary. For EVERY finding or method you
mention, you MUST cite the source paper in this format:

"Paper Title" by ALL authors from the header (Journal, Year)

NEVER say "and colleagues" or "et al." — list EVERY author from the "From
paper:" header exactly as written. Copy the title exactly.

If context lacks information: "Insufficient context."
CRITICAL: NEVER fabricate. NO <think>. Keep under 500 words.
Answer in the same language as the user.
```

### Testergebnis (2026-07-07)

Query: *"What is m6A and which methods are used to detect it?"*

→ 5 Methoden, 68s, 4/5 Citations sauber, 1 verstümmelt.

### Gefundene Probleme

#### 🔴 P1: Paper 5 – Buchkapitel-Citation verstümmelt (gleicher Bug wie entity_lookup)

Das Paper `Naarmann-de Vries IS, Lemsara A, 2023` ist Kapitel 16 in "Computational Epigenomics and Epitranscriptomics" (Methods in Molecular Biology 2624, ed. Pedro H. Oliveira).

| Bot-Antwort | Tatsächlich (PDF) |
|-------------|-------------------|
| `"ComputationalEpigenomicsandEpitranscriptomics"` | Buchtitel (nicht Kapiteltitel!) |
| `Pedro H. Oliveira Editor` | **Editor**, kein Autor |
| `Ethods In` | "Methods in" → zerstückelt |
| `Olecular B. Iology` | "Molecular Biology" → zerstückelt |
| `Series Editor` | Kein Autor |
| `John M. Walker` | Series Editor, kein Autor |

**Root Cause:** Gleicher Bug-Typ wie "Critical Reviews" bei entity_lookup. Das LLM greift strukturellen Text (Editor, Series-Info) aus dem Chunk-Body als Autorennamen, statt NUR den `"From paper:"`-Header zu nutzen. Bei Buchkapiteln ist der Header weniger standardisiert als bei Journal-Artikeln.

#### 🟡 P2: miCLIP (85 Hits) und MeRIP-seq (21 Hits) fehlen

| Methode | Korpus-Hits | In Antwort? |
|---------|-------------|-------------|
| Direct RNA Sequencing | – | ✅ |
| Antibody-Based (DIP-seq) | – | ✅ |
| NO-Seq | 5 | ✅ |
| GLORI | 95 | ✅ |
| eTAM-seq | 2 | ✅ |
| m6A-SAC-seq | 2 | ✅ |
| MePMe-seq | 6 | ✅ |
| **miCLIP** | **85** | ❌ |
| **MeRIP-seq** | **21** | ❌ |
| DART-seq | 4 | ❌ |

miCLIP ist die Referenzmethode für Einzelnukleotid-Auflösung – ein signifikantes Loch.

#### 🟢 Positive Aspekte

- m6A-Definition präzise und korrekt
- 4/5 Paper-Citations: ALLE Autoren, keine "and colleagues"
- Keine halluzinierten Methoden
- Struktur (Definition + nummerierte Liste) sauber

### Empfohlene Prompt-Änderung

Nur eine gezielte Ergänzung nötig (analog zu entity_lookup-Fix):

```
"Paper Title" by ALL authors from the header (Journal, Year)
→ CRITICAL: Use ONLY the "From paper:" header for the citation.
  NEVER extract author names or paper titles from the chunk body text.
  Copy the header exactly, character for character.
```

### Offene Punkte `knowledge_retrieval`

- [ ] "From paper:"-Header-Only-Guard in Prompt einbauen
- [ ] Buchkapitel-Metadaten im Chunk-Filter verbessern (Titel = Kapiteltitel, nicht Buchtitel)
- [ ] miCLIP/MeRIP-seq-Recall untersuchen (warum nicht gerankt?)
- [ ] Methodenbeschreibungen auf Spezifität prüfen (NO-Seq = NaIO4-Oxidation?)

---

## Metriken & Qualitätskriterien

| Kriterium | author_lookup | entity_lookup | knowledge_retrieval |
|-----------|:------------:|:------------:|:-------------------:|
| Präzision (keine Halluzinationen) | ✅ 100% | ⚠️ "Critical Reviews"-Bug | ✅ 100% (keine erfundenen Fakten) |
| Recall (Vollständigkeit) | ⚠️ 19% | ⚠️ ~4/38+ mods | ⚠️ miCLIP/MeRIP-seq fehlen |
| Autoren-Vollständigkeit | ✅ ALLE | ⚠️ Editor als Autor | ✅ 4/5 korrekt |
| "and colleagues"-Frei | ✅ | ✅ | ✅ |
| Quote-Verifikation (PDF) | ✅ 5/5 | – | ⚠️ 4/5 sauber, 1 Buchkapitel verstümmelt |
| Prompt-Stabilität | ✅ v3 final | ❌ braucht Redesign | ⚠️ Header-Only-Guard fehlt |
| Cross-Cutting Bug | – | 🔴 "Critical Reviews" | 🔴 "Series Editor" (gleiche Klasse) |

---

## Nächste Schritte

1. **`entity_lookup`** analysieren (Recall, Entity-Typen, Paper-Zuordnung, Prompt)
2. **`knowledge_retrieval`** analysieren (Faktentreue, Zitate, Vollständigkeit)
3. **Recall-Architektur** für `author_lookup` verbessern (Query-Expansion, top_k-Tuning)
4. **Regression-Tests** für alle 3 Intents nach Prompt-Änderungen
