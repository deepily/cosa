# COSA Development History

> **🔍 CURRENT**: 2025.12.02 - Parent Lupin Sync: Code Similarity Visualization + Duplicate Snapshot Bug Fixes! Synced 3 files from parent Lupin Sessions 16-17. **PHASE 1 - CODE SIMILARITY SEARCH**: Replaced stub `get_snapshots_by_code_similarity()` with real LanceDB vector search on `code_embedding` field, added new `get_snapshots_by_solution_similarity()` method for `solution_embedding` field (+200 lines in lancedb_solution_manager.py). **PHASE 2 - API ENDPOINTS**: Added 3 Pydantic models (`CodeSimilarityResult`, `SimilarSnapshotsResponse`, `SnapshotPreviewResponse`) and 2 endpoints (`/admin/snapshots/{id_hash}/preview`, `/admin/snapshots/{id_hash}/similar`). **DUPLICATE BUG FIX 1 - TOCTOU RACE**: Added `threading.Lock` around `save_snapshot()` critical section to prevent concurrent calls from both passing cache/DB checks. **DUPLICATE BUG FIX 2 - ID HASH PRESERVATION**: Added `snapshot.id_hash = existing_id_hash` in `_update_existing_snapshot()` so `merge_insert` matches existing record. **GIST GENERATION FIX**: `running_fifo_queue.py` called uninitialized `self.normalizer`; fixed by importing/initializing `GistNormalizer`, plus added gist generation to `_handle_base_agent()` for new jobs. **Total Impact**: 3 files, +513 insertions/-81 deletions (net +432 lines). 🔍💻🐛✅

> **🔥 PREVIOUS**: 2025.12.01 - Parent Lupin Sync: Synonym Signal Loss ROOT CAUSE FOUND + FIXED! Synced 9 files from parent Lupin Sessions 13-15. **ROOT CAUSE**: `agent_base.py:129` was calling DEPRECATED `SolutionSnapshot.remove_non_alphanumerics()` which strips ALL punctuation including apostrophes and math operators ("What's 4 + 4?" → "whats 4 4"). **FIX APPLIED**: Changed to `self.question = question` (store verbatim). **DEPRECATION NUKE**: Made `remove_non_alphanumerics()` SCREAM its deprecation with ASCII box, fire emojis, stack trace (limit=5), and 40 fire emojis. **STT-FRIENDLY CONTRACTIONS**: Added 24 apostrophe-less variants to Normalizer ("whats"→"what is", "dont"→"do not", etc.). **ADMIN IMPROVEMENTS**: Added threshold query param, descending sort, synonym debug logging. **DUPE-GUARD**: DB fallback for cache desync in save_snapshot() and delete_snapshot(). **SIMILARITY DEBUG**: Verbose logging for vector search (query embedding, raw results, top 10, threshold filtering). **JOB-TRACE**: Added job processing logging for duplicate investigation. **Total Impact**: 9 files, +221/-66 lines (net +155 lines). ✅ Synonym signal loss fixed! 🔥🐛✅

> **Previous Achievement**: 2025.11.30 - Parent Lupin Sync: LanceDB Part 6 Complete + Config-Driven Design! Synced 6 files from parent Lupin Session 12. Import fix, config-driven design, vector search implementation, adaptive retry logic, tokenization approach. Total Impact: 6 files, +325/-146 lines. ✅ LanceDB Part 6 Complete! 🔧✅

> **Previous Achievement**: 2025.11.26 - Parent Lupin Sync: Snapshot ID Hash Collision Bug Fix + Diagnostic Cleanup! Synced critical bug fix from parent Lupin session. **ROOT CAUSE IDENTIFIED**: Classic Python mutable default argument bug in `solution_snapshot.py:161` where `run_date: str=get_timestamp()` was evaluated ONCE at module load time instead of per-instantiation. All snapshots created without explicit `run_date` shared the SAME frozen timestamp, generating IDENTICAL SHA256 `id_hash` values. This caused "sqrt(122)" to find existing record with that hash (sqrt(100)), add "sqrt(122)" synonym to wrong snapshot, returning "10" instead of ~11.045. **FIX**: Changed default parameters from function calls to `None` (line 161), then call `self.get_timestamp()` (with `microseconds=True` for run_date) in function body when values are None (lines 257-259). **DIAGNOSTIC CLEANUP**: Removed ~200 lines of verbose diagnostic logging from investigation phase across 4 files. **LanceDB Query Fix**: Previous session's pandas filtering fix for exact match queries (3 methods). **Method Rename**: `add_snapshot()` → `save_snapshot()` for semantic clarity. **Total Impact**: 8 files, +151/-185 lines (net -34 lines). ✅ Hash collision bug fixed! 🐛✅🧹

> **Previous Achievement**: 2025.11.25 - Parent Lupin Sync: LanceDB Query Fix + Method Rename + Dependency Injection! Synced 6 files from parent Lupin Session 10 with critical bug fixes and architectural improvements. **LanceDB Query Pattern Bug Fix**: Fixed critical bug where exact match lookups returned WRONG snapshots (e.g., "What's the square root of 144?" returned "What's 2+2?" answer). Root cause: LanceDB's `table.search().where(filter)` without a vector query returns **arbitrary rows**, not filtered results. Fixed all three `find_exact_*` methods in canonical_synonyms_table.py to use pandas filtering instead. **Method Rename**: `add_snapshot()` → `save_snapshot()` across 4 files (22 call sites) for semantic clarity - the method is actually an upsert (INSERT or UPDATE), not just "add". **Stale Stats Fix**: FastAPI dependency injection pattern - added `get_snapshot_manager()` dependency function that retrieves global singleton from `fastapi_app.main` module, ensuring cache consistency between math agent writes and admin reads. **Admin API Enhancement**: Added `synonymous_questions` and `synonymous_question_gists` fields to SnapshotDetailResponse. **Total Impact**: 6 files, +108 insertions/-143 deletions (net -35 lines). ✅ All Session 10 fixes synced! 🐛🔧

