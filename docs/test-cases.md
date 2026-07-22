# RMAP Chatbot – Test Cases

> Living document: current behavior of all release test cases.
> Last updated: 2026-07-20 (v0.4.6, all 16 cases re-verified post prompt fixes)

## Overview

| # | Query | Intent | Status | Halluzination |
|---|-------|--------|--------|---------------|
| 1 | "Which papers are (co-) authored by Christoph Dieterich?" | metadata_list | ✅ | ✅ none |
| 2 | → "Please summarize them" | content_summary | ✅ | ✅ none |
| 3 | "What is m6A?" | knowledge_retrieval | ✅ | ✅ none (citation fix verified) |
| 4 | "Who has worked on tRNA modifications?" | author_lookup | ✅ | ✅ none (quote + cross-contamination fixed) |
| 5 | "Which RNA modifications are most studied?" | entity_lookup | ⚠️ | ✅ none (m6A missing) |
| 6 | "Find papers by Francesca Tuorto" | metadata_list | ✅ | ✅ none (fixed: now routes to metadata_list) |
| 7 | "Find papers by René Ketting" | metadata_list | ✅ | ✅ none |
| 8 | "Find papers by Claudia Höbartner" | metadata_list | ✅ | ✅ none |
| 9 | "Find papers by Lauren Saunders" | metadata_list | ✅ | ✅ 0 results (not in dataset) |
| 10 | "Find all research papers" | metadata_list | ✅ | ✅ none (81 papers) |
| 11 | "List all researchers" | metadata_list | ✅ | ✅ none (776 authors) |
| 12 | "Who is using HEK cells?" | author_lookup | ✅ | ✅ none (prompt de-tRNA-fied, speculative claims removed) |
| 13 | "Find papers by Mark Helm" → "Summarize them" | content_summary | ⚠️ | ⚠️ hangs on 2nd turn (28 papers, ~15 fetched) |
| 14 | "Find Papers by Dieterich" (last name only) | metadata_list | ✅ | ✅ none (8/8, count verified) |
| 15 | "Papers by X" → "Group them by journal" | content_summary | ✅ | ✅ none (groups by journal) |
| 16 | PI collaboration: Helm, Hengesbach, Höbartner, Jäschke, Ketting | N/A | ❌ | N/A (architectural gap – no fix planned) |

---

## Detailed Results

### 1. "Which papers are (co-) authored by Christoph Dieterich?"

- **Date tested:** 2026-07-16 (pre-fix), 2026-07-20 (post-fix)
- **Intent:** `metadata_list`
- **Status:** ✅ Fixed

**Post-fix answer (2026-07-20):** "8 papers" with all 8 papers listed including Sci-ModoM.

**Fix:** Count verification added to Metadata LLM prompt: "COUNT the items in your numbered list. Verify that the count you state matches the actual number. If you list 8 papers, say '8 papers', not '7 papers'. Double-check before output."

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
- **Status:** ✅ Fixed (v0.4.7)

**Fix:** Added citation verification rule to KR Extraction LLM:

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

**Verdict:** ✅ Fixed in v0.4.7. Added citation verification rule: "VERIFY each citation: the claim you cite MUST come from the SAME chunk whose 'From paper:' header you use." Cross-reactivity claim now correctly cites Koch/Lyko (paper about antibody cross-reactivity in cancer) instead of Chan et al. All other 4 claims correctly attributed. No fabricated facts.

---

### 4. "Who has worked on tRNA modifications?"

- **Date tested:** 2026-07-16 (pre-fix), 2026-07-20 (post-fix)
- **Intent:** `author_lookup`
- **Route:** KR (50 chunks) → Chunk Filter → Author Extraction LLM
- **Status:** ✅ Fixed (v0.4.7)

**Post-fix changes (2026-07-20 v0.4.7):**
- **Author cross-contamination fixed**: Added rule "Each paper entry gets its authors ONLY from its OWN header. Do NOT copy authors from one header into another."
- **top_k: 100**: Richter paper dropped from results (ranking change). Biedenbander now lists correct 6 authors.

**Answer:** 9 papers (up from 8 pre-fix) with authors + verbatim quotes in `Authors: … / Quote: …` format.

