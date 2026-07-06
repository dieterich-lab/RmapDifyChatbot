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
- **Author-Halluzination behoben**: Prompt hardened – extrahiert nur Autoren aus "From paper:"-Headern
- **`migrate_to_3llm.py`**: Transformations-Script für YAML-Workflow

## ✅ Alle 3 KR-Routes getestet (2026-07-06, qwen2.5:14b, top_k=50)

### author_lookup

> **Query:** "Who has worked on tRNA modifications or queuosine detection?"

**Route:** Unified Router → `author_lookup` → KR (50 chunks) → Chunk Filter (7 kept / 19 removed) → KR Intent Router → **Author Extraction LLM**

**Answer:**
```
**Direct RNA Sequencing for Queuosine Detection** (Nucleic Acids Res)
- Anne E Ehrenhofer-Murray: "Here, we have employed direct RNA sequencing using
  nanopore technology to detect the modification of tRNAs with Q and Q precursors."

**Queuosine Biosynthesis and Its Impact on tRNA Modifications** (Nucleic Acids Res)
- Markus Helm: "Having established that preQ1-L1 is actively incorporated into
  native tRNAs, we next investigated a particularly interesting effect of queuosine..."

**Queuosine Introduction by TGT Complex in Human Cells** (BioEssays)
- Frank Tuorto: "For different species, including human, discrete tRNAs are
  further modified by QTGAL or QTMAN..."

**Queuosine and Its Role in Translation Optimization** (J Mol Biol)
- Frank Tuorto: "Glycosylated queuosines in tRNAs optimize translational rate
  and post-embryonic growth."

**Computational Analysis of RNA Modifications** (Comput Struct Biotechnol J)
- Markus Helm: "This confers to this modification a diagnostic value for the
  discrimination of tRNAs vs. tsRNAs."
```
⏱️ 61s | 5 papers, 3 authors, alle grounded

---

### entity_lookup

> **Query:** "Which RNA modifications are most studied in epitranscriptomics?"

**Route:** Unified Router → `entity_lookup` → KR (50 chunks) → Chunk Filter (16 kept / 16 removed) → KR Intent Router → **Entity Extraction LLM**

**Answer:**
```
| Entity | Type | Paper |
|--------|------|-------|
| N6-methyladenosine (m6A) | RNA modification | Helm M, Motorin Y, 2021, WIREs RNA |
| pseudouridines and 5-substituted U residues | RNA modifications | Helm M, Richter F, 2022, Nucleic Acids Res |
| tRNA and rRNA | RNA targets | Helm M, Motorin Y, 2021, WIREs RNA |
| EBER2 | viral noncoding RNAs | Lee N, Henry BA, 2022, RNA |
| epitranscriptomic "writers" | enzymes | Helm M, Motorin Y, 2021, WIREs RNA |
```
⏱️ 64s | Entity-Tabelle mit Paper-Attribution

---

### knowledge_retrieval

> **Query:** "What is m6A and which methods are used to detect it?"

**Route:** Unified Router → `knowledge_retrieval` → KR (50 chunks) → Chunk Filter (13 kept / 24 removed) → KR Intent Router → **KR Extraction LLM**

**Answer:**
```
N6-methyladenosine (m6A) is "the most abundant internal mRNA modification,
with estimates ranging from 1 to 13 modifications present per transcript."
Methods for detecting m6A include antibody-based protocols such as methylated
RNA immunoprecipitation sequencing (MeRIP-seq), which involves "cDNA synthesis
by reverse transcription and PCR-based library amplification," and miCLIP,
where "RNA crosslinking and immunoprecipitation with an m6A-specific antibody"
is performed. Additionally, enzyme-assisted approaches like the use of
methylation-sensitive restriction enzymes (MazF) are mentioned for mapping
m6A sites. These methods rely on high-throughput short-read sequencing on
platforms such as Illumina to profile transcriptome-wide m6A methylation.
```
⏱️ 81s | Verbatin quotes, fully grounded

---

## 📊 Vergleich v0.3.2 → v0.4.0

| | v0.3.2 | v0.4.0 |
|---|---|---|
| **Extraction** | 1 LLM, Multi-Intent | 3 LLMs, intent-geroutet |
| **KR Query Rewriter** | HyDE-style Keyword-Expansion | Pass-through |
| **Model** | gpt-oss | qwen2.5:14b |
| **top_k** | 10 | 50 |
| **Author-Halluzination** | ❌ Papers erfunden | ✅ Nur "From paper:"-Header |
| **Mixed Output** | ❌ Alle 3 Sektionen | ✅ Nur geroutete Sektion |
| **Nodes** | 20 | 23 |
| **Edges** | 22 | 27 |

---

**Full Changelog**: [CHANGELOG.md](https://github.com/dieterich-lab/RmapDifyChatbot/blob/master/CHANGELOG.md)