> **Previous Achievement**: 2025.11.24 - Parent Lupin Sync: Math Agent Debugging + Admin Snapshots API + LanceDB Optimizations! Synced 10 files from parent Lupin repository with improvements from 4 math agent debugging sessions (Sessions 5-9). **Math Agent Enhancements**: Added static `apply_formatting()` method enabling SolutionSnapshot replay to use same formatting logic as original agent execution, preventing formatter hallucination in terse mode. **Gist Caching System**: NEW `GistCacheTable` class (536 lines) providing LanceDB-backed persistent cache for LLM-generated gists (~500ms savings per cache hit, 70-80% expected hit rate). **LanceDB Optimizations**: Added scalar index on id_hash for merge_insert performance, pre-merge cache invalidation, fresh DB read after merge, comprehensive stats debugging. **Total Impact**: 11 files (10 modified, 1 created), +423 insertions/-127 deletions (net +296 lines). ✅ Math agent cache hit formatting now consistent with original execution! 🧮🔧

> **Previous Achievement**: 2025.11.20 - Parent Lupin Sync: Test Infrastructure & Code Quality Improvements! Synced 7 files from parent Lupin repository with improvements from 100% Test Adherence achievement (2025.11.20). **Configuration Manager**: Enhanced docstrings with Testing/Notes sections documenting atomic `_reset_singleton=True` pattern for test isolation. **Normalizer**: Added MATH_OPERATORS preservation ({+, -, *, /, =, >, <} etc.) for mathematical query support. **Solution Snapshot**: Improved question handling (verbatim storage + normalized indexing), fixed field mapping bug (code_returns → code). **Total Impact**: 7 files modified, +95 insertions/-29 deletions (net +66 lines). ✅ Improved test reliability and error diagnostics! 🔧✨

> **Previous Achievement**: 2025.11.19 - PostgreSQL Repository Migration (Phase 2.6.3) COMPLETE! Migrated 8 COSA service layer files from direct SQLite database calls to PostgreSQL repository pattern. **Services Migrated**: email_token_service.py, rate_limiter.py, api_key_auth.py middleware, refresh_token_service.py. **Timezone Modernization**: All datetime operations migrated from `datetime.utcnow()` → `datetime.now(timezone.utc)` (Python 3.12+ best practice). **Total Impact**: 8 files modified, +186 insertions/-291 deletions (net -105 lines). ✅ Ready for integration testing! 🐘🔄

> **Previous Achievement**: 2025.11.18 - LanceDB GCS Multi-Backend Testing & Normalization Fix COMPLETE! Test-driven development approach (Option B) achieved 100% test pass rate across all backends. **Critical Bug Fixed**: Normalization mismatch between insert/query operations (50%→100% pass rate). Root cause: `SolutionSnapshot.__init__()` used deprecated `remove_non_alphanumerics()` vs `Normalizer.normalize()` in queries. **Final Results**: Local backend 3/3 PASS, GCS backend 3/3 PASS, unit tests 11/11 PASS. 🎯✅

> **Previous Achievement**: 2025.11.13 - LanceDB Multi-Backend Storage Infrastructure COMPLETE! Implemented factory pattern for LanceDB solution manager enabling seamless switching between local filesystem (development) and Google Cloud Storage (test/production deployment). Ready for Cloud Run test deployment with GCS backend! 🏗️✅

> **Previous Achievement**: 2025.11.11 - Phase 2.5.4 Config Migration COMPLETE! Renamed `~/.lupin/config` → `~/.notifications/config` and `target_user` → `global_notification_recipient`. Dual support for backward compatibility implemented. 🔄✅

> **Previous Achievement**: 2025.11.10 - Phase 2.5.4 API Key Authentication Infrastructure COMPLETE! Header-based API key authentication (X-API-Key header) implemented. Fixed critical schema bug (api_keys.user_id INTEGER→TEXT). Integration testing infrastructure created (10 tests).

> **Previous Achievement**: 2025.11.08 - Notification System Phase 2.3 CLI Modernization COMMITTED! Split async/sync notification clients with Pydantic validation (1,376 lines across 3 new files).

---

## 2025.12.02 - Parent Lupin Sync: Code Similarity Visualization + Duplicate Snapshot Bug Fixes

### Summary
Synced 3 files from parent Lupin Sessions 16-17 (2025.12.02). Major feature: full code similarity visualization for admin snapshots dashboard. Critical bug fixes: duplicate snapshot creation (TOCTOU race + id_hash preservation) and code_gist generation (uninitialized normalizer + missing generation location).

### Work Performed

#### Code Similarity Search Backend - COMPLETE ✅
**File**: `memory/lancedb_solution_manager.py` (+258/-81 lines, net +177 lines)

**Phase 1 - Replace Stub with Real Vector Search**:
- Replaced placeholder `get_snapshots_by_code_similarity()` with real LanceDB vector search on `code_embedding` field
- NEW `get_snapshots_by_solution_similarity()` method for `solution_embedding` field searches
- Both methods: validate embeddings, perform vector search with `.metric("dot").nprobes()`, convert distance to similarity percentage, filter by threshold, exclude self

**Distance-to-Similarity Formula**:
```python
# With dot metric: _distance = 1 - dot_product (lower = more similar)
distance = record.get( "_distance", 0.0 )
similarity_percent = ( 1.0 - distance ) * 100
```

#### Duplicate Snapshot Bug Fixes - COMPLETE ✅
**File**: `memory/lancedb_solution_manager.py`

**BUG 1 - TOCTOU Race Condition**:
- **Problem**: Two concurrent `save_snapshot()` calls for same question could both pass cache/DB checks before either INSERT commits
- **Fix**: Added `from threading import Lock`, class-level `_save_lock = Lock()`, wrapped critical section with `with self._save_lock:`
- **Pattern**: Follows existing codebase (EmbeddingManager, Normalizer, GistNormalizer all use `_lock = Lock()`)

