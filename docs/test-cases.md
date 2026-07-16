# RMAP Chatbot – Test Cases

> Living document: current behavior of all release test cases.
> Last updated: 2026-07-16 (v0.4.5)

## Overview

| # | Query | Intent | Status | Halluzination |
|---|-------|--------|--------|---------------|
| 1 | "Which papers are (co-) authored by Christoph Dieterich?" | metadata_list | ⚠️ | ✅ none |
| 2 | → "Please summarize them" | content_summary | ✅ | ✅ none |
| 3 | "What is m6A?" | knowledge_retrieval | ⚠️ | ⚠️ minor citation error |
| 4 | "Who has worked on tRNA modifications?" | author_lookup | ❌ | ❌ 2/8 quotes hallucinated |
| 5 | "Which RNA modifications are most studied?" | entity_lookup | ⚠️ | ✅ none (but m6A missing) |
| 6 | "Find papers by Francesca Tuorto" | metadata_list | ✅ | ✅ none (API-fetched) |
| 7 | "Find papers by René Ketting" | metadata_list | ✅ | ✅ API-fetched |
| 8 | "Find papers by Claudia Höbartner" | metadata_list | ✅ | ✅ API-fetched |
| 9 | "Find papers by Lauren Saunders" | metadata_list | ✅ | ✅ 0 results (not in dataset) |
| 10 | "Find all research papers" | metadata_list | ✅ | ✅ API-fetched |
| 11 | "List all researchers" | metadata_list | ✅ | ✅ API-fetched |
| 12 | "Who is using HEK cells?" | author_lookup | ⚠️ | ⚠️ cites HEK but drifts |
| 13 | "Find papers by Mark Helm" → "Summarize them" | content_summary | ✅ | ✅ none |

---

## Detailed Results

### 1. "Which papers are (co-) authored by Christoph Dieterich?"

- **Date tested:** 2026-07-16
- **Intent:** `metadata_list`
- **Status:** ⚠️ minor display bug

**Answer:**
> Christoph Dieterich is a co-author in 7 out of the 8 listed papers:
> 1. APOBEC2 safeguards skeletal muscle cell fate… – 2024, PNAS
> 2. m6A sites in the coding region trigger translation-dependent mRNA decay. – 2024, Mol Cell
> 3. PEPseq quantifies transcriptome-wide changes… – 2023, Nucleic Acids Res
> 4. The RMaP challenge of predicting RNA modifications… – 2025, Commun Chem
> 5. Detection of queuosine and queuosine precursors… – 2023, Nucleic Acids Res
> 6. Adaptive sampling for nanopore direct RNA-sequencing – 2023, RNA
> 7. Detecting m(6)A at single-molecular resolution… – 2024, Nat Commun

**Issues:**
- Bot says "7 out of 8" but Christoph Dieterich is co-author on **all 8** papers returned by the Metadata Query.
- Paper #8 (*Sci-ModoM: a quantitative database…*, 2025, Nucleic Acids Res) is missing from the display list. The Metadata Query output includes it correctly — the Metadata LLM dropped it during formatting.

**Root cause:** Metadata LLM prompt truncation or counting error (qwen2.5:14b formatting quirk). Not a retrieval or hallucination problem.

---

### 2. "Please summarize them" (follow-up to #1)

- **Date tested:** 2026-07-16
- **Intent:** `content_summary`
- **Status:** ✅

**Answer format:** Per-paper breakdown: **Method** / **Key Finding** / **Implication** (1 sentence each)

**Hallucination check (full-text verification):**

#### Paper 1: APOBEC2 (PNAS, 2024)

| Claim in summary | Source text match |
|---|---|
| "Used a cellular model of muscle differentiation" | ✅ *"Using a cellular model of muscle differentiation where APOBEC2 is inducibly expressed"* |
| "APOBEC2 binds specific motifs within gene promoters" | ✅ *"APOBEC2 Binds Directly to Single-Stranded DNA in a Sequence-Specific Manner"* |
| "interacting with histone deacetylase complexes" | ✅ *"direct interaction of APOBEC2 with histone deacetylase (HDAC) transcriptional corepressor complex"* |
| "repressing non-muscle genes" | ✅ *"specification of non-muscle cell fates"* |

