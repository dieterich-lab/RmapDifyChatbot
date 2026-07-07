# v0.4.0 – 3-LLM Intent Architecture

## 🏗️ 3-LLM Intent Routing

Der einzelne Extraction LLM wurde durch drei dedizierte, intent-geroutete LLMs ersetzt. Jeder Prompt ist single-purpose – kein Mixed Output mehr.

```
Chunk Filter → KR Intent Router (IF/ELSE on {{#intent#}})
    ├─ author_lookup       → Author Extraction LLM   ─┐
    ├─ entity_lookup       → Entity Extraction LLM   ─┤→ Final Answer Sanitizer → Answer
    └─ knowledge_retrieval → KR Extraction LLM       ─┘
```

## 🔧 Changes

- **3-LLM Architecture**: `Author Extraction LLM`, `Entity Extraction LLM`, `KR Extraction LLM` ersetzen den einzelnen Multi-Intent Extraction LLM. Routing via neuen `KR Intent Router` (IF/ELSE auf `{{#1778800001033.intent#}}`)
- **qwen2.5:14b**: Ersetzt `gpt-oss`, das Papers außerhalb des Korpus halluzinierte. Streng grounded, keine erfundenen Publikationen mehr
- **top_k: 50**: `TOP_K_MAX_VALUE=50` im Dify-Container gesetzt. Retrieval-Qualität massiv verbessert (11 unique papers statt 2–3)
- **KR Query Rewriter entfernt**: Pass-through für bessere Retrieval-Qualität. Der HyDE-style Rewriter matchte überproportional Bibliographie-Sections
- **Chunk Filter**: Signal-Density-basierte Reference-Erkennung (DOI, nummerierte Refs, Jahreszahlen), Doc-Deduplizierung (max 3 chunks/paper), Safety-Net bei <3 überlebenden Chunks
- **Alle Autoren**: Alle drei Extraction-LLMs listen jetzt sämtliche Autoren pro Paper. "and colleagues" / "et al." explizit verboten. Author Extraction mit `Authors: ... / Quote: ...` Format + Few-Shot Example. Sanitizer mit Autor-Anreicherung aus Chunk-Metadaten (neue Edge Chunk Filter → Sanitizer, 27 Edges)
- **`migrate_to_3llm.py`**: Transformations-Script für YAML-Workflow

## ✅ Alle 3 KR-Routes getestet (2026-07-06, qwen2.5:14b, top_k=50)

### author_lookup

> **Query:** "Who has worked on tRNA modifications or queuosine detection?"

**Route:** Unified Router → `author_lookup` → KR (50 chunks) → Chunk Filter (7 kept / 17 removed) → KR Intent Router → **Author Extraction LLM**

**Answer:**
```
**"Detection of queuosine and queuosine precursors in tRNAs by direct RNA sequencing"**
(Nucleic Acids Res, 2023)
Authors: Yu Sun, Michael Piechotta, Isabel Naarmann-de Vries, Christoph Dieterich,
Ann E. Ehrenhofer-Murray
Quote: "Here, we have employed direct RNA sequencing using nanopore technology to
detect the modification of tRNAs with Q and Q precursors."

**"Functional integration of a semi-synthetic azido-queuosine derivative into
translation and a tRNA modification circuit"** (Nucleic Acids Res, 2022)
Authors: Larissa Bessler, Navpreet Kaur, Lea-Marie Vogt, Laurin Flemmich,
Carmen Siebenaller, Marie-Luise Winz, Francesca Tuorto, Ronald Micura,
Ann E. Ehrenhofer-Murray, Mark Helm
Quote: "We therefore asked whether Q-L1 can serve as a biologically active
surrogate for queuosine in this circuit."

**"Queuosine‐tRNA promotes sex‐dependent learning and memory formation by
maintaining codon‐biased translation elongation speed"** (EMBO J, 2023)
Authors: Cansu Cirzi, Francesca Tuorto
Quote: "Queuosine (Q) is a modified nucleoside at the wobble position of
specific tRNAs."
```
⏱️ 71s | 5 papers, ALL authors listed (5–10 per paper), no "and colleagues"