**BUG 2 - id_hash NOT Preserved on Update**:
- **Problem**: New snapshot has its OWN id_hash (generated from creation timestamp), but `merge_insert("id_hash")` expects matching hash. Mismatch causes INSERT instead of UPDATE!
- **Fix**: Added `snapshot.id_hash = existing_id_hash` in `_update_existing_snapshot()` before calling `_full_replace_snapshot()`

**Concurrent Save Test**:
```python
# Added to quick_smoke_test(): Pre-creates 3 snapshots, launches threads, verifies only 1 record
concurrent_snapshots = [SolutionSnapshot(...) for _ in range(3)]
threads = [threading.Thread(target=threaded_save, args=(s,)) for s in concurrent_snapshots]
# Verify: len(matching) == 1
```

#### Admin API Endpoints - COMPLETE ✅
**File**: `rest/routers/admin.py` (+229 lines)

**New Pydantic Models**:
- `CodeSimilarityResult`: Individual result (id_hash, question_preview, code_gist, similarity, created_date)
- `SimilarSnapshotsResponse`: Two lists (code_similar, explanation_similar) with counts
- `SnapshotPreviewResponse`: Preview data for hover tooltips (code_preview, code_gist)

**New Endpoints**:
1. `GET /admin/snapshots/{id_hash}/preview` - Returns first 300 chars of code + code_gist for hover preview
2. `GET /admin/snapshots/{id_hash}/similar` - Vector similarity search returning code-similar and explanation-similar snapshots

**Detail Modal Enhancements**:
- Added `solution_summary` and `code_gist` fields to `SnapshotDetailResponse`

#### Gist Generation Fix - COMPLETE ✅
**File**: `rest/running_fifo_queue.py` (+26/-10 lines, net +16 lines)

**BUG - Uninitialized Normalizer**:
- **Problem**: Code called `self.normalizer.process_text()` but `self.normalizer` was NEVER INITIALIZED
- **Fix**: Import `GistNormalizer`, initialize `self.gist_normalizer` in `__init__`, use `self.gist_normalizer.get_normalized_gist()`

**BUG - Missing Generation Location**:
- **Problem**: `code_gist` only generated in `_handle_solution_snapshot()` (cached path) but NOT in `_handle_base_agent()` (new jobs)
- **Fix**: Added gist generation block to `_handle_base_agent()` after speech emitted but before `update_runtime_stats()`

**Cache Hit Tuple Unpack**:
- Fixed unpacking: `score, cached_snapshot = cached_snapshots[0]` (was missing score)

### Files Modified

**COSA Repository** (3 files):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `memory/lancedb_solution_manager.py` | +258/-81 | Code/solution similarity search, TOCTOU lock, id_hash preservation, concurrent test |
| `rest/routers/admin.py` | +229/-0 | 3 Pydantic models, 2 endpoints, 2 detail fields |
| `rest/running_fifo_queue.py` | +26/-10 | GistNormalizer init, gist generation in new jobs path, tuple unpack fix |

**Total Impact**: 3 files, +513 insertions/-81 deletions (net +432 lines)

### Integration with Parent Lupin

**Parent Session Context** (2025.12.02, Sessions 16-17):
- Session 16: Duplicate snapshot bug investigation - found TOCTOU race + id_hash mismatch root causes
- Session 17: Code similarity visualization feature complete - 4 phases (backend, API, hover preview, drill-down modal)

**Frontend Changes** (in parent Lupin only, not COSA):
- Hover preview icons (📝 💻) on search results
- Similarity modal with two-column layout
- Click-to-view detail items

### Current Status

- **Code Similarity Search**: ✅ IMPLEMENTED - Real LanceDB vector search on code_embedding
- **Solution Similarity Search**: ✅ IMPLEMENTED - New method for solution_embedding
- **TOCTOU Race Fix**: ✅ COMPLETE - Thread lock prevents concurrent duplicate inserts
- **ID Hash Preservation**: ✅ COMPLETE - Updates use original id_hash for merge_insert match
- **Gist Generation**: ✅ FIXED - Initialized normalizer, added new jobs path generation
- **Preview/Similar Endpoints**: ✅ COMPLETE - Admin can explore code similarity

### Testing Performed

1. Concurrent save protection test added to `quick_smoke_test()`
2. Both sequential and concurrent tests pass
3. Preview endpoint returns code + gist
4. Similar endpoint returns code and explanation matches

---

## 2025.12.01 - Parent Lupin Sync: Synonym Signal Loss ROOT CAUSE FOUND + FIXED

### Summary
Synced 9 files from parent Lupin Sessions 13-15 (2025.12.01). Major breakthrough: finally traced the source of question corruption ("What's 4 + 4?" → "whats 4 4") to deprecated `remove_non_alphanumerics()` method being called in `agent_base.py:129`. Fixed by storing questions verbatim, added screaming deprecation warnings, and enhanced debugging throughout.

### Work Performed

#### Synonym Signal Loss Root Cause - FIXED ✅
**File**: `agents/agent_base.py` (+1/-1 lines)

**Problem**: Questions like "What's 4 + 4?" were being corrupted to "whats 4 4" before storage, losing apostrophes and math operators.

**Root Cause**: Line 129 was calling `ss.SolutionSnapshot.remove_non_alphanumerics( question )` which uses regex `[^a-zA-Z0-9 ]` to strip ALL punctuation.

**Fix**: Changed to store question verbatim:
```python
# BEFORE (broken - strips math operators!)
self.question = ss.SolutionSnapshot.remove_non_alphanumerics( question )

# AFTER (correct - preserve verbatim)
self.question = question  # Store verbatim - DO NOT normalize here!
```

