# RMAP Chatbot – Feature Roadmap & Analysis

> Stand: 2026-07-31 · v0.4.17 · App `16d50bee-bc86-4bda-bb56-a861743f3ddb` · ⚠️ **BROKEN** (see §Infrastructure Incident)

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

## ⚠️ Infrastructure Incident (2026-07-31)

**Symptom:** Both Draft and Published App unresponsive. Draft API returns only `event: ping` (no node execution). Published API returns `HTTP 401` or hangs. Web UI (`/chat/...`) shows opening statement but no query responses.

**Timeline:**
| Time | Event |
|------|-------|
| 2026-07-29 | H100 migration tested successfully with `qwen3:32b` (draft API, 14/14 tests) |
| 2026-07-30 | `qwen3:32b` regression tests complete; results documented in `docs/timing.md`, `docs/test-cases.md` |
| 2026-07-30 | New dataset indexing started on `gpu-g5-1` (H100) — still running on 2026-07-31 |
| 2026-07-31 | Published app stopped responding; debug reveals first LLM node hangs (no output) |
| 2026-07-31 | `sync_draft()` bug found: `opening_statement` read from `app.features` instead of `workflow.features` → fixed |
| 2026-07-31 | After fix: Published app works via runtime API, but Draft API hangs |
| 2026-07-31 | **Hypothesis:** GPU contention from long-running embedding indexing on `gpu-g5-1` may be causing internal Dify/Ollama communication issues, affecting `app01.internal` indirectly |

**Root Cause Hypothesis:** A new dataset indexing job on `gpu-g5-1` (H100) has been running since 2026-07-30. If the GPU is saturated, it may cause:
1. Ollama on `gpu-g5-1` to become unresponsive → Dify's model provider hangs
2. Dify's internal state to degrade (database locks, queue overflow)
3. Cross-contamination: `app01.internal` (A2) may be affected if Dify's worker pool is blocked waiting for H100 requests

**Immediate Actions:**
1. 🔲 Delete the new (incomplete) dataset from Dify UI
2. 🔲 Shutdown Ollama on `gpu-g5-1` (`ollama stop` or kill Slurm job)
3. 🔲 Verify `app01.internal` (A2) Ollama is responsive independently
4. 🔲 Test Published App with A2 config → should work if GPU contention was the cause
5. 🔲 Test Draft with A2 config

### 🆕 Planned: Separate Apps for A2 and H100

**Problem:** Using a single Dify app for both A2 and H100 configs causes interference — draft/publish operations overwrite each other, and model endpoint configurations are shared.

**Solution:** Create two separate Dify apps:

| App | Branch | Model | Ollama | Purpose |
|-----|--------|-------|--------|---------|
| RMAP Chatbot (A2) | `master` | `qwen2.5:14b` | `app01.internal:21434` | Production, stable |
| RMAP Chatbot (H100) | `h100-migration` | `qwen3:32b` | `gpu-g5-1:21434` | Development, H100 testing |

**Benefits:**
- No draft/publish interference between configs
- Independent env vars, API keys, dataset bindings
- Can test H100 without affecting production users
- Clear separation of concerns

**Steps:**
1. 🔲 Export published A2 config as baseline
2. 🔲 Create new Dify app "RMAP Chatbot H100" via Dify UI
3. 🔲 Import H100 config into new app
4. 🔲 Configure H100 app with its own dataset binding and env vars
5. 🔲 Update scripts to support `--app-id` for both apps
6. 🔲 Update documentation

---

## Priorities & Planned Work

> Historical fixes → `CHANGELOG.md` · Intent deep-dives → [`intent-architecture.md`](intent-architecture.md) · Lessons learned → [`lessons-learned.md`](lessons-learned.md)

