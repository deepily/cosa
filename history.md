# COSA Development History

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