#### Deprecation Warning Enhancement - COMPLETE ✅
**File**: `memory/solution_snapshot.py` (+40/-24 lines)

**Changes**: Made `remove_non_alphanumerics()` SCREAM its deprecation:
- Massive ASCII box docstring explaining the destruction
- Console output with 🔥 fire emojis and warning banners
- Display of input text being corrupted
- Stack trace (limit=5) to identify caller
- 40 fire emojis at the end
- Still executes for backward compatibility, but caller WILL notice

#### STT-Friendly Contractions - COMPLETE ✅
**File**: `memory/normalizer.py` (+27/-1 lines)

**Addition**: Added 24 apostrophe-less contractions common in speech-to-text output:
- "whats"→"what is", "thats"→"that is", "theres"→"there is"
- "dont"→"do not", "wont"→"will not", "cant"→"cannot"
- "youre"→"you are", "theyre"→"they are"
- "youve"→"you have", "theyve"→"they have"
- And 14 more variants

**Omitted**: Ambiguous ones (im, id, its, hell, shell, well, were) that could be valid words.

#### Admin Search Improvements - COMPLETE ✅
**File**: `rest/routers/admin.py` (+25/-1 lines)

**Changes**:
1. **Threshold Query Param**: Now accepts `threshold` parameter (0-100, default 80) for flexible search
2. **Descending Sort**: Added explicit `search_results.sort( key=lambda x: x.score, reverse=True )`
3. **Synonym Debug Logging**: Shows ID, question, and all synonyms with scores for each result:
   ```
   [ADMIN-SEARCH] ID: abc12345, Score: 85.2%
     Question: What's 2 + 2?
     Synonyms (3):
       - 'whats 2 plus 2' (92.1%)
       - 'what is two plus two' (88.4%)
   ```

#### DUPE-GUARD: DB Fallback for Cache Desync - COMPLETE ✅
**File**: `memory/lancedb_solution_manager.py` (+150/-8 lines)

**Problem**: Cache could become stale during race conditions, causing duplicate inserts or failed deletes.

**Solution**: Added DB fallback checks when cache misses:
1. **save_snapshot()**: If cache miss, check DB directly before INSERT to prevent duplicates
2. **delete_snapshot()**: If cache miss, check DB directly before failing
3. NEW `_check_db_for_question()` method for direct DB lookups

**Similarity Debug Logging**: Added verbose output for vector search debugging:
- Query embedding validation (checks for all-zeros)
- Raw search results count
- Top 10 results with pass/fail indicators
- Threshold filtering summary

#### Minor Enhancements - COMPLETE ✅

| File | Changes | Description |
|------|---------|-------------|
| `memory/embedding_manager.py` | +2/-3 | Debug output showing original vs normalized text |
| `memory/canonical_synonyms_table.py` | +1 | Minor whitespace cleanup |
| `rest/running_fifo_queue.py` | +8/-4 | JOB-TRACE logging for duplicate investigation |
| `rest/todo_fifo_queue.py` | +2/-2 | Variable alignment cleanup |

### Files Modified

**COSA Repository** (9 files):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `agents/agent_base.py` | +1/-1 | Store question verbatim (ROOT CAUSE FIX) |
| `memory/solution_snapshot.py` | +40/-24 | Screaming deprecation warning |
| `memory/normalizer.py` | +27/-1 | 24 STT-friendly contractions |
| `memory/lancedb_solution_manager.py` | +150/-8 | DUPE-GUARD + similarity debug |
| `rest/routers/admin.py` | +25/-1 | Threshold param + sort + debug |
| `memory/embedding_manager.py` | +2/-3 | Debug output enhancement |
| `memory/canonical_synonyms_table.py` | +1 | Whitespace cleanup |
| `rest/running_fifo_queue.py` | +8/-4 | JOB-TRACE logging |
| `rest/todo_fifo_queue.py` | +2/-2 | Variable alignment |

**Total Impact**: 9 files, +221 insertions/-66 deletions (net +155 lines)

### Integration with Parent Lupin

**Parent Session Context** (2025.12.01, Sessions 13-15):
- Session 13: UI polish + synonym signal loss investigation + STT contractions
- Session 14: ESC key handler for admin modal
- Session 15: ROOT CAUSE FOUND + FIXED + deprecation nuke

**Why Gist Was Correct**: The gist goes through `gist_normalizer.get_normalized_gist()` which properly expands contractions and preserves operators - that's why synonym gist showed "what is 4 + 4" while question showed corrupted "whats 4 4".

### Current Status

- **Root Cause**: ✅ FIXED - agent_base.py now stores verbatim
- **Deprecation Warning**: ✅ IMPLEMENTED - Impossible to miss
- **STT Contractions**: ✅ ADDED - 24 variants in Normalizer
- **Admin Search**: ✅ ENHANCED - Threshold param + sort + debug
- **DUPE-GUARD**: ✅ IMPLEMENTED - DB fallback prevents duplicates
- **Similarity Debug**: ✅ ADDED - Comprehensive vector search logging

### Testing Required

1. Delete LanceDB database to clear corrupted data
2. Restart server
3. Test "What's 4 + 4?" via voice → should store verbatim
4. Verify synonyms show correctly in admin detail view
5. Confirm no duplicate snapshots created

---

## 2025.11.30 - Parent Lupin Sync: LanceDB Part 6 Complete + Config-Driven Design

### Summary
Synced 6 files from parent Lupin Session 12 (2025.11.30). Major theme: config-driven design improvements. Fixed ConfigurationManager import bug, implemented proper LanceDB vector similarity search, added adaptive retry logic for notifications, and rewrote multimodal text processing with tokenization approach.

### Work Performed

#### ConfigurationManager Import Fix - COMPLETE ✅
**File**: `rest/routers/admin.py` (+9/-2 lines)

**Problem**: ModuleNotFoundError when accessing admin endpoints - wrong import path.