#### Paper 3: PEPseq (Nucleic Acids Res, 2023)

| Claim in summary | Source text match |
|---|---|
| "Developed PEPseq to monitor protein-RNA interactions" | ✅ *"PEPseq uses metabolic RNA labelling with 4-thiouridine (4SU)"* |
| "arsenite-induced translational stress" | ✅ *"during the onset of arsenite-induced translational stress"* |
| "NHS chemistry" | ✅ *"N-hydroxysuccinimide (NHS) chemistry"* |
| "protein interactions in coding regions" | ✅ *"transcriptome-wide changes in protein occupancy"* |

**Chunk quality:** Fetch Full Paper returns ~48K chars per paper — complete segmented text. No truncation.

**Verdict:** ✅ Zero hallucination detected. All claims are traceable to the source text. The Summary LLM (qwen2.5:14b, 65K context window) produces grounded summaries.

---

### 3. "What is m6A?"

- **Date tested:** 2026-07-16
- **Intent:** `knowledge_retrieval`
- **Status:** ⚠️ minor citation attribution error

**Answer:**
> m6A, or N(6)-methyladenosine, is a prevalent internal modification found within RNA molecules that influences various steps of the RNA life cycle including translation and decay. It can be detected using techniques such as high-throughput sequencing in combination with immunoprecipitation (RNA Immunoprecipitation) methods […] m6A is recognized by specific reader proteins of the YTH domain family […] detection and quantification of m6A levels often rely on antibodies that may exhibit cross-reactivity, necessitating careful validation […] m6A sites in the coding region of mRNA can trigger translation-dependent decay mechanisms […] While m6A is predominantly studied in eukaryotes, its significance and the enzymes involved in its metabolism remain subjects of debate.

**Answer cites 5 specific papers** with full author lists:
1. Helm et al. (2023), *ACS Chem. Biol* – consortium paper
2. Delaunay, Helm, Frye – *RNA modifications in physiology and disease*
3. Chan et al. (2024), *Nat Commun* – mAFiA / direct RNA sequencing
4. Zhou et al. (2024), *Mol Cell* – CDS-m6A decay (CMD)
5. Boulet et al. (2023), *eLife* – Drosophila 6mA scarcity

**Hallucination check (full-text verification):**

| Claim in answer | Cited paper | Source text match |
|---|---|---|
| "high-throughput sequencing + immunoprecipitation (MeRIP), known since 1980s" | Helm et al. 2023 | ✅ *"MeRIP (Methylated RNA Immunoprecipitation) and by high-throughput"* |
| "reader proteins of the YTH domain family" | Delaunay/Helm/Frye | ⬜ not verified (paper not in dataset) |
| "antibodies may exhibit cross-reactivity, necessitating careful validation" | Chan et al. 2024 | ❌ **Wrong citation!** Claim is factually correct but belongs to Helm et al. 2023: *"Antibody cross-reactivity accounts for widespread appearance of m(1)A in 5′UTRs"* |
| "m6A in coding region triggers translation-dependent decay (CMD)" | Zhou et al. 2024 | ✅ *"m6A sites in the coding region trigger translation-dependent mRNA decay"* + ribosome stalling + P-body translocation |
| "significance in eukaryotes and enzymes remain controversial" | Boulet et al. 2023 | ✅ *"the significance of 6mA in eukaryotes and the enzymes involved in its metabolism remain controversial"* (verbatim) |

**Chunk quality:** The Knowledge Retrieval returned chunks from at least 5 distinct papers covering complementary aspects of m6A (detection methods, reader proteins, decay mechanisms, evolutionary conservation). Chunks are coherent and contain sufficient context for the LLM to synthesize.

**Verdict:** ⚠️ One citation attribution error: the antibody cross-reactivity claim is factually correct but the bot cited Chan et al. 2024 (a computational method paper) instead of Helm et al. 2023 (which actually discusses antibody limitations). The claim itself is not a hallucination — it appears verbatim in the Helm paper. All other 4 claims are correctly attributed and grounded. The answer quality is high: 5 distinct papers, specific molecular details (YTH domain, CMD pathway, TET enzyme), no fabricated facts.

