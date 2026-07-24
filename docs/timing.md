# RMAP Chatbot – Timing Benchmarks

> **Purpose:** Track end-to-end latency across hardware configurations for regression testing and capacity planning.
> **Last updated:** 2026-07-21 · v0.4.8 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb`

## Current Baseline: A2 (Ampere, 16 GB VRAM)

**Ollama Server:** `http://app01.internal:21434` · **Model:** qwen2.5:14b · **top_k:** 100

Measured via Runtime API (`/v1/chat-messages`, blocking mode), single-turn, cold start.

| # | Intent | Query | Total (s) | Answer (chars) |
|---|--------|-------|-----------|----------------|
| 1 | `metadata_list` | Find Papers by Dieterich | 55.5 | 1,045 |
| 2 | `knowledge_retrieval` | What is m6A? | 90.3 | 2,787 |
| 3 | `author_lookup` | Who has worked on tRNA modifications? | 134.8 | 4,616 |

### Breakdown by Intent

- **metadata_list** (fastest): ~56s. Dify Dataset API call (~1–2s) + Metadata LLM formatting (~50s). LLM is the bottleneck.
- **knowledge_retrieval** (medium): ~90s. Hybrid retrieval (top_k=100) → KR Chunk Filter → KR Extraction LLM.
- **author_lookup** (slowest): ~135s. Same retrieval + filter path, plus Author Extraction LLM prompt is heavier (lists all authors + quotes per paper).

### Key Observation

All times are **LLM-dominated**. The qwen2.5:14b on A2 (16 GB VRAM) is the primary bottleneck. Non-LLM overhead (API calls, chunk filtering) is negligible (< 5s).

---

## Comparison: H100 (80 GB VRAM)

**Ollama Server:** `http://gpu-g5-1:21434` · **Model:** qwen2.5:14b · **top_k:** 100

| # | Intent | Query | Total (s) | vs. A2 | Answer (chars) |
|---|--------|-------|-----------|--------|----------------|
| 1 | `metadata_list` | Find Papers by Dieterich | 24.5 | **2.3× faster** | 1,045 |
| 2 | `knowledge_retrieval` | What is m6A? | 32.0 | **2.8× faster** | 2,567 |
| 3 | `author_lookup` | Who has worked on tRNA modifications? | 37.3 | **3.6× faster** | 8,044 |

### Speedup Analysis

| Intent | A2 (s) | H100 (s) | Speedup |
|--------|--------|----------|---------|
| `metadata_list` | 55.5 | 24.5 | **2.3×** |
| `knowledge_retrieval` | 90.3 | 32.0 | **2.8×** |
| `author_lookup` | 134.8 | 37.3 | **3.6×** |

Heavier prompts benefit disproportionately: the Author Extraction LLM (longest prompt, most output tokens) sees the largest gain. LLM inference is the dominant factor — H100's higher memory bandwidth and compute eliminate the A2's bottleneck.

---

## Methodology

- **API:** Runtime API (`/v1/chat-messages`, `response_mode: blocking`)
- **Measurement:** Python `time.time()` around `requests.post()`, includes network latency to Dify + Ollama
- **Cold start:** Each query runs in a fresh conversation (no cache)
- **Model:** qwen2.5:14b via Ollama, temperature 0 on all LLM nodes

## How to Re-run

```bash
DIFY_APP_API_KEY="app-..." python3 -c "
import requests, time
h = {'Authorization': 'Bearer $DIFY_APP_API_KEY'}
for q in ['Find Papers by Dieterich', 'What is m6A?', 'Who has worked on tRNA modifications?']:
    t0 = time.time()
    r = requests.post('http://rmap-chatbot-demo-dify/v1/chat-messages',
        headers=h, json={'query':q, 'inputs':{}, 'response_mode':'blocking', 'user':'bench'})
    print(f'{q}: {round(time.time()-t0,1)}s')
"
```

### A2 vs H100 Timing Benchmarks

Identical model (`qwen2.5:14b`) across hardware, per `docs/timing.md`:

| Intent | A2 (16 GB) | H100 (94 GB) | Speedup |
|--------|-----------|-------------|---------|
| `metadata_list` | 55.5s | 24.5s | **2.3×** |
| `knowledge_retrieval` | 90.3s | 32.0s | **2.8×** |
| `author_lookup` | 134.8s | 37.3s | **3.6×** |

LLM inference is the dominant bottleneck; H100 eliminates the A2's memory bandwidth limit. Heavier prompts benefit disproportionately.