**Fix**: Changed import from `cosa.app` to `cosa.config`:
```python
from cosa.config.configuration_manager import ConfigurationManager
```

Added module-level config manager for threshold access with config-driven values:
- `threshold = _config_mgr.get( "similarity_threshold_admin_search", default=80.0 )`
- `debug = _config_mgr.get( "app_debug", default=False )`

#### LanceDB Vector Search Implementation - COMPLETE ✅
**File**: `memory/lancedb_solution_manager.py` (+87/-87 lines, net 0)

**Problem**: Level 4 similarity search used placeholder text-based similarity (`_calculate_text_similarity()`) instead of actual vector search.

**Fix**: Implemented proper LanceDB vector similarity search:
- Added `QuestionEmbeddingsTable` import for embedding generation
- Initialize `self._question_embeddings_tbl` and `self._nprobes` in constructor
- Level 4 now generates query embedding via `_question_embeddings_tbl.get_embedding()`
- Performs actual vector search: `self._table.search( query_embedding, vector_column_name="question_embedding" ).metric( "dot" ).nprobes( self._nprobes )`
- Removed obsolete `_calculate_text_similarity()` method (22 lines deleted)

**Threshold Changes**:
- `threshold_question` default: 100.0 → 90.0 (sensible fallback)
- `threshold_gist` default: 100.0 → 90.0

#### Solution Manager Factory Config - COMPLETE ✅
**File**: `memory/solution_manager_factory.py` (+2/-1 lines)

**Changes**:
- `storage_backend` default: `"local"` → `"development"` (config-driven naming)
- Added `nprobes` to config dict: `config_mgr.get( "solution snapshots lancedb nprobes", default=20, return_type="int" )`

#### Normalizer Verbose Output Cleanup - COMPLETE ✅
**File**: `memory/normalizer.py` (+2/-2 lines)

**Changes**: Replaced `du.print_banner()` with simple `print()` for verbose output:
```python
# BEFORE
if self.verbose: du.print_banner( f"Normalizing: {text[:50]}..." )

# AFTER
if self.debug and self.verbose: print( f"Normalizing: {text[:50]}..." )
```

#### Notification Retry Logic - COMPLETE ✅
**File**: `cli/notify_user_async.py` (+122/-69 lines, net +53)

**New Feature**: Adaptive retry intervals for WebSocket auth timing (Phase 2.7).

**Implementation**:
- NEW `calculate_retry_intervals()` function (49 lines) with Design by Contract docstring
- Short timeouts (≤10s): Aggressive linear retries `[1, 1, 2, 2, 3]` to catch WebSocket auth window
- Long timeouts (>10s): Exponential backoff with 5s cap `[1, 2, 4, 5, 5, 5...]`
- Retry loop wrapping HTTP requests with attempt tracking and debug output
- Only retries on `user_not_available` status, fails fast on network/HTTP errors

#### Multimodal Tokenization Approach - COMPLETE ✅
**File**: `rest/multimodal_munger.py` (+103/-37 lines, net +66)

**Problem**: Previous regex-based punctuation replacement failed at sentence boundaries.
- `" five "` pattern couldn't match "five?" at end of sentence
- `" five "` pattern couldn't match "Five" at start of sentence

**Solution**: Tokenization approach with case preservation:
```python
"What's five plus five?" → ["What's", " ", "five", " ", "plus", " ", "five", "?"]
                        → ["What's", " ", "5",    " ", "+",    " ", "5",    "?"]
                        → "What's 5 + 5?"
```

**Implementation**:
- NEW `_tokenize()` method (25 lines) with Design by Contract docstring
- Rewritten `munge_text_punctuation()` using tokenization
- Build case-insensitive lookup dictionaries from .map files
- Replace tokens by checking lowercase, keep original case when no match
- Preserved OLD APPROACHES in comments for rollback reference

### Files Modified

**COSA Repository** (6 files):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `cli/notify_user_async.py` | +122/-69 | Adaptive retry intervals for WebSocket auth |
| `memory/lancedb_solution_manager.py` | +87/-87 | Proper vector search, threshold defaults |
| `memory/normalizer.py` | +2/-2 | Verbose output cleanup (print_banner → print) |
| `memory/solution_manager_factory.py` | +2/-1 | nprobes config, storage_backend default |
| `rest/multimodal_munger.py` | +103/-37 | Tokenization approach for punctuation |
| `rest/routers/admin.py` | +9/-2 | Import fix, config-driven threshold+debug |

**Total Impact**: 6 files, +325 insertions/-146 deletions (net +179 lines)

### Threshold Separation Summary

| Context | Threshold | Rationale |
|---------|-----------|-----------|
| Queue (user queries) | 95% | Precision-focused for direct answers |
| Admin search | 80% | Recall-focused for discovery/exploration |
| Function defaults | 90% | Sensible fallback when not specified |

### Current Status

- **Import Fix**: ✅ COMPLETE - ConfigurationManager path corrected
- **Vector Search**: ✅ IMPLEMENTED - Proper LanceDB similarity search
- **Config-Driven**: ✅ IMPLEMENTED - Thresholds, debug, storage_backend from config
- **Retry Logic**: ✅ COMPLETE - Adaptive intervals for WebSocket timing
- **Tokenization**: ✅ COMPLETE - Reliable word-level replacement

### LanceDB Upgrade Status

All 6 parts complete:
1. ✅ Backend infrastructure
2. ✅ Match % UI display
3. ✅ STT + Ctrl+R integration
4. ✅ nprobes warning fix
5. ✅ Admin threshold separation
6. ✅ Import fix + config-driven design

---

## 2025.11.26 - Parent Lupin Sync: Snapshot ID Hash Collision Bug Fix + Diagnostic Cleanup COMPLETE

