# COSA Development History

> **✅ SESSIONS 239-242 COMMIT**: Proxy INI integration, trust feedback persistence, configurable dry-run, user_initiated_message rename, conditional LoRA args (2026.02.20)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 239-242** (10 files, +406/-90 lines):
>
> **Decision Proxy INI Integration + DB Persistence (Sessions 241+)**:
> - Added `trust_proxy_config_from_config_mgr()` factory in `decision_proxy/config.py` — reads 14 generic trust proxy INI keys with defaults
> - Added `swe_proxy_config_from_config_mgr()` factory in `swe_team/proxy/config.py` — reads 4 SWE-specific proxy INI keys (accepted_senders as comma-separated list)
> - Added `_persist_decision()` to `DecisionResponder` — DB persistence for all 4 action branches (shadow, suggest, act, defer), non-fatal best-effort
> - Rewired `SweTeamOrchestrator.__init__()` proxy initialization to build TrustTracker + CircuitBreaker from INI config via factory functions
> - Restructured `_gated_confirmation()`: always evaluates proxy (shadow/suggest/active), records trust feedback after every user decision, persists to DB via `_persist_trust_feedback()`
> - Added proxy status fields to `get_status()` (trust_mode, trust_levels, trust_stats, circuit_breaker)
> - Changed SWE Team default `trust_mode` from `"disabled"` to `"shadow"` in `swe_team/config.py`
> - Added INI-driven `trust_mode` read in `SweTeamJob._execute()` with fallback to shadow
>
> **Approach D Rename + Configurable Dry-Run (Session 242)**:
> - Renamed notification type `"user_message"` → `"user_initiated_message"` in `notification_client.py`, `queues.py` (filter, docstrings, smoke test dicts)
> - Added echo acknowledgment WebSocket emission in `queues.py` — progress notification echoed back to sender after job message persisted
> - Added `id_hash` field to WebSocket notification payloads in `queues.py`
> - Added `dry_run_phases` (default 10) and `dry_run_delay` (default 1.5s) params to `SweTeamJob`
> - Replaced 6 hardcoded sleep/notify blocks with loop over `DRY_RUN_PHASE_LABELS` list
> - Mock cost summary now uses actual simulated duration; artifacts stored for queue pickup
> - Wired `dry_run_phases`/`dry_run_delay` through `agentic_job_factory.py`
>
> **Training Data Conditional Args (Session 240)**:
> - Added conditional_args detection in `xml_coordinator.py` `build_agentic_job_training_prompts()` — scans voice commands for trigger phrases, appends matching arg values to output
>
> **Commit**: (pending)

---

