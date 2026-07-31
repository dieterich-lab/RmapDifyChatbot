# RMAP Chatbot – Timing Benchmarks

> **Purpose:** Track end-to-end latency across hardware configurations for regression testing and capacity planning.
> **Last updated:** 2026-07-30 · v0.4.17 · H100 model comparison: qwen3:32b vs qwen3.5:35b

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

## H100 Model Comparison: qwen3:32b vs qwen3.5:35b (2026-07-30)

Both are "thinking" models that produce internal reasoning tokens before generating output. Measured via Draft API (`/console/api/apps/{id}/advanced-chat/workflows/draft/run`, SSE streaming), single-turn, warm start. Both on H100 `gpu-g5-1:21434`, `max_tokens=4096` (unless noted).

### qwen3:32b (20 GB VRAM)

| # | Intent | Query | Thinking Tokens | Time (s) | Finish |
|---|--------|-------|-----------------|----------|--------|
| 1 | `knowledge_retrieval` | What is m6A? | 1,226 | 26.5 | stop |
| 2 | `entity_lookup` | Which RNA modifications most studied? | ~1,000 | ~20 | stop |
| 3 | `metadata_list` | Paper by Jean-Yves Roignant | 1,011 | 23.5 | stop |
| 4 | `metadata_list` | Papers 2020–2025 by Dieterich | 1,280 | 28.9 | stop |
| 5 | `knowledge_retrieval` | Summarize RMaP challenge 2025 | 835 | 26.7 | stop |
| 6 | `metadata_list` | Hello (greeting edge case) | ~600 | ~10 | stop |
| 7 | `knowledge_retrieval` | List papers about RNA mod detection | ~1,000 | ~25 | stop |
| 8 | `metadata_list` | Papers with Roignant in title | ~1,000 | ~20 | stop |

**Key metrics:**
- Thinking: 800–1,300 tokens (fits within 4,096 budget with room for output)
- Per-node latency: 8–29s (Router: 8–18s, Summary/Metadata: 20–29s)
- All `finish_reason=stop` — never hits token limit
- Reasoning separated into `reasoning_content` field (visible in Dify SSE)
- Output quality: structured with real citations, 10-entity tables, full author lists

### qwen3.5:35b (24 GB VRAM)

| Test | Tokens | Time | Finish | Notes |
|------|--------|------|--------|-------|
| Direct API (no context, `max_tokens=2,000`) | 731 | 9s | stop | ✅ Simple prompts work |
| Direct API (no context, `max_tokens=50,000`) | 3,857 | 46s | stop | ✅ Full output: 9,807 chars |
| Dify Router (simple prompt, 4,096 tokens) | 957 | 17.7s | stop | ✅ Router only — short prompt |
| Dify Summary (11 chunks, 4,096 tokens) | 4,096 | 54s | **length** | ❌ All tokens consumed by thinking; `text=""` |
| Dify Summary (11 chunks, 50,000 tokens) | — | >300s | timeout | ❌ GPU unresponsive during test |
| Dify "Hello" (50,000 tokens) | — | >120s | timeout | ❌ Even simplest query timed out |

**Key findings:**
- Thinking extremely verbose: ~53% of tokens for simple prompts, ~100% for context-heavy prompts (11 paper chunks)
- 4,096 token budget insufficient for any context-heavy LLM node
- With 50K tokens, model should theoretically work (46s direct API) but Dify timed out at 300s — likely GPU memory contention from other loaded models on the shared H100
- `reasoning_content` is empty via Ollama's `/v1/chat/completions` endpoint — thinking tokens consumed internally but not exposed to Dify
- Estimated at scale: 90–120s per Dify query (3–4× slower than qwen3:32b)

### Decision: qwen3:32b Selected for H100 Production

| Factor | qwen3:32b | qwen3.5:35b |
|--------|-----------|-------------|
| Thinking budget fit | ✅ Fits in 4,096 tokens | ❌ Needs 8K+ for context-heavy prompts |
| Per-node latency | 8–29s | 17–54s (est. 30–60s at scale) |
| Output quality | ⭐⭐⭐ Real citations, structured | ⭐⭐⭐ Comparable (where it finishes) |
| Reliability | ✅ 8/8 smoke tests pass | ❌ 1/4 Dify tests pass (only router) |
| GPU stability | ✅ Stable on shared H100 | ❌ Intermittent unresponsiveness |

**Verdict:** qwen3:32b is the clear production choice. qwen3.5:35b is deferred pending: (a) dedicated GPU allocation to avoid memory contention, (b) Dify timeout configuration review for long-running thinking models, (c) evaluation of whether the quality gain justifies 3–5× latency increase.

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
    r = requests.post('http://<your-dify-host>/v1/chat-messages',
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