### Summary
Synced critical bug fix and diagnostic cleanup from parent Lupin session. Root cause of wrong math agent answers finally identified: Python's mutable default argument anti-pattern causing all snapshots to share identical timestamps and thus identical SHA256 `id_hash` values.

### Work Performed

#### Snapshot ID Hash Collision Bug Fix - COMPLETE ✅
**File**: `memory/solution_snapshot.py` (+19/-11 lines)

**The Bug**: All snapshots created without explicit `run_date` parameter shared the SAME frozen timestamp ("2025-11-26 @ 08:30:00 PST"), generating IDENTICAL SHA256 `id_hash` values. When "sqrt(122)" was saved, it found existing record with that hash (sqrt(100)), added "sqrt(122)" synonym to wrong snapshot, causing future queries to return "10" instead of ~11.045.

**Root Cause**: Classic Python mutable default argument bug at line 161:
```python
# BEFORE (broken - evaluated ONCE at module load)
def __init__( self, ..., run_date: str=get_timestamp(), ... ):

# AFTER (correct - evaluated per call)
def __init__( self, ..., run_date: str=None, ... ):
    self.run_date = run_date if run_date else self.get_timestamp( microseconds=True )
```

**Fix Applied**:
- Changed `created_date`, `updated_date`, `run_date` defaults from function calls to `None`
- Added conditional assignment in function body (lines 257-259)
- Added `microseconds=True` for `run_date` to ensure uniqueness even for rapid succession calls
- Added explanatory comment documenting the bug for future developers

#### Diagnostic Logging Cleanup - COMPLETE ✅
Removed ~200 lines of verbose diagnostic logging added during investigation phase:

| File | Lines Removed | What Was Removed |
|------|---------------|------------------|
| `rest/todo_fifo_queue.py` | -14 | Query entry block diagnostics |
| `memory/lancedb_solution_manager.py` | -78 | Hierarchical search logging (Levels 1-4) |
| `memory/canonical_synonyms_table.py` | -54 | Synonym audit logging + `_get_synonyms_for_snapshot()` helper |
| `memory/solution_snapshot.py` | -33 | State mutation tracking |

**Retained**: Core debug logging guarded by `if self.debug:` conditions (non-verbose).

#### Previous Session Fixes (Still in Diff) - COMPLETE ✅
- **LanceDB Query Fix**: Pandas filtering for exact match queries (3 methods in canonical_synonyms_table.py)
- **Method Rename**: `add_snapshot()` → `save_snapshot()` for semantic clarity
- **Cache Lookup Fix**: Use verbatim questions for cache lookup (matching delete_snapshot behavior)

### Files Modified

**COSA Repository** (8 files):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `memory/solution_snapshot.py` | +19/-11 | ID hash collision fix (None defaults + microseconds) |
| `memory/canonical_synonyms_table.py` | +32/-30 | LanceDB query fix + diagnostic cleanup |
| `memory/lancedb_solution_manager.py` | +32/-32 | Method rename + cache fix + diagnostic cleanup |
| `memory/snapshot_manager_interface.py` | +9/-5 | Abstract method rename |
| `memory/solution_snapshot_mgr.py` | +11/-5 | File-based manager rename + return type |
| `rest/routers/admin.py` | +71/-71 | Dependency injection + cleanup |
| `rest/running_fifo_queue.py` | +9/-8 | Call site renames + cache hit save |
| `rest/todo_fifo_queue.py` | +1/-1 | Minor formatting |

**Total Impact**: 8 files, +151 insertions/-185 deletions (net -34 lines)

### Current Status

- **ID Hash Collision**: ✅ FIXED - Each snapshot gets unique timestamp with microseconds
- **LanceDB Query Fix**: ✅ COMPLETE - Exact matches use pandas filtering
- **Method Rename**: ✅ COMPLETE - `save_snapshot()` across all files
- **Diagnostic Cleanup**: ✅ COMPLETE - ~200 lines removed

### Testing Required

1. Delete LanceDB database to clear corrupted data
2. Restart server
3. Test "sqrt(100)" → should return 10
4. Test "sqrt(122)" → should return ~11.045 (NOT 10!)
5. Verify unique `id_hash` values in admin snapshots view

---

## 2025.11.25 - Parent Lupin Sync: LanceDB Query Fix + Method Rename + Dependency Injection COMPLETE

### Summary
Synced 6 files from parent Lupin Session 10 (2025.11.25) with critical bug fixes and architectural improvements. Tonight's work addressed three major issues: (1) LanceDB exact match queries returning wrong results, (2) method naming inconsistency (add_snapshot → save_snapshot), and (3) stale runtime stats in admin endpoints.

### Work Performed

#### LanceDB Query Pattern Bug Fix - COMPLETE ✅
**File**: `memory/canonical_synonyms_table.py` (+28/-30 lines)

**Problem**: Exact match lookups returned WRONG snapshots. Example: Asking "What's the square root of 144?" returned "What's 2+2?" answer (4 instead of 12).

**Root Cause**: LanceDB's `table.search().where(filter)` without a vector query returns **arbitrary rows**, not filtered results - it's NOT a SQL-like filter!

**Fix**: Changed all three `find_exact_*` methods to use pandas filtering instead:
```python
# BEFORE (broken - returns arbitrary rows)
results = self._canonical_synonyms_table.search().where(
    f"question_verbatim = '{escaped_question}'"
).limit( 1 ).to_list()

# AFTER (correct - actual exact match)
df = self._canonical_synonyms_table.to_pandas()
matches = df[df['question_verbatim'] == question]
```

**Methods Fixed**:
- `find_exact_verbatim()` (lines 276-300)
- `find_exact_normalized()` (lines 325-349)
- `find_exact_gist()` (lines 374-398)

#### Method Rename: add_snapshot → save_snapshot - COMPLETE ✅
**Rationale**: The method performs an upsert (INSERT or UPDATE), not just "add". Renamed for semantic clarity.