> **✅ SESSIONS 235-236 COMMIT**: Unified job-user association (Bug #5) + Approach D user-initiated messaging (2026.02.20)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 235-236** (15 files, +828/-214 lines):
>
> **Bug #5 — Unify Job-User-Session Association (Session 235)**:
> - Added `register_scoped_job()` atomic operation to `UserJobTracker` — combines `generate_user_scoped_hash()` + `associate_job_with_user()` into single call
> - Replaced 2-call pattern with `register_scoped_job()` across all 6 agentic routers + 3 `todo_fifo_queue` call sites
> - Replaced 8 `user_job_tracker.get_user_for_job()` lookups with direct `job.user_id` in `running_fifo_queue.py`
> - Replaced tracker lookup with `job.user_id` in `queue_consumer.py` and `queues.py` router
> - Removed dead code: session tracking (`associate_job_with_session`, `get_session_for_job`, `get_jobs_for_session`), `get_user_for_job()`, `extract_base_hash()`
> - Fixed `user_id` key `"user_id"` → `"uid"` in `deep_research_to_podcast.py` and `podcast_generator.py`
>
> **Approach D — User-Initiated Messaging (Session 236)**:
> - NEW: `agents/swe_team/notification_client.py` (381 lines) — `OrchestratorNotificationClient` WebSocket listener for user messages → `threading.Queue`
> - Added `_user_messages` queue + `_urgent_interrupt` event to orchestrator
> - Extended `_check_in_with_user()` to drain messages, analyze via lead model, present with gated confirmation
> - Added urgent interrupt check in `_execute_live()` loop for immediate check-in on urgent messages
> - Added `_start_notification_client()` to `SweTeamJob._execute()` with try/finally cleanup
> - Added `enable_user_messages` config field + `job_id` param to orchestrator constructor
> - New REST endpoint: `POST /api/jobs/{job_id}/message` in `queues.py` router
>
> **Commit**: ab88631

---

> **✅ SESSIONS 226-234 COMMIT**: Voice-driven SWE factory, _parse_boolean, agentic modes, expeditor UX, speculative job ID, LoRA env resolution, check-in MVP, sender_id fix (2026.02.18)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 226-234** (16 files, +474/-145 lines):
>
> **Voice-Driven SWE Team + _parse_boolean (Session 226)**:
> - Wired canonical `create_agentic_job()` factory into voice path in `todo_fifo_queue.py` (deleted 75 lines inline factory)
> - Added `_parse_boolean()` to `agentic_job_factory.py` — fixes string `"no"` truthy bug on all 5 `dry_run` lines
> - Added `dry_run` to SWE Team registry entry, CLI `--user-visible-args`, proxy TEST_PROFILES
> - Removed 3 hardcoded `dry_run` exclusions in `expeditor.py` (now whitelist-controlled)
>
> **LoRA Env Var Resolution (Session 227)**:
> - Added `os.path.expandvars()` in `ConfigurationManager.get()` for `${ENV_VAR}` pattern resolution
> - Added `_update_lora_env()` to `PeftTrainer` — auto-updates `~/.lora_env` after successful training runs
>
> **Agentic Mode Switches (Session 229)**:
> - Added `AGENTIC_MODE_MAP` (5 entries) + `MODE_METADATA` entries for UI dropdown in `todo_fifo_queue.py`
> - Agentic modes bypass LoRA router, routing directly to disambiguation → expeditor → factory
>
> **Expeditor UX + Speculative Job ID (Session 230)**:
> - Truncated batch TTS to count-only preamble in `notification_utils.py`
> - Added fallback default pre-population in `expeditor.py` (original_question → default_value)
> - Added `job_prefix` to all 5 AGENTIC_AGENTS registry entries
> - Speculative job ID generation before expeditor runs in `todo_fifo_queue.py`
> - Added None→empty-string coercion `field_validator` to `ExpeditorResponse` + `ArgConfirmationResponse`
> - Extended `job_id` regex to accept compound short format (`prefix-hex8::UUID`) in `notification_models.py`
>
> **Duplicate Notification Fix (Session 231)**:
> - Added early return after AGENTIC_AGENTS branch in `push_job()` to prevent fallthrough double-notify
>
> **SWE Team Training Data Routing (Session 232)**:
> - Added `get_swe_team_tasks()` to `xml_prompt_generator.py`
> - Registered `swe_team_tasks` in `xml_coordinator.py` dispatch dict
>
> **User-Initiated Check-In MVP (Session 233)**:
> - Added `_check_in_with_user()` to `orchestrator.py` with WAITING_FEEDBACK state + configurable timeout
> - 2 check-in call sites: between-task (with feedback injection) and post-completion
> - Added `enable_checkins` + `checkin_timeout` config fields in `swe_team/config.py`
>
> **Bug F: sender_id Validation (Session 234)**:
> - Fixed `get_sender_id()` in `cosa_interface.py` to strip `::user_id` suffix from compound session IDs
>
> **Commit**: 4510eb7

---

> **✅ SESSIONS 219-225 COMMIT**: Factory safe parsing, progress_group_id persistence, training cleanup, SWE Team routing (2026.02.18)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 219-225** (11 files, +156/-122 lines):
>
> **Factory ValueError Fix (Session 219)**:
> - Added `_SEMANTIC_NONE` set + `_parse_optional_int()`/`_parse_optional_float()` safe parsing helpers in `agentic_job_factory.py`
> - Replaced 6 raw `int()`/`float()` casts across all 5 agentic job types (deep research, podcast, research-to-podcast, claude code, swe team)
> - Added `"timeout"` + `"default"` to expeditor skip guards at both batch and single paths
>
> **progress_group_id Backend Persistence (Session 220 Checkpoint 3)**:
> - Added `progress_group_id` column to `Notification` model (String(12), nullable, indexed)
> - Wired `progress_group_id` through all 3 `create_notification()` call sites in notifications router
> - Added `progress_group_id` + `job_id` to both serialization dicts (`get_sender_conversation` + `get_sender_conversation_by_date`)
>
> **Training Pipeline Cleanup (Session 222)**:
> - Deleted `write_agentic_job_ttv_split_to_jsonl()` + `get_agentic_job_train_test_validate_split()` (stale, unused)
> - Refactored `build_agentic_job_training_prompts()` to config-driven dispatch via `_load_agentic_commands_config()` + `_get_placeholder_values_by_name()`
> - Updated `xml_prompt_generator.py` to use enriched JSON config format
>
> **SWE Team Notification Routing Fix (Session 225)**:
> - Changed `agentic_job_base.py` `notify_progress()`/`notify_completion()` to import core `voice_io` instead of deep research `voice_io`
> - Added `SESSION_ID = self.id_hash` in SWE Team job `_execute()` and `_execute_dry_run()` paths
> - Added `progress_group_id` parameter to SWE Team `voice_io.notify()` wrapper
> - Converted all 4 dispatch branches in `utils/voice_io.py` from positional to keyword arguments
>
> **Commit**: 7a7ea21

---

> **✅ SESSIONS 214-218 COMMIT**: SWE Team notifications/Surface 3, answer_is_correct, semantic match, Calculator bugs, PEFT OOM (2026.02.16)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 214-218** (28 files, +1,268/-174 lines):
>
> **SWE Team Notifications & Surface 3 (Sessions 214-218)**:
> - 3-tier notification gap analysis (20 gaps): progress, escalation, job_id, artifacts, ResultMessage, state emission, contracts, decision proxy, ProgressLog
> - Surface 2A/2B: SWE Team Job class, factory registration, FastAPI router, 22 tests + 6 mock scenarios
> - Surface 3: Registered SWE Team in AGENTIC_AGENTS (5th agent), added `--user-visible-args` to CLI, created proxy profile
>
> **answer_is_correct Tri-State Field (Session 215)**:
> - Added `answer_is_correct` (True/False/None) to SolutionSnapshot + LanceDB schema
> - Non-blocking async verification via `_fire_correctness_check_async()` in RunningFifoQueue
> - Cache hits inherit stored value
>
> **Semantic Match Simplification (Session 215)**:
> - Removed 95% hard threshold floor, 3-tier decision (100% auto-accept, >=90% ask user, <90% skip to LLM)
> - Commented out L3 gist match block, removed L4 threshold filter
>
> **Calculator Bug Fixes (Session 214)**:
> - MathAgent snapshot replay: missing `prompt_response_dict` copy-back
> - "unitless" bug: prompt rule 6, unit validation guard, whole-number format check
>
> **PEFT Resume OOM (Session 216)**: Documented as WILL NOT FIX (cold allocator, 16GB monolithic segment)
>
> **PR #16 merged** → v0.1.4 tag created → new branch `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> **Commit**: 96606c8

---

> **✅ SESSIONS 206-213 COMMIT**: SWE Team Delegation/Verification/Decision Proxy + PEFT Resume-from-Merged + GPU Memory Release (2026.02.14)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 206-213** (34 files, +4,755/-375 lines):
>
> **SWE Team Multi-Agent System (Sessions 206-207, 210)**:
> - Phase 2: Lead→Coder delegation loop via Claude Agent SDK — `hooks.py` (notification/pre-tool/post-tool hooks), `state_files.py` (FeatureList + ProgressLog persistence), `_decompose_task()` → `_parse_task_specs()` → `_delegate_task()` pipeline, coder role activated (v0.2.0)
> - Phase 3: Coder-Tester verification loop — `test_runner.py` (pytest subprocess via `asyncio.create_subprocess_exec`), `VerificationResult` model, `_verify_result()` + `_redelegate_with_feedback()`, MAX_VERIFICATION_ITERATIONS=3, tester role activated (v0.3.0)
> - Phase 4: Trust-Aware Decision Proxy — 4-layer hybrid architecture:
>   - Extracted shared proxy infra to `agents/utils/proxy_agents/` (7 files): BaseStrategy protocol, BaseWebSocketListener, BaseResponder ABC, shared config, REST submitter, CLI args
>   - Built decision proxy framework in `agents/decision_proxy/` (13 files): trust mode, smart router, category classifier ABC, base decision strategy ABC, XML models, circuit breaker, trust tracker L1-L5 with time-weighted decay
>   - SWE engineering domain in `agents/swe_team/proxy/` (5 files): 6 engineering categories (deployment/testing/deps/architecture/destructive/general), keyword classifier with sender hints
>   - Decision store + ratification API: ProxyDecision + TrustState ORM models in `postgres_models.py`, repository with shadow/log/ratify/find_similar, FastAPI router (4 endpoints)
>   - Refactored `notification_proxy/config.py` for backward compatibility (re-export shared constants)
>
> **PEFT Trainer Enhancements (Sessions 209, 213)**:
> - `peft_trainer.py`: Added `--resume-from-merged` CLI arg — skips phases 1-3, uses existing merged adapter for phases 4-5 (post-validation, quantization)
> - `peft_trainer.py`: Removed `run_pipeline_adhoc()` (170 lines hardcoded workaround) — replaced by new CLI flag
> - `quantizer.py`: Added `release_gpu_memory()` — `model.cpu()` + GC + CUDA cache clear for post-quantization vLLM OOM fix
> - `peft_trainer.py`: Cleanup block calls `release_gpu_memory()` before `del quantizer`
>
> **Bug Fix: vLLM max_tokens overflow in PEFT validation**:
> - `xml_coordinator.py`: Threads `max_new_tokens` param through to `CompletionClient.run()`
>
> **Commit**: 357ca84
>
> ---

> **✅ SESSIONS 201-205 COMMIT**: Routing Command Normalization + Cache N/A Bug Fix + Similarity Confirmation Toggle + WebSocket Exception Fix + SWE Team Agent (2026.02.14)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 201-205** (~11 files modified, 1 new package, +219/-74 lines):
>
> **Routing Command Normalization (Sessions 201-205)**:
> - Shortened verbose routing commands across 6 files: `"date and time"` → `"datetime"`, `"todo list"` → `"todo"`, `"automatic routing mode"` → `"automatic"`
> - `date_and_time_agent.py`: Default routing_command updated
> - `todo_list_agent.py`: Default routing_command updated
> - `prompt_template_processor.py`: MODEL_MAPPING keys normalized
> - `xml_parser_factory.py`: agent_model_map + formatter keys normalized
> - `xml_models.py`: AgentRouterResponse valid_commands list normalized
> - `todo_fifo_queue.py`: Backward-compatible `in` tuple/list checks for old + new command strings
> - `llm_client_factory.py`: Smoke test prompt template key normalized
> - `xml_coordinator.py`: Training augmentation_config keys normalized
>
> **Bug Fix: Cache Re-Execution of Non-Executable Code — "N/A" Bug (Session 204)**:
> - `solution_snapshot.py`: Changed code fallback from `"N/A"` to `[ "" ]` (correct `list[str]` type)
> - `solution_snapshot.py`: Added empty-code guard in `run_code()` raising `ValueError` before subprocess spawn
> - `running_fifo_queue.py`: `try/except ValueError` wrapper in `_format_cached_result()` for empty code
>
> **Bug Fix: Missing WebSocket Event in Generic Exception Handler (Session 204)**:
> - `running_fifo_queue.py`: Generic except block in `_process_job()` now emits `job_state_transition('run', 'dead')` with full metadata (error, timing, status) + TTS notification — matching `_handle_error_case()` pattern
>
> **Bug Fix: Stopwatch API Mismatch in Cache Hit Path (Session 204)**:
> - `running_fifo_queue.py`: Replaced non-existent `stop()` + `get_elapsed_millis()` with `get_delta_ms()`
>
> **Similarity Confirmation Toggle — Runtime Configurable (Session 205)**:
> - `todo_fifo_queue.py`: Check `similarity_confirmation_enabled` config before prompting user; auto-accept semantic match when disabled
> - `rest/routers/system.py`: New GET/POST `/api/config/similarity-confirmation` endpoints with Pydantic models + `get_todo_queue()` dependency
>
> **Dead Code Removal**:
> - `todo_fifo_queue.py`: Removed unreachable `refactor` branch in math routing, removed defensive `hasattr(agent, 'id_hash')` check
>
> ---

> **✅ SESSIONS 190-200 COMMIT**: CJ Flow Bounded Jobs + 768-dim Embedding Standardization + Dead Job WebSocket Fix + Batch XML Model + Expeditor open_ended_batch Fix (2026.02.12)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 190-200** (~38 files modified, +863/-189 lines):
>
> **CJ Flow Bounded Job Packaging + Claude Code LORA Data (Session 197)**:
> - `claude_code/job.py`: Externalized hardcoded defaults (max_turns=50, timeout_seconds=3600) to config with class-level caching
> - `agentic_job_factory.py`: Registered ClaudeCodeJob in shared factory
> - `claude_code_queue.py`: Router updated to use shared factory
> - `agent_registry.py`: ClaudeCodeJob entry with display_name + user-visible-args
> - CJ Flow branding propagated to 12 files (docstrings/comments only): agentic_job_base, queue_protocol, queue_consumer, running_fifo_queue, websocket_manager, 5 routers
> - `xml_coordinator.py` + `xml_prompt_generator.py` + `xml_models.py`: Claude Code LORA training pipeline (66 templates, 1,500 samples)
>
> **LanceDB Embedding Dimension Mismatch — 768 Standardization (Session 198)**:
> - `embedding_manager.py`: Pass `dimensions=embedding_dim` to OpenAI API (MRL truncation)
> - `embedding_provider.py`: Simplified `dimensions` + `code_dimensions` properties using centralized config
> - All 6 LanceDB table classes: Simplified dimension init + added `_validate_embedding_dimensions()` auto-drop/recreate on schema mismatch
>   - canonical_synonyms_table, embedding_cache_table, input_and_output_table, lancedb_solution_manager, query_log_table, question_embeddings_table
>
> **Dead Job Card WebSocket Fix (Session 199)**:
> - `running_fifo_queue.py`: Added missing `emit_job_state_transition()` in `_handle_error_case()` for `run -> dead` transition with full error metadata
>
> **Batch XML Model + Ampersand Escaping (Session 195)**:
> - `notification_proxy/xml_models.py`: NEW `BatchScriptMatcherResponse` — first-class Pydantic XML model with nested `<entries><entry>` structure
> - `llm_script_matcher.py`: Updated `_handle_batch()` to use new model
> - `prompt_template_processor.py`: Registered batch model in `MODEL_MAPPING`
> - `util_xml_pydantic.py`: Added `&` entity escaping in `from_xml()` for bare ampersands in LLM reasoning
>
> **Expeditor open_ended_batch Fix (Session 200)**:
> - `notifications.py`: Added `"open_ended_batch"` to `valid_response_types` list
> - `notify_user_sync.py`: Enhanced HTTP error diagnostic — status code now in error string (`http_error_400`)
> - `expeditor.py`: Updated expeditor notification flow
> - `notification_proxy/voice_io.py`: Voice I/O enhancements
> - `notification_proxy/config.py` + `responder.py`: Configuration updates
>
> **Other**:
> - `rest/middleware/api_key_auth.py`: Auth middleware additions
> - `mock_job.py`: Expeditor test mode updates
> - `llm_client_factory.py`: Client factory refinements
>
> **Commit**: 399c991
>
> ---

> **✅ SESSIONS 182-189 COMMIT**: LLM Script Matcher + Data-Driven Sender IDs + CRUD Dedup Guards + Local Embedding Provider + vLLM Marlin Config (2026.02.12)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 182-189** (~26 files modified/created):
>
> **Notification Proxy LLM Script Matcher (Session 183)** — 3 new files:
> - `xml_models.py` — `ScriptMatcherResponse` and `VerificationResponse` BaseXMLModel subclasses
> - `strategies/llm_script_matcher.py` — `LlmScriptMatcherStrategy` drop-in replacement for `ExpediterRuleStrategy`, Phi-4 powered
> - `verification.py` — `LlmAnswerVerifier` with exact-match bypass optimization
> - `responder.py`: 3-tier strategy chain (script_matcher → rules → cloud)
> - `__main__.py`: `--strategy` CLI flag for strategy selection
> - `config.py`: 10 new constants for script matcher configuration
> - `prompt_template_processor.py`: 2 `MODEL_MAPPING` entries
>
> **Data-driven sender ID filtering (Session 187)**:
> - Replaced hardcoded `EXPEDITER_SENDER_ID` with data-driven `sender_ids` field from Q&A script JSON
> - `expediter_rules.py`: `accepted_senders` param + list-based `can_handle()`
> - `config.py`: `DEFAULT_ACCEPTED_SENDERS` list + deprecated alias
> - `responder.py`: Extract `sender_ids` from script, pass to strategies at construction
>
> **CRUD dedup guards + live pipeline test (Session 189)**:
> - `crud_operations.py`: Dedup guard in `add_item()`, multi-delete guard in `delete_item()`, infrastructure column rejection in `_validate_match_fields()`
> - `schemas.py`: `DEDUP_KEYS` dict, `INFRASTRUCTURE_COLS` frozenset, `get_dedup_keys()` helper
> - `dispatcher.py`: `"duplicate"` voice formatting
> - `config.py`: `crud` profile in `TEST_PROFILES`
>
> **Local embedding provider** (undocumented session):
> - `memory/embedding_provider.py` (NEW) — Routing layer: "openai" → EmbeddingManager (1536 dims), "local" → CodeEmbeddingEngine/ProseEmbeddingEngine (768 dims)
> - `memory/local_embedding_engine.py` (NEW) — CodeEmbeddingEngine (nomic-ai/CodeRankEmbed) + ProseEmbeddingEngine (nomic-embed-text-v1.5 Matryoshka)
> - All 7 memory tables: Configurable embedding dimension from provider config (hardcoded 1536 → dynamic)
> - `todo_fifo_queue.py`: Switched from `EmbeddingManager` to `EmbeddingProvider` for embedding generation
> - `requirements.txt`: Added sentence-transformers, nomic, llama-index-embeddings-huggingface/nomic
>
> **vLLM PEFT pipeline improvements (Sessions 182, 184)**:
> - `llama_3_2_3b.py`: `"quantization": "gptq_marlin"` in vllm_config, expanded config structure
> - `peft_trainer.py`: `quantization` parameter + `verbose_server` flag for Marlin kernel verification
>
> **Commit**: 9f807aa
>
> ---

> **✅ SESSIONS 168-180 COMMIT**: Notification Proxy Agent + Calculator Pipeline job_id + JWT WebSocket Fix + vLLM V1 Engine Compatibility (2026.02.10)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 168-180** (~20 files modified/created):
>
> **New Notification Proxy Agent (Session 171)** — 10 new files:
> - `agents/notification_proxy/` package — standalone CLI agent that connects via WebSocket, subscribes to notification events, auto-answers expediter questions using hybrid strategy (rules for known patterns, LLM fallback for unknowns)
> - `listener.py` — async WebSocket client with auth, ping/pong, exponential backoff reconnection
> - `responder.py` — notification router + REST API response submission
> - `strategies/expediter_rules.py` — rule-based keyword matching with 4 test profiles
> - `strategies/llm_fallback.py` — Anthropic SDK fallback
> - `config.py` — 2-tier credential resolution (Session 173), test profiles, `all_agents` union profile (Session 179)
>
> **Calculator agent pipeline (Sessions 161, 172, 177)**:
> - `SolutionSnapshot`: CalculatorAgent formatter bypass (skip LLM reformatting), `str()` wrapper on answer field
> - `push_job()` returns `Dict` with `job_id` at all 5 return sites in todo_fifo_queue.py
> - `queues.py`: Extract `job_id` from dict return, include in `/api/push` API response
> - `queue_extensions.py`: Double-scoping prevention in `create_compound_hash()`
> - `xml_coordinator.py`: Added `"agent router go to calculator": { "factor": 3 }` to augmentation_config
>
> **JWT WebSocket auth fix (Session 173)**:
> - `websocket.py`: Strip `Bearer ` prefix before `verify_token()` — REST endpoints got this from FastAPI's HTTPBearer, WebSocket needed manual handling
>
> **vLLM V1 engine compatibility (post-0.8.5 upgrade)**:
> - `ministral_8b.py`: Added `max_num_seqs=64` to prevent V1 engine warmup OOM
> - `qwen3_4b.py`: Reduced `gpu_memory_utilization` 0.90→0.70, added `tensor_parallel_size=1`, `max_num_seqs=64`
> - `peft_trainer.py`: Config-driven TP size override (was always auto-detect), `max_num_seqs` passthrough to vLLM serve command
>
> **Training pipeline fix**:
> - `xml_coordinator.py`: Pass `max_tokens=max_new_tokens` to `llm_client.run()` — was dropping parameter, causing context overflow
>
> **Expediter rules fix (Session 179)**:
> - Keyword ordering fix in `expediter_rules.py`
>
> **Commit**: 1b58d95
>
> ---

> **✅ SESSIONS 155-167 COMMIT**: Batch Questions + PEFT Multi-LLM + Calculator Agent + CRUD Delete Fix + Expeditor Enhancements (2026.02.09)
> **Owner**: claude.code@cosa.deepily.ai#b726f9e6
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 155-167** (~20 files modified, 2 new):
>
> **Batch open-ended questions + expeditor defaults (Session 156)**:
> - New `OPEN_ENDED_BATCH` ResponseType in notification_models.py
> - `format_open_ended_batch_for_tts()` and `convert_open_ended_batch_for_api()` in notification_utils.py
> - `_batch_collect_args()` in expeditor.py — partitions batchable vs special-handler args
> - `_resolve_default()` three-tier override chain (config INI > agent_registry fallback_defaults > None)
> - `fallback_defaults` dict added to each agent entry in agent_registry.py
>
> **PEFT dual quantization + multi-LLM support (Session 157)**:
> - `--quantize-bits {both,4,8}` loop producing separate quantized models per bit width
> - `_write_training_summary_to_file()` markdown dashboard with YAML frontmatter + 4 tables
> - Qwen3-4B-Base LoRA config with Alpaca prompt template (new `qwen3_4b.py`)
> - Model registered in `MODEL_CONFIG_MAP` and `supported_model_names` (model_config_loader.py)
> - KLUDGE vendor fallback in llm_client_factory.py for HF model ID parsing
> - Fixed post-training validation model name — bare path for vLLM (4 call sites)
> - Bash executable fix for venv activation in `_start_vllm_server()`
>
> **CRITICAL delete bug fix (Session 159)**:
> - `_validate_match_fields()` helper in crud_operations.py — returns error if key doesn't exist in DataFrame columns
> - Guards added to both `delete_item()` and `update_item()` preventing silent all-row deletion
>
> **Expeditor job_id threading + request context (Session 160)**:
> - `_build_request_context()` method for human-readable notification card abstracts
> - `job_id` threaded through all notification calls (_ask_for_confirmation, _ask_for_arg, _batch_collect_args)
> - `display_name` added to agent_registry.py entries
> - DIAG logging gate: 8-line WebSocket state dump wrapped behind `app_debug and app_verbose`
> - Safer default: `response_default="no"` in `_ask_for_confirmation()`
>
> **New Calculator agent (Session 161)**:
> - `agents/calculator/` package — CalculatorAgent with `run_prompt_with_fallback()` + `_delegate_to_math_agent()`
> - CalcIntent XML model with `get_example_for_template()` fix (literal JSON braces → descriptive text)
>
> **Expeditor timeout chain fix (Session 163)**:
> - Raised notification timeouts: `_ask_for_arg` 60→180s, `_ask_for_confirmation` 60→180s, `_batch_collect_args` 120→300s
> - Diagnostic `[Expeditor]` debug prints after all 3 `notify_user_sync` calls
> - API default timeout 30→120s in notifications.py
>
> **Commit**: 0f139aa
>
> ---

> **✅ SESSIONS 147-154 COMMIT**: Audience Normalization + Expeditor Enhancements + PEFT Dashboard + Principled Augmentation (2026.02.07)
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 147-154** (30 files, +1,101/-214 lines):
>
> **Audience normalization across all agents (Session 149)**:
> - Renamed `target_audience` → `audience`, default `"expert"` → `"academic"` across all 3 pipelines
> - Wired `audience`/`audience_context` through job → factory → REST router → agent registry → prompts
> - Added `AUDIENCE_DIALOGUE_GUIDELINES` dict to podcast `script_generation.py`
> - Updated `PodcastConfig`, CLI args, REST models, and agent_base.py
>
> **Runtime Argument Expeditor enhancements (Sessions 151, 154)**:
> - Confirmation loop: `_confirm_and_iterate()` + `_parse_modification()` in expeditor.py
> - `ArgConfirmationResponse` BaseXMLModel with `is_approval()`/`is_cancel()`/`is_modify()` helpers
> - User-visible args whitelist: agents publish `USER_VISIBLE_ARGS`, expeditor consumes via `get_user_visible_args()`
> - Changed confirmation from blacklist (hide system_provided) to whitelist (show only user-visible)
> - Added `--user-visible-args` flag to all 3 agent CLIs
>
> **PEFT training improvements (Sessions 148, 152)**:
> - Results dashboard: 4 comparison tables (overall, per-command, quantization, timing) in peft_trainer.py
> - Augmentation factor loop: `augmentation_config` parameter per command in xml_coordinator.py
> - `skip_empty`/`skip_comments` for `get_file_as_list()` in util.py
> - Automatic routing mode handler in todo_fifo_queue.py
>
> **CRUD pipeline alignment (Session 148 CP3)**:
> - Replaced ad-hoc placeholder with `{{PYDANTIC_XML_EXAMPLE}}` marker in prompt_template_processor
> - Registered `CRUDIntent` in `MODEL_MAPPING`
> - Generic placeholders for unbiased LLM XML structure
>
> **Commit**: bebdac7
>
> ---

> **✅ SESSIONS 136-146 COMMIT**: DataFrame CRUD System + PEFT Training + Async Fix (2026.02.06)
> **Owner**: claude.code@cosa.deepily.ai#5d7d4301
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 136-146** (16 files, +2,746/-80 lines):
>
> **New `crud_for_dataframes/` package (10 files)**:
> - Phase 1 storage layer: schemas, xml_models, storage, crud_operations (Session 137)
> - Phase 2 agent layer: agent, todo_crud_agent, calendar_crud_agent, dispatcher, intent_extractor (Session 143)
>
> **Queue integration (Phase 3, Session 143)**:
> - Feature-flag routing swap: TodoCrudAgent/CalendarCrudAgent replace legacy agents in todo_fifo_queue.py
> - Cache skip + serialization exclusion for mutable CRUD data in running_fifo_queue.py
> - Voice confirmation for destructive operations (delete, update) via notify_user_sync
> - Agentic command disambiguation with product names (Deep Dive, PodMaker, Doc-to-Pod)
>
> **PEFT training improvements (Sessions 131, 136, 142, 146)**:
> - Stratified validation sampling (equal per command instead of random) in peft_trainer.py
> - File-loaded templates replacing 10 hardcoded patterns with 65+ per command in xml_coordinator.py
> - Fixed DataFrameGroupBy.apply DeprecationWarning (include_groups=False)
> - GPU memory release logging moved to after actual release
>
> **Bug fixes (Sessions 142, 144)**:
> - Fixed async event loop deadlock in expeditor test mode (asyncio.to_thread in mock_job.py)
> - Fixed expeditor voice prompt priority (HIGH) and suppress_ding (False) in expeditor.py
>
> **Commit**: 3adb85e
>
> ---

> **✅ SESSION 135 COMPLETE**: Branch Transition v0.1.3 → v0.1.4 (2026.02.05)
> **Owner**: claude.code@cosa.deepily.ai#6aeca163
> **Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
>
> ### Accomplishments
>
> **Completed branch transition from v0.1.3 to v0.1.4 via PR merge workflow**:
> - Stashed 11 modified + 3 untracked WIP files (v0.1.4 in-progress work)
> - Created PR #15: "COSA v0.1.3: Sessions 108-128" (8 commits, 55 files, +4,316/-1,380 lines)
> - PR merged on GitHub, fast-forwarded main to `8a596ac`
> - Created new branch `wip-v0.1.4-2026.02.05-tracking-lupin-work` from updated main
> - Restored stashed WIP changes cleanly (no conflicts)
>
> **PR #15**: https://github.com/deepily/cosa/pull/15
> **WIP files restored**: RuntimeArgumentExpeditor, agentic_job_factory, training pipeline improvements, router updates
>
> ---

## Archive Navigation

### Monthly Archives
- **[Nov 2025 - Feb 2026 (Nov 8, 2025 - Feb 3, 2026)](history/2025-11-08-to-2026-02-03-history.md)** - Sessions 56-126: Conversation Identity, Deep Research Agent, Podcast Generator, Queue Protocol, Directory Analyzer, Lupin sync entries
- **[October 2025 (Oct 4-30)](history/2025-10-history.md)** - Planning workflows, CLI modernization, history management, branch analyzer refactoring (9 sessions)
- **[June-October 2025 (Jun 27 - Oct 3)](history/2025-06-27-to-10-03-history.md)** - Authentication infrastructure, WebSocket implementation, notification system refactor, testing framework (20 sessions)

### Project Context
- **Project Span**: June 2025 - Present (COSA framework within Lupin project)
- **Current Branch**: `wip-v0.1.4-2026.02.05-tracking-lupin-work`
- **Architecture**: Collection of Small Agents (COSA) for Lupin FastAPI application
- **Parent Project**: Lupin (located at `../..`)