| # | Target | Prio | Impact | Effort | Status |
|---|--------|:---:|--------|--------|--------|
| 🔥 | **Infrastructure Recovery** | 🔴 | App unresponsive — production down | ? | ⚠️ In Progress (see §Infrastructure Incident) |
| 1 | **H100 LLM Migration: qwen3:32b** | 🔴 | Behebt #5 (m6A-Recall), bessere Qualität | ✅ Done | ⚠️ Blocked by infra incident |
| 🆕 | **Separate A2/H100 Apps** | 🔴 | Eliminiert Config-Interferenz | 2h | 🔲 Planned (see §Separate Apps) |
| 2 | **qwen3-embedding Evaluation** | 🟡 | Bessere Retrieval-Rankings (miCLIP/MeRIP) | 3h | 🔲 After infra recovery |
| 3 | **#16 Collaboration Analysis** | 🟢 | Co-Author pair frequencies | ✅ Done | ✅ Implemented (v0.4.15) |
| 4 | **Prompt-Tuning: "what else" re-query** | 🟢 | "What else did X publish?" → metadata_list re-query | ✅ Done | ✅ Code-level guard (v0.4.16+), test case #21 |
| 5 | **🔬 Abstract Parent-Child Chunking** | 🔵 | Bessere Retrieval-Rankings durch semantisches Chunking | >2d | Preprocessing-Pipeline nötig |
| – | **Future computation modes** | 🔵 | `publication_timeline`, `journal_distribution`, `author_productivity` | je 2–4h | Nach Collaboration-Pattern |

### 🔴 Priority 1 — H100 LLM Migration ✅ DONE (2026-07-30)

**Result**: `qwen3:32b` deployed on H100 (`gpu-g5-1:21434`), `max_tokens=8192`. All 14 single-turn regression cases pass. Full documentation in `docs/timing.md` and `docs/test-cases.md`.

#### H100 Model Comparison

| Model | Size | Deployed? | 14-Case Regression | Verdict |
|-------|------|-----------|-------------------|--------|
| **`qwen3:32b`** | 20 GB | ✅ Production | ✅ 14/14 (1.5× faster than A2) | **Selected** |
| `qwen3.5:35b` | 24 GB | ❌ | N/A (thinking too verbose, GPU instability) | Deferred |
| `qwen2.5:14b` | 9 GB | — (A2) | Baseline | Fallback |

#### Key Wins over qwen2.5:14b (A2)

1. **#5 entity_lookup fixed**: 10 entities with m6A (was 5, m6A missing) — our oldest open bug
2. **1.5× faster**: 48s avg vs 73s (H100 eliminates A2 bottleneck)
3. **Better answer structure**: Sections, full author lists (no "et al."), real citations
4. **Thinking models work in Dify**: `qwen3:32b` thinking stays within 8K budget (800-1,300 tokens typical)

#### qwen3.5:35b — Deferred

Thinking too verbose for context-heavy prompts (100% of 4K tokens consumed on thinking). With 50K tokens, estimated 90-120s per query (3-5× slower than qwen3:32b). Will re-evaluate after qwen3-embedding if embedding upgrade changes retrieval profile.

### 🟡 Priority 2 — Planned Extensions

- **qwen3-embedding**: ~4× larger than nomic. Test methodology: bge-m3 approach (v0.4.14), full 5-intent regression.
- **#13 Timeout**: ✅ Fixed (v0.4.10, cap 15→8). Caching as optional improvement.

### 🔵 Research — Abstract Parent-Child Chunking

Parent-child indexing with abstract as parent, body paragraphs (`\n\n`) as children. Hypothesis: abstract vector is more precise than full-doc or mechanical split-parent → better retrieval rankings. Challenge: Dify has no semantic parent-splitting — needs preprocessing pipeline (abstract extraction, separate dataset, dual-KR-node architecture). Effort: multiple days. Success probability: medium (embedding upgrade likely higher leverage).

### ❌ No-Fix

- **Externes Author-Wiki** (#18): Lauren Saunders has no papers in dataset. Requires separate infrastructure — orthogonal to paper-centric chatbot.