**Files Modified**:
1. `memory/lancedb_solution_manager.py` (+24/-24 lines) - Definition + docstring
2. `memory/snapshot_manager_interface.py` (+9/-5 lines) - Abstract method
3. `memory/solution_snapshot_mgr.py` (+11/-5 lines) - File-based implementation (now returns bool)
4. `rest/running_fifo_queue.py` (+8/-9 lines) - 3 call sites

**Additional Fix in running_fifo_queue.py**:
Added `self.snapshot_mgr.save_snapshot( cached_snapshot )` in `_format_cached_result()` - this was the ROOT CAUSE of runtime stats not persisting on cache hits (blocked Sessions 8-9).

#### FastAPI Dependency Injection (Stale Stats Fix) - COMPLETE ✅
**File**: `rest/routers/admin.py` (+28/-70 lines)

**Problem**: Admin endpoints showed stale runtime stats (run_count always 0) despite multiple executions.

**Root Cause**: Each admin request created a new `LanceDBSolutionManager` instance instead of using the global singleton that math agent was writing to.

**Fix**: Implemented FastAPI dependency injection pattern:
```python
def get_snapshot_manager():
    """Dependency to get snapshot manager from main module."""
    import fastapi_app.main as main_module
    return main_module.snapshot_mgr
```

**Endpoints Updated**:
- `GET /admin/snapshots/search` - now uses `Depends(get_snapshot_manager)`
- `GET /admin/snapshots/{id_hash}` - now uses `Depends(get_snapshot_manager)`
- `DELETE /admin/snapshots/{id_hash}` - now uses `Depends(get_snapshot_manager)`

**Model Enhancement**:
Added to `SnapshotDetailResponse`:
- `synonymous_questions: Dict[str, float] = {}` - question → similarity score
- `synonymous_question_gists: Dict[str, float] = {}` - gist → similarity score

### Files Modified

**COSA Repository** (6 files):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `memory/canonical_synonyms_table.py` | +28/-30 | LanceDB query fix (pandas filtering) |
| `memory/lancedb_solution_manager.py` | +24/-24 | Method rename + docstring |
| `memory/snapshot_manager_interface.py` | +9/-5 | Abstract method rename |
| `memory/solution_snapshot_mgr.py` | +11/-5 | File-based rename + return type |
| `rest/routers/admin.py` | +28/-70 | Dependency injection + synonyms fields |
| `rest/running_fifo_queue.py` | +8/-9 | 3 call sites + cache hit save |

**Total Impact**: 6 files, +108 insertions/-143 deletions (net -35 lines)

### Integration with Parent Lupin

**Parent Session Context** (2025.11.25, Session 10 Part 3):
- Three major features: Collapsible Synonyms UI, TTFA Timing Metrics, Stale Stats Fix
- Earlier Session 10: LanceDB query pattern bug fix, method rename, cache lookup consistency

**COSA Benefit**:
- Exact match queries now return correct results
- Semantic clarity with save_snapshot naming
- Admin endpoints show live runtime stats
- Cache hits properly persist runtime stats

### Current Status

- **LanceDB Query Fix**: ✅ FIXED - Exact matches work correctly
- **Method Rename**: ✅ COMPLETE - 4 files, 22 call sites updated
- **Dependency Injection**: ✅ IMPLEMENTED - Admin reads global singleton
- **Synonyms Fields**: ✅ ADDED - Admin detail endpoint includes synonyms

### Next Session Priorities

1. Validate LanceDB query fix with production data
2. Monitor admin endpoint runtime stats display
3. Consider adding cache consistency verification to admin endpoints

---

## 2025.11.24 - Parent Lupin Sync: Math Agent Debugging + Admin Snapshots API + LanceDB Optimizations COMPLETE

### Summary
Synced 10 files from parent Lupin repository with improvements from 4 math agent debugging sessions (Sessions 5-9, Nov 22-24). Work focused on resolving cache hit formatting inconsistencies, adding gist caching infrastructure, fixing LanceDB persistence issues, and enhancing admin API debugging capabilities. Major architectural improvement: SolutionSnapshot now preserves agent class name to replay with identical formatting logic.

### Work Performed

#### Math Agent Static Formatting Method - COMPLETE ✅
**File**: `agents/math_agent.py` (+51/-29 lines, net +22 lines)

**Changes**:
- NEW `apply_formatting()` static method (40 lines) encapsulating terse/verbose formatting decision
- Both MathAgent.run_formatter() and SolutionSnapshot.run_formatter() use same logic
- Debug/verbose conditionals updated throughout (4 locations)

**Problem Solved**: Cache hits were using LLM formatter even when original execution used terse mode, causing "2+2=4" to become verbose explanations.

#### Gist Cache Table - NEW FILE ✅
**File**: `memory/gist_cache_table.py` (536 lines, NEW)

**Purpose**: LanceDB-backed persistent cache for LLM-generated gists (~500ms savings per hit).

**Key Features**:
- Two-tier lookup: verbatim → normalized (catches "What's" vs "What is" variations)
- FTS indexes on both question_verbatim and question_normalized
- Expected 70-80% hit rate, ~5ms lookup vs ~525ms LLM call
- Statistics tracking (access_count, last_accessed)

#### LanceDB Solution Manager Optimizations - COMPLETE ✅
**File**: `memory/lancedb_solution_manager.py` (+119/-36 lines, net +83 lines)

**Changes**:
1. **Scalar Index on id_hash**: Added `create_scalar_index("id_hash", replace=True)` for merge_insert reliability
2. **Pre-Merge Cache Invalidation**: Clear cache BEFORE merge_insert to prevent stale reads
3. **Fresh DB Read After Merge**: Repopulate cache from DB, not in-memory record
4. **Comprehensive Debug Logging**: `[STATS DEBUG]`, `[CACHE DEBUG]`, `[CONSISTENCY]` prefixes
5. **DELETE Bug Fix**: Removed `.lower()` normalization causing cache key mismatch
6. **NEW `agent_class_name` Field**: Added to schema for formatting logic preservation

