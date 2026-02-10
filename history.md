# COSA Development History

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
> **Commit**: [pending]
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