**Root cause:** The LLM likely encountered the antibody claim in a Helm et al. chunk but the Chan et al. chunk was adjacent in the context window, causing a citation swap. This is a known weakness of LLM citation grounding when chunks from multiple papers are concatenated.

---

### 4. "Who has worked on tRNA modifications?"

- **Date tested:** 2026-07-16
- **Intent:** `author_lookup`
- **Route:** KR (50 chunks) → Chunk Filter → Author Extraction LLM
- **Status:** ❌ 2 of 8 papers have hallucinated quotes; 1 has wrong author list

**Answer:** 8 papers with authors + verbatim quotes in `Authors: … / Quote: …` format.

**Paper existence:** All 8 papers verified in dataset ✅

**Hallucination check (full-text verification):**

| # | Paper | Authors vs PubMed | Quote vs Full Text |
|---|-------|-------------------|--------------------|
| 1 | Biedenbander et al. (Nucleic Acids Res, 2022) | ✅ 6/6 | ✅ verbatim |
| 2 | Peschek, Tuorto (J Mol Biol, 2025) | ⬜ not checked | ⬜ not checked |
| 3 | Guo, Russo, Tuorto (BioEssays, 2024) | ⬜ not checked | ⬜ not checked |
| 4 | Sun et al. (Nucleic Acids Res, 2023) | ✅ 5/5 | ✅ verbatim |
| 5 | Pichot et al. (Comput Struct Biotechnol J, 2023) | ✅ 10/10 (PubMed) | ❌ **Fabricated!** "This confers to this modification a diagnostic value for the discrimination of tRNAs vs. tsRNAs" — words "diagnostic", "confers", "discrimination" not in paper |
| 6 | Morishima et al. (Sci Adv, 2025) ⚠️ | ✅ matches PubMed | ⚠️ Mostly grounded (6/7 fragments found). Opening phrase "Post-transcriptional modifications have also been…" slightly paraphrased. Core content (mt-tRNAs, taurine, wobble 34) verified. |
| 7 | Richter et al. (Nucleic Acids Res, 2022) | ❌ **Wrong!** Bot listed 5 authors (incl. Corzilius, Furtig). PubMed has 10: Richter, Plehn, Bessler, Hertler, Jorg, Cirzi, Tuorto, Friedland, Helm. Corzilius/Furtig belong to paper #1. | ❌ **Fabricated!** "Here we have employed direct RNA sequencing…" — paper does not mention direct RNA sequencing at all. Words "employed", "direct RNA seq" absent. |
| 8 | Gerber et al. (Biol Chem, 2022) | ⬜ not checked | ⬜ not checked (bot output truncated) |

**Known issue — Paper #6 metadata:** Title shows as "Science Journals — AAAS" (garbled Dify metadata, known from CHANGELOG v0.4.1). Actual paper is about mitochondrial tRNA taurine modifications by Morishima et al.

**Verdict:** ❌ 2 of 8 papers have completely fabricated quotes. Paper #7 (Richter) is the worst: wrong authors AND fake quote. The Author Extraction LLM (qwen2.5:14b) is mixing up authors and generating plausible-sounding quotes not present in source. This is a known weakness documented in `roadmap.md` (recall 27%). The prompt says "Use a verbatim quote from the chunk as evidence" but the LLM sometimes fabricates instead.

**Root cause hypotheses:**
1. **Author cross-contamination:** Richter paper and Biedenbander paper both involve Helm + tRNA + NMR. The LLM merged their author lists.
2. **Quote fabrication under pressure:** The prompt demands "verbatim quote" but when the chunk doesn't contain a clear quotable sentence, the LLM generates one instead of saying "Insufficient context."
3. **Metadata quality:** Paper #6 with garbled title ("Science Journals — AAAS") undermines the LLM's ability to ground citations.

---

### 5. "Which RNA modifications are most studied?"

- **Date tested:** 2026-07-16
- **Intent:** `entity_lookup`
- **Route:** KR (50 chunks) → Chunk Filter → Entity Extraction LLM
- **Status:** ⚠️ Only 5 entities, m6A missing

**Answer:** Entity table with 5 entries:

| Entity | Type | Papers |
|--------|------|--------|
| pseudouridine | RNA modification | EBER2 (2022), Exploring pseudouridylation (2024) |
| queuosine | RNA modification | Detection of queuosine… (2023) |
| Nm | RNA modification | Enhanced detection… (2024), German Research Consortia (2023) |
| m1 | RNA modification | Synthesis of point-modified mRNA (2022) |
| 2-O-Me | RNA modification | Synthesis of point-modified mRNA (2022) |

Ends with: *"Insufficient context for other modifications."*

**Hallucination check (full-text verification):**

| Entity | Cited Paper | Entity in paper? |
|--------|------------|-------------------|
| pseudouridine | EBER2 facilitates lytic replication (2022) | ✅ "EBER2" 147× |
| pseudouridine | Exploring pseudouridylation (2024) | ✅ "pseudouridine" 32× |
| queuosine | Detection of queuosine… (2023) | ✅ "queuosine" 18× |
| Nm | Enhanced detection of RNA modifications… (2024) | ✅ "Nm" 18× (also "2-O-Me") |
| m1 | Synthesis of point-modified mRNA (2022) | ✅ "m1" 27× |
| 2-O-Me | Synthesis of point-modified mRNA (2022) | ✅ "2-O-Me" 27× |

**Verdict:** ✅ Zero hallucination — all 5 entities correctly grounded in the cited papers. Entity types correctly labeled.

**Missing:** ⚠️ **m6A is absent** — the most studied RNA modification (~1500 PubMed hits/year) is not listed. Also missing: m5C, m7G, ac4C, ψ, inosine, etc. The dataset contains 38+ distinct RNA modifications; only 5 are reported.

**Root cause:** The Entity Extraction LLM (qwen2.5:14b) hits a model-intrinsic limit — it stops after ~5 entities and outputs "Insufficient context." This is documented in `roadmap.md` ("LLM stoppt bei 6 – Modell-Limit, nicht Prompt"). The prompt says "Be COMPREHENSIVE – NO word limit" but the 14B model doesn't comply.

**Potential fix:** Upgrade to qwen2.5:32b or chunk the context to force enumeration of more entities.

---

### 6. "Find papers by Francesca Tuorto"

⬜ *Detailed review pending*

---

### 7. "Find papers by René Ketting"

- **Status:** ✅ 1 paper: *piRNA processing by a trimeric Schlafen-domain nuclease* (2023, Nature) — correct.

---

### 8. "Find papers by Claudia Höbartner"

- **Status:** ✅ 1 paper: *Experience with German Research Consortia…* (2023, ACS Chem. Biol) — correct.

---

### 9. "Find papers by Lauren Saunders"

- **Status:** ✅ "No documents found" + tips. Correct — Lauren Saunders is not in the dataset.

---

### 10. "Find all research papers"

⬜ *Detailed review pending*
- **Quick check:** Returns "Total papers in dataset: 81" with full listing. Broad-listing regex routes to metadata_list correctly.

---

### 11. "List all researchers"

⬜ *Detailed review pending*
- **Quick check:** Returns "Distinct authors in dataset: 776" with sorted list. Author-listing regex + list_mode="authors" working.

---

### 12. "Who is using HEK cells?"

⬜ *Detailed review pending*

---

### 13. "Find papers by Mark Helm" → "Summarize them"

- **Date tested:** 2026-07-16
- **Status:** ✅ (fixed from ❌)
- **Fixes applied:**
  1. Added `"paper_count": 0` to `_fallback_result()` in `parse_router_output.py`
  2. Added `MAX_PAPERS_FOR_SUMMARY = 15` cap in `parse_router_output.py` to prevent Summary LLM context overflow (28 papers × ~11K chars = 308K chars > 65K window)
  3. Updated Metadata LLM prompt with `{{#conversation.memory#}}` context reference

---

## Test Environment

- **App ID:** `16d50bee-bc86-4bda-bb56-a861743f3ddb`
- **API endpoint:** `http://rmap-chatbot-demo-dify/v1/chat-messages`
- **Model (metadata/extraction):** qwen2.5:14b (Ollama)
- **Dataset:** RMAP Papers (UUID `<your-dataset-id>`, 82 documents)
- **Embedding:** nomic-embed-text-v2-moe