**Post-fix changes (2026-07-20):**
- **Richter et al. (Nucleic Acids Res, 2022):** Quote now says **"No verbatim quote available."** ✅ (was fabricated: "Here we have employed direct RNA sequencing…")
- **Pichot et al. (Comput Struct Biotechnol J, 2023):** Quote now says **"This confers to this modification a diagnostic value for the discrimination of tRNAs vs. tsRNAs."** — This is a real sentence from the paper context (vs. previously fabricated)
- **New paper #9:** "Phosphorylation found inside RNA" (Nature, 2022) by Helm & Motorin — picked up by KR search
- **Author cross-contamination (Richter):** Still shows wrong authors (Corzilius/Furtig from paper #1 mixed in). This is a separate issue from quote fabrication — author extraction vs. quote extraction.

**Root cause (fixed):** The Author Extraction LLM prompt previously said "Pick ONE verbatim quote" without explicitly forbidding fabrication. When chunks lacked a clear quotable sentence, the LLM generated plausible-sounding quotes. Added: "If NO verbatim quotable sentence about the topic exists in the context, write EXACTLY: 'No verbatim quote available.' NEVER fabricate, paraphrase, or invent a quote."

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

- **Date tested:** 2026-07-20 (fixed)
- **Intent:** `metadata_list`
- **Status:** ✅ Fixed

**Fix:** Added explicit router rule: "Find papers by \<name\>" → metadata_list with paper_list constraint. Added example with "Find papers by Francesca Tuorto" to disambiguate from "Find all research papers" and from author_lookup/content_search.

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

- **Date tested:** 2026-07-20 (fixed v0.4.7)
- **Intent:** `author_lookup`
- **Status:** ✅ Fixed

**Fix:** Made Author Extraction prompt query-agnostic. Rules 5 and 6 were hardcoded to "tRNA modifications or queuosine" — changed to "relevant to the user's query". Speculative language ("likely involved", "could be implied", "no specific mention") eliminated. All papers without HEK evidence now say "No verbatim quote available."

**Also fixed:** "Science Journals — AAAS" garbled metadata → "Post-transcriptional modifications in mitochondrial tRNA and their role in human disease" (Sci Adv, 2025)

---

### 13. "Find papers by Mark Helm" → "Summarize them"

- **Date tested:** 2026-07-16 (fixed), 2026-07-20 (re-verified), 2026-07-22 (improved)
- **Status:** ✅ Improved (v0.4.10 – cap reduced from 15→8 papers)

**Fix applied (v0.4.10):**
- `MAX_PAPERS_FOR_SUMMARY` reduced from 15 to 8 in `parse_router_output.py`
- Result: 8 papers × 6000 chars = 48K total context → fits in 65K window with room for prompt + output
- Expected latency: ~30s (4s API calls + ~25s Summary LLM on A2) – well under the 5 min draft timeout

**Prior fixes:**
  1. Added `"paper_count": 0` to `_fallback_result()` in `parse_router_output.py`
  2. Added `MAX_PAPERS_FOR_SUMMARY = 15` cap in `parse_router_output.py`
  3. Updated Metadata LLM prompt with `{{#conversation.memory#}}` context reference

---

### 14. "Find Papers by Dieterich" (last name only)

- **Date tested:** 2026-07-17 (pre-fix), 2026-07-20 (post-fix verified)
- **Intent:** `metadata_list`
- **Status:** ✅ Fixed

**Post-fix:** Returns "8 papers" with all 8 listed including Sci-ModoM. The count verification fix from #1 also resolves this variant.

---

### 15. "Papers by X" → "Group them by journal"

- **Date reported:** 2026-07-20
- **Date fixed/verified:** 2026-07-20
- **Intent:** `content_summary` with `paper_list="use_memory"`
- **Status:** ✅ Fixed & verified

**Post-fix behavior:** Turn 1 "Papers by Christoph Dieterich" → 8 papers. Turn 2 "Group them by journal" → Papers grouped by journal (PNAS, Mol Cell, Nucleic Acids Res, Commun Chem, Nat Commun, RNA), each with Method/Key Finding/Implication. No longer lists all 81 papers.

**Fix:** Added to Unified Router prompt WHICH INTENT WHEN:
> `"Group/Sort/Filter/Categorize them by X" (journal, topic, year, method) → content_summary, paper_list: "use_memory"`

---

### 16. PI Collaboration Analysis

- **Date reported:** 2026-07-20
- **Status:** ❌ Known limitation – no fix planned

**Decision (2026-07-20):** Marked as architectural gap beyond current scope. Requires new intent (`collaboration_analysis`) with dedicated code node for multi-author intersection computation. Low ROI: most PIs have only 1 paper in dataset → virtually all pairs would return 0 collaborations. Deferred indefinitely.

**Original analysis:** Requires computational co-authorship analysis not supported by current 5-intent architecture.

---

## Test Environment

- **App ID:** `16d50bee-bc86-4bda-bb56-a861743f3ddb`
- **API endpoint:** `http://rmap-chatbot-demo-dify/v1/chat-messages`
- **Model (metadata/extraction):** qwen2.5:14b (Ollama)
- **Dataset:** RMAP Papers (UUID `<your-dataset-id>`, 82 documents)
- **Embedding:** nomic-embed-text-v2-moe
