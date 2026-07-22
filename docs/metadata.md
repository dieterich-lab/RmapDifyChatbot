# Metadata Coverage Report

> Final: 2026-07-22 · Model: qwen3:32b (gpu-g5-1 H100) · Pipeline: PubMed → CrossRef → LLM → Fallback

## Summary

| Source | Count | % |
|--------|-------|---|
| PUBMED | 73 | 87% |
| CROSSREF | 1 | 1% |
| LLM (qwen3:32b) | 10 | 12% |
| **Total** | **84** | **100%** |

## Historical Trend

| Datum | PubMed | CrossRef | LLM | LLM Model | Runtime |
|-------|--------|----------|-----|-----------|--------|
| 2026-06-30 | 69 | 0 | 0 | – | – |
| 2026-07-22 (14B) | 74 | 0 | 10 | qwen2.5:14b @ app01 | ~2 min |
| 2026-07-22 (32B) | 73 | 1 | 10 | qwen3:32b @ gpu-g5-1 | ~8 min |

## Pipeline

```
1. PubMed    (DOI → PMID → MEDLINE)       ← authoritative
2. CrossRef  (DOI → api.crossref.org)     ← broader coverage
3. LLM       (PDF header → BAML/qwen3:32b) ← for papers without valid DOIs
4. Fallback  (filename parsing)           ← last resort (not needed)
```

## CrossRef Paper (1)

| # | Paper | Title |
|---|-------|-------|
| 1 | Helm M, Motorin Y, 2021, WIREs RNA | tRNA modifications and their role in... |

## LLM Papers (qwen3:32b, 10 papers)

| # | Paper | Title | Authors (excerpt) |
|---|-------|-------|-------------------|
| 1 | Dieterich C, Naarmann-de Vries IS, 2023, RNA | Adaptive sampling for nanopore direct RNA-sequencing | ISABEL S. NAARMANN-DE VRIES, ENIO GJERGA, CHRISTOPH DIETERICH |
| 2 | Hildebrand A, Schmidt B, 2024, Drug Discov Today | From GPUs to AI and quantum: three waves of acceleration in bioinformatics | Bertil Schmidt, Andreas Hildebrandt |
| 3 | Hore TA, Ravichandran M, 2022, Sci Adv | Pronounced sequence specificity of the TET enzyme catalytic domain... | Mirunalini Ravichandran, Dominik Rafalski, Claudia I. Davies, ... |
| 4 | Lee N, Henry BA, 2022, RNA | Pseudouridylation of Epstein-Barr virus noncoding RNA EBER2 facilitates lytic replication | BELLE A. HENRY, VIRGINIE MARCHAND, BRENT T. SCHLEGEL, MARK HELM, YURI MOTORIN, NARA LEE |
| 5 | Liu W, Zhang H, 2021 IEEE-ACM TRANSACTIONS | RabbitFX: Efficient Framework for FASTA/Q File Parsing on Modern Multi-Core Platforms | Hao Zhang, Honglei Song, Xiaoming Xu, ... |
| 6 | Lyko F, Koch J, 2023, iScience | Reinvestigating the clinical relevance of the m6A writer METTL3 in urothelial carcinoma | Jonas Koch, Manuel Neuberger, Martina Schmidt-Dengler, ... |
| 7 | Motorin Y, Helm M, 2022, Nature | Reversible internal phosphorylation of transfer RNA | Mark Helm, Yuri Motorin |
| 8 | Naarmann-de Vries IS, Lemsara A, 2023, Methods Mol Biol (Chapter 16) | Computational Epigenomics and Epitranscriptomics | ⚠️ Editor names mixed with authors |
| 9 | Pan-Hammarström Q, Pecori R, 2023, iScience | ADAR1-mediated RNA editing promotes B cell lymphomagenesis | Riccardo Pecori, Weicheng Ren, Mohammad Pirmoradian, ... |
| 10 | Takizawa H, Morishima T, 2025, Sci Adv | Mitochondrial translation regulates terminal erythroid differentiation by maintaining iron homeostasis | Tatsuya Morishima, Md. Fakruddin, Yohei Kanamori, ... |

> ⚠️ #8 is a book chapter. Both 14B and 32B models confuse editor names with author names. Manual curation recommended.

## PubMed Papers (73)

Full details in `reports/metadata_dump_32b.json`. All 73 papers have verified title, authors, year, journal, PMID, and DOI from MEDLINE.

## Method

- **PubMed**: DOI extracted from PDF pages 1–3 (longest match) → NCBI E-utilities → MEDLINE
- **CrossRef**: `https://api.crossref.org/works/{doi}` → title, author (family+given), container-title, date-parts
- **LLM**: PDF page 1 via `pdftotext` → BAML `ExtractTitleFromHeader` + `ExtractAuthorsFromHeader` → qwen3:32b (Ollama on H100/gpu-g5-1), temperature 0.0, max_tokens 2048
- **Dify push**: `scripts/push_metadata.py` → Dify v1 API → 82/84 documents updated. 2 PDFs (Höfer 2023, Schaffrath 2025) sind nicht im Dataset – reines Upload-Gap, kein Metadata-Gap. Metadaten für alle 84 liegen in `reports/metadata_dump_32b.json` vor.
- **SLURM job**: `scripts/slurm_extract_metadata_32b.sh` → `sbatch` on gpu-g5-1