---

### entity_lookup

> **Query:** "Which RNA modifications are most studied in epitranscriptomics?"

**Route:** Unified Router → `entity_lookup` → KR (50 chunks) → Chunk Filter (16 kept / 16 removed) → KR Intent Router → **Entity Extraction LLM**

**Answer:**
```
| Entity | Type | Paper |
|--------|------|-------|
| N6-methyladenosine (m6A) | RNA modification | "Detecting m6A..." by Adrian Chan,
  Isabel S. Naarmann-de Vries, Carolin P. M. Scheitl, Claudia Höbartner,
  Christoph Dieterich (2024) |
| pseudouridines | RNA modification | "General Principles and Limitations..." by
  Yuri Motorin, Mark Helm (2024) |
| tRNA and rRNA | RNA targets | "General Principles and Limitations..." by
  Yuri Motorin, Mark Helm (2024) |
| EBER2 | viral noncoding RNAs | "EBER2" by N. Lee, B. A. Henry (2022) |
| epitranscriptomic writers | enzymes | "General Principles..." by
  Yuri Motorin, Mark Helm (2024) |
```
⏱️ 62s | Entity-Tabelle mit vollen Paper-Zitaten (alle Autoren + Jahr)

---

### knowledge_retrieval

> **Query:** "What is m6A and which methods are used to detect it?"

**Route:** Unified Router → `knowledge_retrieval` → KR (50 chunks) → Chunk Filter (10 kept / 16 removed) → KR Intent Router → **KR Extraction LLM**

**Answer:**
```
m6A, or N6-methyladenosine, is a prevalent RNA modification that influences
various steps in the RNA life cycle such as mRNA stability, splicing, translation,
and decay.

Methods for detecting m6A:

1. NO-Seq: Chemical treatment + RT + sequencing. ("General Principles and
   Limitations for Detection of RNA Modifications by Sequencing" by
   Yuri Motorin, Mark Helm)

2. Direct RNA Sequencing: Single-molecular resolution without antibodies.
   ("Detecting m6A at single-molecular resolution via direct RNA sequencing
   and realistic training data" by Adrian Chan, Isabel S. Naarmann-de Vries,
   Carolin P. M. Scheitl, Claudia Höbartner, Christoph Dieterich)

3. Antibody-Based: Dot blot, ELISA, DIP-seq. ("Refining the role of
   N6-methyladenosine in cancer" by Jonas Koch, Frank Lyko)

4. Quantitative Mapping: eTAM-seq, GLORI, MePMe-seq, m6A-SAC-seq.
   ("Sci-ModoM: a quantitative database..." by Etienne Boileau,
   Harald Wilhelmi, Anne Busch, Andrea Cappannini, Andreas Hildebrand,
   Janusz M. Bujnicki, Christoph Dieterich)

5. Computational Methods: Pipelines + miCLIP validation. ("Dynamic
   RNA Modifications in Disease" by Janina Fuß, J. Zarnack)
```
⏱️ 68s | 5 methods, each cited with paper title + ALL authors (2–7 per paper), no "and colleagues"

---

## 📊 Vergleich v0.3.2 → v0.4.0

| | v0.3.2 | v0.4.0 |
|---|---|---|
| **Extraction** | 1 LLM, Multi-Intent | 3 LLMs, intent-geroutet |
| **KR Query Rewriter** | HyDE-style Keyword-Expansion | Pass-through |
| **Model** | gpt-oss | qwen2.5:14b |
| **top_k** | 10 | 50 |
| **Autoren** | ❌ Nur Erstautor ("Yu Sun") | ✅ Alle Autoren (5–10 pro Paper) |
| **"and colleagues"** | ❌ Ja | ✅ Nein |
| **Mixed Output** | ❌ Alle 3 Sektionen | ✅ Nur geroutete Sektion |
| **Nodes** | 20 | 22 |
| **Edges** | 22 | 27 |

---

**Full Changelog**: [CHANGELOG.md](https://github.com/dieterich-lab/RmapDifyChatbot/blob/master/CHANGELOG.md)