#### Solution Snapshot Agent Tracking - COMPLETE ✅
**File**: `memory/solution_snapshot.py` (+60/-19 lines, net +41 lines)

**Changes**:
- NEW `agent_class_name` field (Optional[str]) stores originating agent class
- `from_agent()` captures `type(agent).__name__` (e.g., "MathAgent", "CalendarAgent")
- `run_formatter()` checks agent_class_name and delegates to agent-specific formatting
- Enables correct terse/verbose behavior during cache hit replay

### Files Created/Modified

**COSA Repository** (11 files: 10 modified, 1 created):

| File | Lines Changed | Description |
|------|---------------|-------------|
| `agents/agent_base.py` | +3/-3 | Debug/verbose conditional fix |
| `agents/iterative_debugging_agent.py` | +1/-1 | Debug/verbose conditional fix |
| `agents/math_agent.py` | +51/-29 | Static formatting method |
| `memory/gister.py` | +56/-6 | Cache integration |
| `memory/gist_cache_table.py` | +536 NEW | Persistent gist cache |
| `memory/input_and_output_table.py` | +2/-6 | Minor cleanup |
| `memory/lancedb_solution_manager.py` | +119/-36 | Indexes, cache fix, debugging |
| `memory/solution_snapshot.py` | +60/-19 | Agent class tracking |
| `rest/routers/admin.py` | +20/-2 | API fields, debugging |
| `rest/routers/speech.py` | +35/-35 | Debug/verbose cleanup |
| `rest/running_fifo_queue.py` | +7/-18 | Code cleanup |

**Total Impact**: 11 files, +423 insertions/-127 deletions (net +296 lines)

### Current Status

- **Math Agent Formatting**: ✅ FIXED - Cache hits use same terse/verbose logic as original execution
- **Gist Caching**: ✅ IMPLEMENTED - ~500ms savings per cache hit
- **LanceDB Indexes**: ✅ ADDED - Scalar index on id_hash for merge_insert
- **DELETE Bug**: ✅ FIXED - Removed normalization causing cache key mismatch
- **Agent Tracking**: ✅ IMPLEMENTED - agent_class_name preserved in snapshots
- **Debug Output**: ✅ CLEANED - 15+ locations updated to debug && verbose pattern

---

## 2025.11.20 - Parent Lupin Sync: Test Infrastructure & Code Quality Improvements COMPLETE

### Summary
Synced 7 COSA files with improvements from parent Lupin repository's 100% Test Adherence achievement (2025.11.20). Updates focus on test infrastructure reliability, mathematical query support, error diagnostics, and defensive programming for Docker environments.

### Files Modified
7 files modified, +95 insertions/-29 deletions (net +66 lines)

---

## 2025.11.19 - PostgreSQL Repository Migration (Phase 2.6.3) COMPLETE

### Summary
Migrated COSA service layer files from direct SQLite database access to PostgreSQL repository pattern. Updated 8 files to use repository abstraction layer. Modernized all datetime operations from deprecated `datetime.utcnow()` to timezone-aware `datetime.now(timezone.utc)`.

### Files Modified
8 files modified, +186 insertions/-291 deletions (net -105 lines)

---

## 2025.11.18 - LanceDB GCS Multi-Backend Testing & Normalization Fix COMPLETE

### Summary
Completed comprehensive test-driven validation of LanceDB multi-backend storage infrastructure. Discovered and fixed critical normalization bug that caused 50% integration test failure.

### Test Results
- **Unit Tests**: ✅ 11/11 PASS (100%)
- **Local Backend Integration**: ✅ 3/3 PASS (100%)
- **GCS Integration**: ✅ 8/8 PASS (100%)
- **Total**: 22/22 tests passing (100%)

---

## 2025.11.18 - Unit Test Naming Standardization COMPLETE

### Summary
Standardized all 43 COSA unit test files from `unit_test_*.py` to `test_*.py` naming convention to align with pytest standards.

**Total Impact**: 44 files (43 renamed, 1 documentation update)

---

## 2025.11.13 - LanceDB Multi-Backend Storage Infrastructure COMPLETE

### Summary
Implemented multi-backend storage factory pattern for LanceDB solution snapshot manager to enable Cloud Run deployment with Google Cloud Storage.

### Files Modified
2 files modified, +120 insertions, -46 deletions

---

## 2025.11.11 - Phase 2.5.4 Config Migration COMPLETE

### Summary
Completed configuration migration for notification system. Renamed config location and keys with backward compatibility.

### Files Modified
4 files, +116/-18 lines

---

## 2025.11.10 - Phase 2.5.4 API Key Authentication Infrastructure COMPLETE

### Summary
Implemented header-based API key authentication for notification system.

### Files Created
3 new files, 609 lines

### Files Modified
5 files, +112/-39 lines

---

## 2025.11.08 - Notification System Phase 2.3 CLI Modernization COMPLETE

### Summary
Maintenance session to commit and push Phase 2.3 notification CLI work (1,376 lines).

---

## Archive Navigation

### Monthly Archives
- **[October 2025 (Oct 4-30)](history/2025-10-history.md)** - Planning workflows, CLI modernization, history management, branch analyzer refactoring (9 sessions)
- **[June-October 2025 (Jun 27 - Oct 3)](history/2025-06-27-to-10-03-history.md)** - Authentication infrastructure, WebSocket implementation, notification system refactor, testing framework (20 sessions)

### Project Context
- **Project Span**: June 2025 - Present (COSA framework within Lupin project)
- **Current Branch**: `wip-v0.1.0-2025.10.07-tracking-lupin-work`
- **Architecture**: Collection of Small Agents (COSA) for Lupin FastAPI application
- **Parent Project**: Lupin (located at `../..`)
