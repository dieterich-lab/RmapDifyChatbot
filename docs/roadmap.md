# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-29 · v0.4.16 · App `<your-app-id>` · Model `qwen2.5:14b` (A2) · H100 testing `qwen3.5:35b` / `qwen3:32b` · Embedding `nomic-embed-text-v2-moe`

## Übersicht

| Intent | Status | Präzision | Recall / Scope | Prompt reif? |
|--------|--------|-----------|----------------|-------------|
| `metadata_list` | ✅ stabil | ✅ API-fetched (keine Halluzination) | ✅ 84 Papers, 821 Authors | ✅ stabil (v0.4.12+) |
| `content_summary` | ✅ stabil | ✅ 0 Halluzination (Volltext-verified) | ⚠️ Max 8 Papers (A2-Latenz-Limit) | ✅ stabil |
| `knowledge_retrieval` | ✅ stabil | ✅ Citations korrekt (v0.4.7) | ⚠️ miCLIP/MeRIP fehlen | ✅ stabil (v0.4.7) |
| `author_lookup` | ✅ stabil | ✅ Quotes + Autoren korrekt (v0.4.7) | ~27% (7/26) | ✅ stabil (v0.4.8) |
| `entity_lookup` | ⚠️ Recall-Limit | ✅ sauber (keine Halluzination) | ⚠️ 5/38+ Modifikationen, m6A fehlt | ✅ stabil (v0.4.2) |

### 20 Test Cases – Current Standings (2026-07-27)

| # | Intent | Query | Status | Fixed In |
|---|--------|-------|--------|----------|
| 1 | `metadata_list` | Papers by Christoph Dieterich | ✅ 8 papers | v0.4.6 |
| 2 | `content_summary` | → Summarize them | ✅ Grounded | – |
| 3 | `knowledge_retrieval` | What is m6A? | ✅ citations correct | v0.4.7 |
| 4 | `author_lookup` | Who worked on tRNA? | ✅ quotes + authors correct | v0.4.7 |
| 5 | `entity_lookup` | Which RNA mods most studied? | ⚠️ 5 entities, m6A missing (H100 testing pending) | – |
| 6–9 | `metadata_list` | Tuorto, Ketting, Höbartner, Saunders | ✅ | v0.4.6 |
| 10 | `metadata_list` | Find all research papers | ✅ LLM-native | v0.4.6 |
| 11 | `metadata_list` | List all researchers | ✅ LLM-native | v0.4.6 |
| 12 | `author_lookup` | Who is using HEK cells? | ✅ no speculative claims | v0.4.8 |
| 13 | `content_summary` | Mark Helm → Summarize | ✅ 194s (cap 8 papers) | v0.4.10 |
| 14 | `metadata_list` | Papers by Dieterich (last name) | ✅ 8 papers | v0.4.6 |
| 15 | `content_summary` | Papers by X → Group by journal | ✅ Groups by journal | v0.4.6 |
| 16 | `metadata_list` | PI Collaboration Analysis | ✅ co-author pair frequencies | v0.4.15 |
| 17 | `metadata_list` | Multi-author OR: "Identify: Helm, Hengesbach" | ✅ 39 papers, 14–28s | v0.4.14 |
| 18 | N/A | Hardcoded info for Lauren Saunders | ❌ external KB needed | – |
| 19 | `metadata_list` | Find papers by Tamer Butto | ✅ 2 papers | v0.4.11 |
| 20 | `metadata_list` | Find papers by Michaela Frye | ✅ 1 paper | v0.4.11 |

**Tally: ✅ 19 · ⚠️ 2 · ❌ 1** (v0.4.16)

### Bonus Cases – Author Name Format Normalization (v0.4.9)

| Query | Before (v0.4.8) | After (v0.4.9) |
|-------|-----------------|-----------------|
| `Mark Helm` | `metadata_list` ✅ | `metadata_list` ✅ |
| `Helm, Mark` | `author_lookup` ❌ | `metadata_list` ✅ |
| `M. Helm` | `author_lookup` ❌ | `metadata_list` ✅ |
| `Dieterich` | `content_summary` ❌ | `metadata_list` ✅ |

---

## Priorities & Planned Work

> Historical fixes → `CHANGELOG.md` · Intent deep-dives → [`intent-architecture.md`](intent-architecture.md) · Lessons learned → [`lessons-learned.md`](lessons-learned.md)

| # | Target | Prio | Impact | Effort | Status |
|---|--------|:---:|--------|--------|--------|
| 1 | **H100 Provider Config + 35B Regression** | 🔴 | Behebt #5 (m6A-Recall), verbessert `author_lookup` Recall | 2h | Models gepullt, YAML fehlt |
| 2 | **qwen3-embedding Evaluation** | 🟡 | Bessere Retrieval-Rankings (miCLIP/MeRIP) | 3h | Analog zu bge-m3 Test (v0.4.14) |
| 3 | **#16 Collaboration Analysis** | 🟢 | Co-Author pair frequencies | ✅ Done | ✅ Implemented (v0.4.15) |
| 4 | **Prompt-Tuning: "what else" re-query** | 🟢 | "What else did X publish?" → metadata_list re-query | ✅ Done | ✅ Code-level guard (v0.4.16+), test case #21 |
| 5 | **🔬 Abstract Parent-Child Chunking** | 🔵 | Bessere Retrieval-Rankings durch semantisches Chunking | >2d | Preprocessing-Pipeline nötig |
| – | **Future computation modes** | 🔵 | `publication_timeline`, `journal_distribution`, `author_productivity` | je 2–4h | Nach Collaboration-Pattern |

### 🔴 Priority 1 — H100 LLM Migration (IN PROGRESS, 2026-07-29)

**Goal**: qwen2.5:14b (A2, 16 GB) → larger models on H100 (94 GB) for better quality.

**Infrastructure**: Ollama on `gpu-g5-1:21434`. Models pulled, Dify provider configured per-model.

#### H100 Model Inventory (2026-07-29)

| Model | Size | Thinking? | Ollama Direct | Dify Draft | Dify Runtime | Verdict |
|-------|------|-----------|---------------|------------|-------------|--------|
| `qwen3.5:35b` | 24 GB | ✅ Yes | ✅ 404-763 chars, `finish=stop` | ❌ 300s timeout, 0 chars | ❌ HTTP 400 | **Blocked by Dify** |
| `qwen3:32b` | 20 GB | ✅ Yes | ✅ 1924 chars, `finish=stop` | ⚠️ Once worked, now ❌ | ❌ HTTP 400 | **Blocked by Dify** |
| `qwen3:30b` | 19 GB | ✅ Yes | ❌ `<think>` tags in content | — | — | Thinking model |
| `qwen3:14b` | 9 GB | ✅ Yes | ❌ `<think>` tags in content | — | — | Thinking model |
| `qwen2.5:14b` | 9 GB | ❌ No | ✅ Works | — | — | **Fallback (2.3-3.6× faster)** |

#### Key Findings

1. **Thinking models work via Ollama directly** — both `qwen3.5:35b` and `qwen3:32b` produce clean `message.content` via OpenAI-compatible endpoint with `max_tokens≥4096`. Thinking is internal; content is delivered without `<think>` tags.
2. **Thinking overhead is massive** — the models think about EVERY chunk, EVERY author list, EVERY paper title in the KR context. With 11 chunks (typical m6A query), thinking consumes 2000-8000 tokens before producing output. `max_tokens` must be ≥8192 for KR queries.
3. **Dify blocks thinking models** — both draft and runtime APIs return 0 chars or HTTP 400. Suspected causes: Dify's Ollama provider timeout (<300s), `max_tokens` clamping, or streaming handler incompatibility with thinking model response format.
4. **`enable_thinking: false` is ignored** — Ollama does not respect this parameter for qwen3 models.
5. **`qwen2.5:14b` on H100: 2.3-3.6× faster** than A2 (per `docs/timing.md`). No quality improvement (same model), but significant latency reduction.

#### Test Results (qwen3.5:35b, max_tokens=16384, via Dify Runtime)

| # | Query | Time | Status | Notes |
|---|-------|------|--------|-------|
| 1 | Papers by Christoph Dieterich | 79s | ✅ | 8 papers, 3117 chars |
| 3 | What is m6A? | 243s | ❌ | 642-char fallback |
| 5 | Which RNA mods most studied? | 222s | ❌ | 642-char fallback |
| 16 | Who has collaborated the most? | 62s | ✅ | 3253 pairs, 7248 chars |

> #1 and #16 work because they use Dataset API (no LLM thinking overhead). #3 and #5 fail because the KR Extraction LLM's thinking consumes all tokens before producing output.

#### Next Steps

1. **Debug Dify integration** — find why thinking models are blocked. Check Dify server logs, Ollama provider timeout settings, and `max_tokens` passthrough.
2. **Quality comparison** — once Dify works, test all 20 cases with `qwen3.5:35b` and `qwen3:32b`, focusing on entity recall (#5) and author recall (#4).
3. **Alternative: direct Ollama benchmark** — if Dify remains broken, inject real KR chunks into Ollama API calls and compare output quality between models.
4. **Fallback: `qwen2.5:14b` @ H100** — deploy for latency reduction (2.3-3.6×) while debugging larger models.

### 🟡 Priority 2 — Planned Extensions

- **qwen3-embedding**: ~4× larger than nomic. Test methodology: bge-m3 approach (v0.4.14), full 5-intent regression.
- **#13 Timeout**: ✅ Fixed (v0.4.10, cap 15→8). Caching as optional improvement.

### 🔵 Research — Abstract Parent-Child Chunking

Parent-child indexing with abstract as parent, body paragraphs (`\n\n`) as children. Hypothesis: abstract vector is more precise than full-doc or mechanical split-parent → better retrieval rankings. Challenge: Dify has no semantic parent-splitting — needs preprocessing pipeline (abstract extraction, separate dataset, dual-KR-node architecture). Effort: multiple days. Success probability: medium (embedding upgrade likely higher leverage).

### ❌ No-Fix

- **Externes Author-Wiki** (#18): Lauren Saunders has no papers in dataset. Requires separate infrastructure — orthogonal to paper-centric chatbot.
