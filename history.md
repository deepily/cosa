# COSA Development History

> **✅ SESSIONS 385+386 COMMITTED**: Unified Job State Machine + TestSuiteJob agent + scheduling timezone fix (2026.03.31)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 385 — CJ Flow: Unified Job State Machine**:
> - `rest/job_state.py` (new): 9-state `JobState( str, Enum )` with frozen transition matrix, `validate_transition()`/`assert_valid_transition()`, convenience sets (TERMINAL, PRE_EXECUTION, ACTIVE), `STATE_TO_UI_CONTAINER` mapping
> - `rest/queue_protocol.py`: `status: str` → `state: JobState`, removed `paused: bool`
> - `agents/agentic_job_base.py`: Removed `paused` constructor param, updated to `state: JobState`
> - `agents/agent_base.py`, `memory/solution_snapshot.py`: Updated to `JobState` protocol fields
> - 9 agent job subclasses updated: `bug_fix_expediter`, `claude_code`, `deep_research`, `deep_research_to_podcast`, `deep_research_to_presentation`, `podcast_generator`, `presentation_generator`, `swe_team`, `mock_job`
> - `rest/queue_util.py`: `emit_job_state_transition()` renamed `from_queue`/`to_queue` → `from_state`/`to_state` with transition validation
> - `rest/job_persistence.py`, `rest/fifo_queue.py`, `rest/queue_consumer.py`, `rest/running_fifo_queue.py`, `rest/todo_fifo_queue.py`, `rest/routers/queues.py`: Updated for JobState enum throughout
>
> **Session 386 — TestSuiteJob: New CJ Flow Agentic Agent**:
> - `agents/test_suite/` (new package): `job.py`, `voice_io.py`, `cosa_interface.py`, `__init__.py` — runs integration/E2E test suites as AgenticJob with `monopolize=True`
> - `rest/routers/test_suite.py` (new): `POST /api/test-suite/submit` endpoint
> - `rest/agentic_job_factory.py`: Factory branch for `test_suite` (9th agent)
> - `agents/runtime_argument_expeditor/agent_registry.py`: Registry entry for `test_suite`
> - `agents/notification_proxy/config.py`: Test profile for `test_suite` auto-answer
>
> **Session 386 — Bug Fix: Scheduled Jobs Execute Immediately**:
> - `rest/fifo_queue.py`: `pop_next_eligible()` and `earliest_scheduled_at()` — timezone-aware UTC vs naive local comparison caused `TypeError`, caught by blanket `except`, treating scheduled jobs as immediate. Fix: `.astimezone().replace( tzinfo=None )` normalizes to naive-local
>
> **Files Created (4)**: `rest/job_state.py`, `agents/test_suite/{__init__,job,voice_io,cosa_interface}.py`, `rest/routers/test_suite.py`
> **Files Modified (23)**: `queue_protocol.py`, `agentic_job_base.py`, `agent_base.py`, `solution_snapshot.py`, 9 agent jobs, `queue_util.py`, `job_persistence.py`, `fifo_queue.py`, `queue_consumer.py`, `running_fifo_queue.py`, `todo_fifo_queue.py`, `routers/queues.py`, `agentic_job_factory.py`, `agent_registry.py`, `notification_proxy/config.py`
>
> Total: +230 insertions, -131 deletions across 23 modified + 4 new files

---

> **✅ SESSIONS 383+383b+384 COMMITTED**: Presentation Generator Phase 8, DR→Presentation bridge, BFE Phases 2-4, CJ Flow scheduling, SentenceTransformer fix (2026.03.30)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 383 — Presentation Generator Phase 8 (Delivery & Chaining)**:
> - `presentation_generator/orchestrator.py`: Real `_deliver_async()` — artifact verification, delivery summary dict
> - `presentation_generator/state.py`: Added `visuals_rendered`, `delivery_summary` to initial state
> - Created `deep_research_to_presentation/` bridge module (5 files): `state.py`, `agent.py`, `job.py`, `__init__.py`, `__main__.py`
> - `rest/routers/deep_research_to_presentation.py`: REST router (`POST /api/deep-research-to-presentation/submit`)
> - `agent_registry.py`: 8th agent entry (`research_to_presentation`, prefix `rx-`)
> - `agentic_job_factory.py`: Factory branch for `research_to_presentation`
> - `job_persistence.py`: Added `presentation`, `research_to_presentation` to AGENTIC_JOB_TYPES
> - `todo_fifo_queue.py`: MODE_METADATA, AGENTIC_MODE_MAP, PRODUCT_NAMES for `research_to_presentation`
> - `notification_proxy/config.py`: 2 new test profiles + updated union profile
>
> **Session 383b — Bug Fixes + CJ Flow Scheduling UI/Voice**:
> - `local_embedding_engine.py`: Added `local_files_only=True` to SentenceTransformer (prevents Hub calls)
> - `rest/routers/claude_code_queue.py`: Added `scheduled_at` + `monopolize` fields to `ClaudeCodeQueueRequest` + pass-through
> - `runtime_argument_expeditor/expeditor.py`: Scheduling section in confirmation summary + modification parser accepts scheduling args
> - `rest/todo_fifo_queue.py`: Runtime scheduling arg extraction + voice-path normalization ("immediately"→None, "yes"→True)
>
> **Session 384 — Bug Fix Expediter Phases 2-4 (Diagnose → Propose → Fix)**:
> - `bug_fix_expediter/orchestrator.py` (new): `BFEOrchestrator` with `run_diagnosis()`, `run_proposal()`, `run_fix()`
> - `bug_fix_expediter/plan_writer.py` (new): `PlanWriter` class for structured markdown plans
> - `bug_fix_expediter/prompts/` (new): `diagnosis.py`, `proposal.py`, `fix.py` prompt templates
> - `bug_fix_expediter/config.py`: +`min_diagnosis_confidence` (0.7), +`max_file_changes_per_fix` (20)
> - `bug_fix_expediter/job.py`: Full orchestrator pipeline wiring (replaces foundation stub)
> - `bug_fix_expediter/__init__.py`: Exports for `BFEOrchestrator`, `PlanWriter`
>
> **Files Created (12)**: `orchestrator.py`, `plan_writer.py`, `prompts/{__init__,diagnosis,proposal,fix}.py`, `deep_research_to_presentation/{__init__,__main__,state,agent,job}.py`, `routers/deep_research_to_presentation.py`
> **Files Modified (13)**: `__init__.py`, `config.py`, `job.py` (BFE), `notification_proxy/config.py`, `orchestrator.py`, `state.py` (PG), `agent_registry.py`, `expeditor.py`, `local_embedding_engine.py`, `agentic_job_factory.py`, `job_persistence.py`, `claude_code_queue.py`, `todo_fifo_queue.py`
> **Commit**: 8db89ff
>
> Total: +4634 insertions, -37 deletions across 25 files

---

> **✅ SESSIONS 382+382b+382d+382e COMMITTED**: CJ Flow Phase 5 UI, Config Manager bug fix, Presentation Generator Phases 6-7, Bug Fix Expediter Phase 0.95+1 (2026.03.28)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 382 — CJ Flow Phase 5: Notifications UI + WebSocket Integration**:
> - `rest/routers/queues.py`: Added WebSocket emission (`job_paused`/`job_resumed`) to pause/resume endpoints
> - `rest/todo_fifo_queue.py`: Added `scheduled_at`, `monopolize`, `paused` to push metadata (cards created from WS events were missing these fields)
>
> **Session 382b — Bug Fix: Config Manager Visual Grouping**:
> - `config/configuration_manager.py`: Fixed `key.split( "_" )[ 0 ]` → `key.split()[ 0 ]` — blank lines inserted between every key instead of only between prefix groups after space-separated key convention change
>
> **Session 382d — Presentation Generator Phases 6-7**:
> - Phase 6 (Marp Text Rendering): Created `MarpTextRenderer` — stateless `@staticmethod` class converting `PresentationModel` → Marp Markdown. Frontmatter, slide type dispatch, presenter notes, visual placeholders. Default theme file (`templates/themes/default.yaml`). Orchestrator integration: `_render_text_async()` + `_load_theme_config()` + `_write_marp()`
> - Phase 7 (Visual Rendering): Created `VisualRenderer` ABC + `VisualRendererRegistry` — type dispatch with PlaceholderRenderer fallback. `MermaidRenderer` — LLM-backed Mermaid code generation via Claude API. `PlaceholderRenderer` — visible TODO markers. `prompts/visual.py` — Mermaid system prompt + diagram type hints. `call_for_mermaid()` added to `PresentationAPIClient`. Orchestrator: `_render_visuals_async()` + Gate 4.
> - Files created: `renderers/marp_text_renderer.py`, `renderers/visual_registry.py`, `renderers/placeholder.py`, `renderers/mermaid.py`, `prompts/visual.py`, `templates/themes/default.yaml`
> - Files modified: `renderers/__init__.py`, `prompts/__init__.py`, `orchestrator.py`, `api_client.py`
>
> **Session 382e — Bug Fix Expediter Phase 0.95 (Model Update) + Phase 1 (Foundation)**:
> - Phase 0.95: Updated all agentic job model defaults from `claude-opus-4-20250514`/`claude-sonnet-4-20250514` to `claude-opus-4-6`/`claude-sonnet-4-6`. 11 config/CLI files updated, cost tracker +3 model tiers
> - Phase 1: Created `agents/bug_fix_expediter/` package (7 files): `__init__.py`, `config.py`, `state.py`, `cosa_interface.py`, `voice_io.py`, `dead_job_packager.py`, `job.py`. Created `rest/routers/bug_fix_expediter.py`. Registered in `agent_registry.py`, `agentic_job_factory.py`, `job_persistence.py`
>
> **Files Created (14)**:
> - `agents/bug_fix_expediter/__init__.py`, `config.py`, `state.py`, `cosa_interface.py`, `voice_io.py`, `dead_job_packager.py`, `job.py`
> - `agents/presentation_generator/renderers/marp_text_renderer.py`, `visual_registry.py`, `placeholder.py`, `mermaid.py`
> - `agents/presentation_generator/prompts/visual.py`
> - `agents/presentation_generator/templates/themes/default.yaml`
> - `rest/routers/bug_fix_expediter.py`
>
> **Files Modified (21)**: `deep_research/cli.py`, `deep_research/config.py`, `cost_tracker.py`, `deep_research_to_podcast/__main__.py`, `deep_research_to_podcast/agent.py`, `notification_proxy/config.py`, `podcast_generator/config.py`, `test_podcast_generator.py`, `presentation_generator/api_client.py`, `presentation_generator/config.py`, `presentation_generator/orchestrator.py`, `prompts/__init__.py`, `renderers/__init__.py`, `agent_registry.py`, `swe_team/__main__.py`, `swe_team/config.py`, `configuration_manager.py`, `agentic_job_factory.py`, `job_persistence.py`, `routers/queues.py`, `todo_fifo_queue.py`
>
> Total: +467 insertions, -42 deletions across 21 modified + 14 new files

---

> **✅ SESSIONS 381b+381c COMMITTED**: CJ Flow Timed Execution + Monopolize + Pause/Resume (backend Phases 0-4), Agentic Job Consistency Remediation (2026.03.27)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 381b — CJ Flow: Timed Execution + Monopolize + Pause/Resume (Backend)**:
> - `rest/queue_protocol.py`: Added `scheduled_at`, `monopolize`, `paused` fields to QueueableJob protocol
> - `agents/agentic_job_base.py`, `agents/agent_base.py`, `memory/solution_snapshot.py`: Added 3 new protocol fields to all implementations
> - `rest/fifo_queue.py`: New `pop_next_eligible()` scans for eligible jobs (not paused, scheduled time reached); `earliest_scheduled_at()` calculates dynamic wake-up timeout; `delete_by_id_hash()` override notifies consumer on removal
> - `rest/queue_consumer.py`: Full rewrite — replaces `pop()` with `pop_next_eligible()`, dynamic `condition.wait(timeout=...)` for timed jobs, all-paused guard, monopolize placeholder
> - `rest/todo_fifo_queue.py`: Pause/resume methods with consumer notification
> - `rest/routers/queues.py`: New `PATCH /api/queue/todo/{id}/pause` and `/resume` endpoints; queue GET serialization updated
> - `rest/routers/deep_research.py`, `podcast_generator.py`, `presentation_generator.py`, `swe_team.py`, `mock_job.py`: Added `scheduled_at`/`monopolize` request fields to all 5 routers
> - `rest/job_persistence.py`: `scheduled_at` + `monopolize` added to JSONB metadata extraction
> - `rest/running_fifo_queue.py`: Added `scheduled_at`/`monopolize` to dead-job metadata
>
> **Session 381c — Agentic Job Consistency Remediation**:
> - `agents/swe_team/job.py`: Added `set_job_id()`/`clear_job_id()` in live execution path
> - `agents/swe_team/config.py`: Added `from_config()` classmethod for INI-driven configuration
> - `agents/podcast_generator/job.py`: Added `queue_name="run"` to all 8 notify calls (live + dry-run)
> - `agents/claude_code/job.py`: Added `queue_name="run"` to all 13 `notify_progress()` calls
> - `agents/presentation_generator/job.py`: Added `queue_name="run"` to all 9 notify calls (live + dry-run)
> - `agents/test_harness/mock_job.py`: Updated with protocol fields and consistency fixes
>
> **Files Modified (22)**:
> - `rest/queue_protocol.py` (+16) — 3 new protocol fields
> - `agents/agentic_job_base.py` (+8) — Protocol field implementations
> - `agents/agent_base.py` (+5) — Protocol field implementations
> - `memory/solution_snapshot.py` (+5) — Protocol field implementations
> - `rest/fifo_queue.py` (+76) — `pop_next_eligible()`, `earliest_scheduled_at()`, `delete_by_id_hash()` override
> - `rest/queue_consumer.py` (+49/-4) — Full consumer loop rewrite with dynamic wake-up
> - `rest/todo_fifo_queue.py` (+25/-1) — Pause/resume methods
> - `rest/routers/queues.py` (+119) — Pause/resume endpoints, serialization updates
> - `rest/routers/deep_research.py` (+6) — scheduled_at/monopolize fields
> - `rest/routers/podcast_generator.py` (+12/-1) — scheduled_at/monopolize fields
> - `rest/routers/presentation_generator.py` (+8/-1) — scheduled_at/monopolize fields
> - `rest/routers/swe_team.py` (+6) — scheduled_at/monopolize fields
> - `rest/routers/mock_job.py` (+6) — scheduled_at/monopolize fields
> - `rest/job_persistence.py` (+3/-1) — Metadata extraction for new fields
> - `rest/running_fifo_queue.py` (+2) — Dead-job metadata fields
> - `agents/swe_team/config.py` (+69/-1) — `from_config()` classmethod
> - `agents/swe_team/job.py` (+31/-5) — `set_job_id`/`clear_job_id` + INI-driven config
> - `agents/claude_code/job.py` (+39/-4) — `queue_name="run"` on all 13 notify calls
> - `agents/podcast_generator/job.py` (+18/-3) — `queue_name="run"` on all 8 notify calls
> - `agents/presentation_generator/job.py` (+37/-4) — `queue_name="run"` on all 9 notify calls
> - `agents/test_harness/mock_job.py` (+17/-2) — Protocol fields + consistency fixes
> - `agents/deep_research/job.py` (+6/-1) — Cost summary in artifacts
> - Total: +487 insertions, -76 deletions

---

> **✅ SESSIONS 376+378 COMMITTED**: Presentation Generator bug fixes (dry-run, cost attr, completion abstract, Docker notifications), PredictionEngine test isolation endpoint, API key strip fix (2026.03.26)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 376 — Bug Fixes: Presentation Generator + Docker Notifications**:
> - `agents/presentation_generator/job.py`: Wired `_execute_dry_run()` call in `_execute()` (was dead code — dry run went through orchestrator without identity setup, causing `is_voice_available()` to cache False). Added identity setup (`SENDER_ID`, `TARGET_USER`) + `try/finally` cleanup in dry-run path.
> - `agents/presentation_generator/job.py`: Fixed `estimated_cost_usd` AttributeError — wrong attribute chain `agent.api_client.estimated_cost_usd` → `agent.api_client.cost_estimate.estimated_cost_usd`
> - `agents/presentation_generator/job.py`: Added completion abstract with clickable `/app/docs?path=` links (matching podcast pattern), `report_path` pointing to Marp output, `voice_io.notify()` with `queue_name="run"` for job card routing
> - `utils/config_loader.py`: Added `LUPIN_API_KEY` env var support — direct key value bypasses config file lookup (for Docker/CI where `~/.lupin/config` unavailable). Updated `get_api_config()` conditional logic and `load_api_key()` priority chain.
>
> **Session 378 — UPE LanceDB Test Isolation + Warm Test Fix**:
> - `rest/routers/system.py`: Added `PredictionEngine.reset()` + `get_prediction_engine()` to `/api/init` hot-swap endpoint
> - `rest/routers/system.py`: Created new `GET /api/prediction-engine/reset` lightweight endpoint — drops LanceDB table + resets singleton. Needed because test process can't drop root-owned LanceDB files and `/api/init` is too heavy per-test (causes 429 rate limiting)
> - `utils/util.py`: Fixed `get_api_key()` returning file contents with trailing `\n` — HTTP headers reject newlines. Added `.strip()` at source (system boundary normalization)
>
> **Files Modified (4)**:
> - `agents/presentation_generator/job.py` (+96/-52) — Dry-run wiring, cost attr fix, completion abstract + links
> - `rest/routers/system.py` (+61) — PredictionEngine reset in /api/init + new /api/prediction-engine/reset endpoint
> - `utils/config_loader.py` (+13/-5) — LUPIN_API_KEY env var for Docker
> - `utils/util.py` (+1/-1) — get_api_key() .strip() fix
> - Total: +177 insertions, -52 deletions

---

> **✅ SESSIONS 372-374 COMMITTED**: Voice injection bug fix, session_name pipeline, Presentation Generator mode map (2026.03.25)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 372 — Bug Fix: Voice Injection Silent Crash on Null Title**:
> - `rest/notification_fifo_queue.py`: Changed `title: Optional[str] = None` → `title: str = ""` and `abstract: Optional[str] = None` → `abstract: str = ""` in both `NotificationItem.__init__()` and `push_notification()` — prevents `startswith()` crash when title is None
> - `rest/routers/notifications.py`: Added API boundary normalization (`title = title or ""`, `abstract = abstract or ""`) to catch None from absent query params
> - `agents/utils/proxy_agents/base_listener.py`: Enhanced error logging — checks for `_log` method before falling back to `print()`
>
> **Session 372b — session_name Pipeline (set_session_topic → UI Header)**:
> - `rest/notification_fifo_queue.py`: Added `session_name: Optional[str] = None` parameter to `NotificationItem` and `push_notification()`, included in `to_dict()` serialization
> - `rest/routers/notifications.py`: Added `session_name` query parameter to `/api/notify`, added `"session_topic"` to valid notification types, plumbed `session_name` through to `push_notification()`
>
> **Session 374 — Presentation Generator CJ Flow Mode Map**:
> - `rest/todo_fifo_queue.py`: Added `"presentation"` entry to `MODE_METADATA` and `AGENTIC_MODE_MAP` — agent now visible in UI mode selector and routable through CJ Flow
>
> **Files Modified (4)**:
> - `agents/utils/proxy_agents/base_listener.py` (+6/-1) — Enhanced error logging
> - `rest/notification_fifo_queue.py` (+24/-8) — title/abstract defaults, session_name field
> - `rest/routers/notifications.py` (+10/-2) — session_name param, session_topic type, boundary normalization
> - `rest/todo_fifo_queue.py` (+2) — Presentation Generator mode map entries
> - Total: +42 insertions, -11 deletions

---

> **✅ SESSIONS 369-371c COMMITTED**: Presentation Generator Phases 3-5, CJ Flow Persistence Phase 6, WebSocket bug fixes (2026.03.24)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 370 — Presentation Generator Phase 3 (Expeditor + Ingest + Narrative Analysis)**:
> - `agents/presentation_generator/__main__.py`: Full CLI rewrite with `--user-visible-args` expeditor protocol, dry-run mode
> - `agents/presentation_generator/api_client.py` (NEW): `AsyncAnthropic` client with exponential backoff retry, per-request cost tracking (Opus/Sonnet pricing), 3 call methods (analysis, outline, elaboration)
> - `agents/presentation_generator/prompts/narrative.py` (NEW): Narrative arc analysis system prompt, prompt builder with slide budget, JSON response parser with fallback
> - `agents/presentation_generator/orchestrator.py`: `_ingest_async()` (markdown section parser, plain text paragraph parser, format auto-detection), `_analyze_async()` (Claude call → parse → NarrativeSection), Gate 1 voice review
> - `agents/presentation_generator/state.py`: `NarrativeSection`, `NarrativeAnalysis` Pydantic models
> - `agents/runtime_argument_expeditor/agent_registry.py`: Registry entry for presentation generator (6 agents total)
> - `agents/runtime_argument_expeditor/expeditor.py`: Agent-aware `fuzzy_file_match` lookup
> - `agents/notification_proxy/config.py`: Presentation generator proxy profile
>
> **Session 371 — CJ Flow Persistence Phase 6 (Job History UI)**:
> - `rest/job_persistence.py`: Extended `query_job_history()` with `days` and `exclude_ids` filters, added `delete_job_history()`
> - `rest/routers/queues.py`: `DELETE /api/job-history/{job_id}`, `POST /api/job-history/{job_id}/retry`, updated `GET` params
>
> **Session 371b — Bug Fix: Action-Required Card Stuck + WS Send-After-Close Crash**:
> - `rest/routers/websocket.py`: Explicit `except WebSocketDisconnect` before generic handler (Fix 4), wrapped outer handler's `close()` in try/except for safe close
>
> **Session 371c — Presentation Generator Phases 4-5 (Outline, Elaborate, Serialize)**:
> - `agents/presentation_generator/prompts/outline.py` (NEW): Outline generation prompt
> - `agents/presentation_generator/prompts/elaboration.py` (NEW): Elaboration prompt for slide content
> - `agents/presentation_generator/prompts/__init__.py`: Module exports for new prompts
> - `agents/presentation_generator/orchestrator.py`: `_outline_async()`, `_elaborate_async()` with chunked fallback, `_serialize_async()` with thread-pool file I/O, Gate 2 + Gate 3 voice review, cost summary
> - `agents/presentation_generator/state.py`: `SlideOutline` model, `to_yaml()`/`from_yaml()` on `PresentationModel`
> - `agents/presentation_generator/job.py`: `audience_context` field
> - `rest/agentic_job_factory.py`: Updated factory for audience_context
> - `rest/todo_fifo_queue.py`: Presentation generator routing
>
> **Files Modified (13) + New (4)**:
> - 13 modified files across agents, rest, and routers
> - 4 new files in `agents/presentation_generator/`
> - Total: +1,710 insertions, -117 deletions

---

> **✅ SESSIONS 365-368 COMMITTED**: Admin filter, Presentation Generator, CJ Flow persistence wiring, bug fixes (2026.03.23)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 365 — CUDA Memory Optimization (Embedding OOM Retry)**:
> - `memory/local_embedding_engine.py`: Added `_run_with_cuda_retry()` — on CUDA OOM, runs `gc.collect()` + `torch.cuda.empty_cache()` then retries once. Multi-batch warmup support.
>
> **Session 366 — 5 Bug Fixes (WebSocket, LanceDB, Config Keys, Phantom Connection)**:
> - `agents/decision_proxy/proxy_decision_embeddings.py`: Schema validation in `_ensure_table()` — drop+recreate on column mismatch (fixes `response_type` field missing from pre-existing tables)
> - `rest/routers/websocket.py`: Identity guard in finally blocks — old handler's `disconnect()` no longer kills new connection on reconnect. TokenExpiredException handling added.
> - `rest/websocket_manager.py`: Dedup `user_sessions` in `connect()`, orphan cleanup in `emit_to_user()`, explicit `ws.close()` in `disconnect()` to prevent phantom connections
> - `rest/routers/system.py`: Fixed 4 config key underscore/space mismatches in `/api/config/client` + added `return_type="int"` to prevent string multiplication
>
> **Session 367 — Notification Admin Filter Toggle ("Not My Jobs" Mode)**:
> - `rest/queue_auth.py`: Added `!self` authorization case (Case 2b) — admins can view jobs NOT belonging to them
> - `rest/fifo_queue.py`: Added `get_jobs_excluding_user()` method
> - `rest/routers/queues.py`: Wired `!`-prefix sentinel to exclusion method
> - `rest/routers/notifications.py`: Added `exclude_own_jobs` param on senders-visible and bulk-delete endpoints
> - `rest/db/repositories/notification_repository.py`: Added `exclude_job_ids` filtering in sender listing + bulk delete
>
> **Session 367b — Presentation Generator Agent (Phases 1-2 Foundation)**:
> - `agents/presentation_generator/` (NEW — 10 files): `PresentationGeneratorJob` (AgenticJobBase), `PresentationConfig` with `from_config()`, 6 Pydantic state models, `PresentationOrchestratorAgent` (8-phase state machine), cosa_interface.py, voice_io.py
> - `rest/routers/presentation_generator.py` (NEW): REST router at `/api/presentation-generator/submit`
> - `rest/agentic_job_factory.py`: Factory branch for presentation generator
>
> **Session 367d — CJ Flow Persistence (Phases 3-5 Write-Through + Recovery + API)**:
> - `rest/queue_util.py`: Wired `job_persistence.py` into `emit_job_state_transition()` — persistence fires after WS emit, filtered by `is_agentic_job_type()`. Changed `websocket_mgr=None` from early-return to conditional guard.
> - `rest/routers/queues.py`: Added `GET /api/job-history` (paginated, role-based) and `GET /api/job-history/{job_id}` (detail with 403/404)
>
> **Session 368 — Bug Fix: WebSocket 503 "user_not_available" Notifications**:
> - `rest/routers/notifications.py`: Added ungated OFFLINE DIAG dump for debugging user-not-available failures
> - `rest/websocket_manager.py`: Added `[WS] STATE` summary logs after connect/disconnect
> - `rest/routers/websocket.py`: Added auth_request handler to audio WS endpoint (~40 lines)
>
> **Other Router Standardization** (Sessions 365-368):
> - Standardized auth imports and dependency injection across routers: `auth.py`, `claude_code.py`, `claude_code_queue.py`, `decision_proxy.py`, `deep_research.py`, `embeddings.py`, `io_files.py`, `jobs.py`, `mock_job.py`, `mode.py`, `speech.py`, `stats.py`, `swe_team.py`, `websocket_admin.py`
>
> **Files Modified (26) + New (10+1)**:
> - 26 modified files across agents, memory, rest, and routers
> - 10 new files in `agents/presentation_generator/`
> - 1 new router `rest/routers/presentation_generator.py`
> - Total: +899 insertions, -155 deletions

---

> **✅ SESSIONS 359-364 COMMITTED**: Config migration, CJ Flow persistence, CUDA OOM fix, WS logging guard (2026.03.14)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 364 — Claude Agent SDK Config Migration (Phases 0-4)**:
> - `deep_research/config.py`: Added `ResearchConfig.from_config( config_mgr )` classmethod — reads 24 fields from INI with type coercion, falls back to dataclass defaults
> - `deep_research/job.py`: Updated to use `ResearchConfig.from_config()` with job arg overrides
> - `deep_research/cli.py`: Updated to use `from_config()` with CLI arg overrides
> - `podcast_generator/config.py`: Added `HostPersonality.from_config()`, `VoiceProfile.from_config()`, `PodcastConfig.from_config()` — nested composition with pipe-delimited list parsing for `typical_phrases` (27 keys)
> - `podcast_generator/job.py`: Updated to use `PodcastConfig.from_config()` with job arg overrides
> - `llm_client_factory.py`: Replaced hardcoded `VENDOR_URLS`, `VENDOR_API_ENV_VARS`, `CLIENT_DEFAULT_PARAMS` class dicts with instance methods loading from INI at singleton init (10 keys)
>
> **Session 360 — CJ Flow Persistence (Phases 1-2)**:
> - `rest/postgres_models.py`: Added `JobHistory` SQLAlchemy model — 16 columns, 5 indexes for tracking agentic job lifecycle
> - `rest/job_persistence.py` (NEW): Stateless persistence service with 8 functions (INSERT/UPDATE/query/recovery). Fire-and-forget error handling.
>
> **Session 359 — Bug Fix: Periodic CUDA OOM on Whisper Transcription**:
> - `rest/routers/speech.py`: Added `_run_whisper_with_retry()` — on CUDA OOM, runs `gc.collect()` + `torch.cuda.empty_cache()` then retries once. Returns 503 with `Retry-After: 5` on persistent failure.
>
> **Session 363 — WS-QUEUE Verbose Logging Guard**:
> - `rest/routers/websocket.py`: Gated `[WS-QUEUE] Received message from` print behind `app_debug and app_verbose` — stops sys_pong flood from cc-listener sessions
>
> **Files Modified (9) + New (1)**:
> - `agents/deep_research/config.py` (+98 lines) — `from_config()` classmethod
> - `agents/deep_research/job.py` (+29/-13 lines) — Use `from_config()`
> - `agents/deep_research/cli.py` (+16/-4 lines) — Use `from_config()`
> - `agents/podcast_generator/config.py` (+178 lines) — Nested `from_config()` classmethods
> - `agents/podcast_generator/job.py` (+18/-4 lines) — Use `from_config()`
> - `agents/llm_client_factory.py` (+95/-26 lines) — INI-based vendor config
> - `rest/postgres_models.py` (+129 lines) — `JobHistory` model
> - `rest/job_persistence.py` (NEW, ~200 lines) — Persistence service
> - `rest/routers/speech.py` (+85/-20 lines) — Whisper CUDA OOM retry
> - `rest/routers/websocket.py` (+1/-1 lines) — Logging guard

---

> **✅ SESSIONS 349-356 COMMIT**: INI key standardization, document viewer/audio player routes, SWE team notification fix (2026.03.13)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 349 — Standardize ~91 Underscore Config Keys to Space-Separated**:
> - Renamed all underscore config keys to space-separated naming across 45 CoSA files (agents, memory, REST, tests, training, utils, config)
> - Key regroupings: `auto_debug` → `debug auto`, `inject_bugs` → `debug inject bugs`, `database_path_wo_root` → `path to database wo root`, `code_execution_file_path` → `path to code execution file`
> - Commented out singleton reuse debug print in `configuration_manager.py`
> - Fixed 5 false positives where Python attribute names were incorrectly renamed as config keys
> - Full regression green: unit 2094/2094, WebSocket 50/50, integration 136 passed
>
> **Sessions 353-354 — Document Viewer + Audio Player Routes & Link Migration**:
> - `pages.py`: Added `/app/docs` and `/app/audio` route table entries + route functions
> - `orchestrator.py`: Migrated 10 link URLs from `/api/io/file?path=` → `/app/docs?path=` (markdown) and `/app/audio?path=` (MP3)
> - `cli.py`: Changed local-path deep research report URL from hardcoded `http://localhost:7999/api/deep-research/report` → relative `/app/docs?path=deep-research/`
>
> **Session 356 — SWE Team Notification Routing Bug Fix**:
> - `swe_team/job.py`: Added `cosa_interface.TARGET_USER = self.user_email` in both live and dry-run execution paths — notifications now route to job submitter instead of personal email
> - `fifo_queue.py`: Replaced hardcoded `ricardo.felipe.ruiz@gmail.com` fallback with `LUPIN_DEV_EMAIL` env var; skips notification if env var unset
>
> **Files Modified (50)**:
> - 45 files: INI config key renames (agents, memory, REST, tests, training, utils, config)
> - `rest/routers/pages.py` — `/app/docs` + `/app/audio` routes (+10 lines)
> - `agents/podcast_generator/orchestrator.py` — 10 link URL migrations (+10/-10 lines)
> - `agents/deep_research/cli.py` — 1 local-path URL migration (+1/-1 lines)
> - `agents/swe_team/job.py` — TARGET_USER assignment (+2/-1 lines)
> - `rest/fifo_queue.py` — env var email fallback (+6/-3 lines)

---

> **✅ SESSION 354 COMMIT**: Audio Player Viewer — in-browser MP3 playback page (2026.03.13)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 354 — Audio Player Viewer: In-Browser MP3 Playback Page**:
> - Created `audio-player.html` (Lupin parent): Styled HTML5 `<audio>` player page mirroring document-viewer architecture — same nav bar, CSS patterns, container layout; includes title derivation from filename, companion `-script.md` metadata lookup, HEAD request for file size, download button, collapsed file details accordion
> - `pages.py`: Added `/app/audio` route table entry + `page_audio()` route function
> - `orchestrator.py`: Migrated last 2 MP3 link URLs from `/api/io/file?path=` → `/app/audio?path=` so podcast MP3 links open in styled player instead of triggering raw download
>
> **Files Modified (2 COSA + 1 Lupin)**:
> - `rest/routers/pages.py` — `/app/audio` route (+5 lines)
> - `agents/podcast_generator/orchestrator.py` — 2 MP3 link URLs migrated to `/app/audio` (+2/-2 lines)
> - `src/fastapi_app/static/html/audio-player.html` (Lupin) — New file (~140 lines HTML/CSS/JS)

---

> **✅ SESSION 353 COMMIT**: Markdown Document Viewer Phase 2 — frontmatter fix + link URL migration (2026.03.13)
> **Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 353 — Document Viewer Phase 2: Frontmatter Accordion + Link Migration**:
> - `document-viewer.html` (Lupin parent): Added `extractFrontmatter()` to strip YAML frontmatter before marked.js parsing; renders metadata as collapsed `<details>` accordion with CSS grid definition list
> - `orchestrator.py`: Migrated 8 markdown link URLs from `/api/io/file?path=` → `/app/docs?path=` so "View Script" / "View Research" links open in the formatted viewer; kept 2 MP3 links on `/api/io/file` for direct download
> - `cli.py`: Changed local-path deep research report URL from hardcoded `http://localhost:7999/api/deep-research/report?path=` → relative `/app/docs?path=deep-research/`; GCS paths kept on old endpoint
>
> **Files Modified (2 COSA + 1 Lupin)**:
> - `agents/podcast_generator/orchestrator.py` — 8 link URLs migrated to `/app/docs` (+8/-8 lines)
> - `agents/deep_research/cli.py` — 1 local-path URL migrated (+1/-1 lines)
> - `src/fastapi_app/static/html/document-viewer.html` (Lupin) — Frontmatter accordion (~55 lines added)

---

> **✅ v0.1.5 PR & MERGE**: PR #17 merged to main, tagged v0.1.5, new branch v0.1.6 created (2026.03.12)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work` → merged → deleted
>
> ### Accomplishments
>
> **v0.1.5 Release — PR & Branch Lifecycle**:
> - Updated README.md with v0.1.5 "What's New" section (Trust Proxy, UPE, Integration Test Infra, CJ Flow, new agents, testing expansion)
> - Created PR #17 via `gh pr create` with comprehensive description (28 commits, 112 files, +13,355/-7,742 lines)
> - Merged to main, verified tag `v0.1.5`, deleted old branch (local + remote)
> - Created new development branch `wip-v0.1.6-2026.03.12-tracking-lupin-work`
>
> **Files Modified (1)**:
> - `README.md` — Replace stale v0.7.0 content with v0.1.5 features (+60/-98 lines)

---

> **✅ SESSIONS 340-348 COMMIT**: UPE response_type filtering, integration test hot-swap infrastructure (2026.03.12)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Sessions 340-348 — UPE Response-Type Filtering + Integration Test Infrastructure**:
> - `proxy_decision_embeddings.py`: Added `response_type` field to LanceDB schema, `add_decision()`, and `find_similar()` — prevents cross-type contamination in CBR lookups
> - `prediction_engine.py`: All 4 prediction slices (yes_no, multiple_choice, open_ended, open_ended_batch) now filter by `response_type`; new `_extract_valid_options()` validates MC predictions against available option labels; bare strings wrapped for MC storage compatibility
> - `database.py`: New `swap_database()` hot-swap function for runtime environment switching; DB defaults disambiguated (`lupin_db_dev`/`lupin_db_prod`)
> - `system.py`: New `GET /api/server-info` endpoint for infrastructure monitoring; enhanced `/api/init` with optional `config_block_id` query param for runtime config + DB swap
>
> **Files Modified (4)**:
> - `agents/decision_proxy/proxy_decision_embeddings.py` — Add `response_type` field + filter (+12/-2 lines)
> - `agents/prediction_engine/prediction_engine.py` — Response-type filtering + MC option validation (+157/-14 lines)
> - `rest/db/database.py` — `swap_database()` + DB name disambiguation (+41/-2 lines)
> - `rest/routers/system.py` — `/api/server-info` + enhanced `/api/init` (+112/-46 lines)

---

> **✅ SESSIONS 337-339 COMMIT**: Harden config_loader, strict project detection, session ID regex (2026.03.11)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Sessions 337-339 — v0.1.5 Hardening**:
> - `config_loader.py`: Removed legacy `~/.notifications/config` fallback and hardcoded defaults; `~/.lupin/config` now required (`FileNotFoundError` if missing)
> - `notification_utils.py`: Added `KNOWN_PROJECTS` registry + `is_known_project()` for strict MCP project detection, 3 smoke tests
> - `websocket.py`: Tightened programmatic session ID regex to require hyphen
>
> **Files Modified (3)**:
> - `utils/config_loader.py` — Remove legacy fallback, require `~/.lupin/config` (+56/-83 lines)
> - `utils/notification_utils.py` — Add `KNOWN_PROJECTS` registry + `is_known_project()` (+51 lines)
> - `rest/routers/websocket.py` — Tighten session ID regex (+1/-1 lines)

---

> **✅ SESSION 337c COMMIT**: Credential store consolidation — swap config_loader.py primary/legacy paths (2026.03.10)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 337c — Credential Store Consolidation (config_loader.py)**:
> - Swapped primary/legacy config paths: `~/.lupin/config` is now primary, `~/.notifications/config` is legacy fallback
> - Updated docstring to reflect new precedence order
> - Renamed variables: `new_config_path`/`old_config_path` → `primary_config_path`/`legacy_config_path`
> - Removed unused `using_deprecated_path` variable
> - Added `lupin-config migrate` hint to deprecation warning message
>
> **Files Modified (1)**:
> - `utils/config_loader.py` — Swapped primary/legacy credential config paths (+13/-14 lines)

---

> **✅ SESSIONS 331-332 COMMIT**: Remove dead `active_conversation_changed` event, qualifier extraction consolidation (2026.03.09)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 331 — Remove Dead `active_conversation_changed` WebSocket Event**:
> - Removed two `active_conversation_changed` emission blocks from `notifications.py` — server emitted this event but it was never in INI available events or JS subscriptions, making it dead code
>
> **Session 332 — Qualifier Extraction Consolidation into notification_utils.py**:
> - Added `extract_qualifier_comment()` — regex-based parser for `yes [comment: ...]` / `no [comment: ...]` response format, returns `( answer, qualifier )` tuple
> - Added `format_qualified_response()` — formats answer + qualifier into enriched string with explicit instructions for Claude to act on the user's comment
> - Added smoke tests (Tests 9-10) for both new functions
> - Added `import re` to support regex parsing
>
> **Files Modified (2)**:
> - `rest/routers/notifications.py` — Removed 2 dead `active_conversation_changed` emission blocks (-26 lines)
> - `utils/notification_utils.py` — Added `extract_qualifier_comment()`, `format_qualified_response()`, smoke tests (+75/-1 lines)

---

> **✅ SESSIONS 328-330 COMMIT**: R2P notification fixes, TARGET_USER handoff, PG audio progress, WebSocket diagnostics, job card bug fixes (2026.03.08)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 328 Checkpoint 1 — CJ Flow Job Card Bug Fixes + Packaging Guide**:
> - Fixed user messages in running job cards rendering as gray activity-log instead of blue chat bubbles
> - Fixed cancel button not removed on job card transition to done/dead
> - Fixed R2P sender_id validation error — changed `self.id_hash` to `self.base_id` for sender_id construction
> - Removed double truncation in job card `last_question_asked` — Python-side no longer truncates, JS handles display
>
> **Session 328 Checkpoint 2 — Fix Missing TARGET_USER in R2P Job**:
> - Added `cosa_interface.TARGET_USER = self.user_email` in both `_execute()` and `_execute_dry_run()`
>
> **Session 329 Checkpoint 1 — R2P Notification Delivery Diagnostics + Fix**:
> - Added diagnostic logging to `WebSocketManager.emit_to_user()` — exposed silent failure points
> - Fixed missing `self.debug` attribute in `WebSocketManager.__init__()`
> - Added `job_id=self.id_hash` and `queue_name="run"` to all 14 `voice_io.notify()` calls in R2P job.py
> - Added `voice_io.set_job_id()` / `voice_io.clear_job_id()` lifecycle in R2P `_execute()` and `_execute_dry_run()`
>
> **Session 329 Checkpoint 2 — Fix R2P → PG Handoff Missing TARGET_USER on Agent**:
> - Added `pg_cosa_interface.TARGET_USER` and `dr_cosa_interface.TARGET_USER` in agent.py before each phase
> - Replaced bare DR completion notification with rich checkpoint showing report path, abstract, cost, tokens, duration
> - Added `**kwargs` pass-through to `_notify()` helper so `abstract=` reaches `voice_io.notify()`
>
> **Session 330 — Fix PG Audio Progress Not Updating In-Place**:
> - Added `progress_group_id = self._audio_progress_group_id` to Phase 5 English audio start notification
>
> **Additional changes committed**:
> - DR cli.py: Added user interaction breadcrumb notifications (clarification, theme selection, topic refinement, plan approval, partial report)
> - DR job.py: Always print tracebacks on failure (not just debug mode), include traceback in error field, CostTracker with session_id + budget_limit_usd
> - queues.py: Fixed `user_id_db` scope — captured `user.id` inside DB session before using outside it
>
> **Files Modified (8)**:
> - `agents/deep_research/cli.py` — User interaction breadcrumb notifications (+30 lines)
> - `agents/deep_research/job.py` — Full traceback on failure, CostTracker params, removed truncation (+24/-12)
> - `agents/deep_research_to_podcast/agent.py` — TARGET_USER on both cosa_interfaces, rich DR checkpoint, `_notify()` kwargs (+21/-4)
> - `agents/deep_research_to_podcast/job.py` — sender_id base_id fix, job_id/queue_name on all notifies, try/finally lifecycle (+158/-100)
> - `agents/podcast_generator/job.py` — Removed filename truncation (+7/-8)
> - `agents/podcast_generator/orchestrator.py` — progress_group_id on English audio start notification (+3/-2)
> - `rest/routers/queues.py` — user_id_db scope fix (+3/-1)
> - `rest/websocket_manager.py` — emit_to_user() diagnostic logging, self.debug init (+33/-18)

---

> **✅ SESSIONS 315+318 COMMIT**: QualifierClassification model, display_qualifier_widget notification field (2026.03.05)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 315 — display_qualifier_widget notification field**:
> - Threaded `display_qualifier_widget` boolean through full notification stack: `NotificationItem` constructor + `to_dict()`, `NotificationFifoQueue.push_notification()`, FastAPI query parameter in `notifications.py` router (both fire-and-forget and response-requested paths)
>
> **Session 318 — QualifierClassification BaseXMLModel**:
> - Added `QualifierClassification` model with `is_question()`/`is_instruction()` helpers, None-to-empty-string coercion, `get_example_for_template()`, and `quick_smoke_test()`
> - Registered `'qualifier classification'` key in `PromptTemplateProcessor.MODEL_MAPPING`
>
> **Files Modified (4)**:
> - `rest/notification_fifo_queue.py`
> - `rest/routers/notifications.py`
> - `agents/io_models/xml_models.py`
> - `agents/io_models/utils/prompt_template_processor.py`
>
> **Commit**: ccd3e25

---

> **✅ SESSION 309 COMMIT**: Extend is_valid_session_id() for programmatic session IDs (2026.03.04)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Session 309 — Fix Headless CC Notification Listener (Bug #2)**:
> - Extended `is_valid_session_id()` to accept programmatic session ID format (`cc-listener-{hash}`) in addition to browser "adjective noun" format
> - Added second regex pattern for lowercase alphanumeric with hyphens (3-49 chars)
> - Updated smoke test cases to cover both browser and programmatic session formats
>
> **Files Modified (1)**:
> - `rest/routers/websocket.py`
>
> **Commit**: 24983d4

---

> **✅ SESSIONS 304-308 COMMIT**: Podcast bug fixes, job_id auto-injection, graceful cancellation, voice_io reconfigure (2026.03.04)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 304-308** (24 files modified, +968/-277 lines):
>
> **Session 304 — Podcast Generator 3 Bug Fixes + target_user dispatch**:
> - Fuzzy matching: `difflib.get_close_matches()` 3rd tier + keyword pre-filter (top 50 from 1001 candidates)
> - sender_id double-hash: Fixed `_get_sender_id()` suffix param across podcast/DR/DR-to-PG
> - Audio segment upload: `_is_interactive()` guard, TTS cost key fix, pre-stitching guard
> - target_user dispatch: Router sets `cosa_interface.TARGET_USER` before `present_choices()`
>
> **Session 306 — Notification Routing + Graceful Cancellation (4 checkpoints)**:
> - job_id auto-injection: Module-level `_job_id` state in voice_io with `set_job_id()`/`clear_job_id()` lifecycle
> - TTS error visibility: Always-print failures in tts_client + error context in abstracts
> - Bug 4: "Initializing..." ping passes job_id; Bug 5: progress_group_id dedup in DONE card
> - Bug 3b: `job_id` param added to cosa_interface wrappers (podcast + deep_research)
> - Graceful cancellation: `_cancel_requested` + `request_cancel()` in AgenticJobBase, `cancel_check` callback in deep_research CLI (4 checkpoints), `POST /api/jobs/{job_id}/cancel`
> - Speculative metadata: Added `'status': 'pending'` to todo_fifo_queue expeditor
>
> **Session 308 — Fix Shared Mutable Global in voice_io**:
> - Added `reconfigure()` to 3 voice_io wrappers (podcast, deep_research, swe_team)
> - Reset `_voice_available` on `configure()` so ping re-runs with correct cosa_interface
> - Called `reconfigure()` at `_execute()` start in 3 job files + 2 router locations + DR-to-PG pipeline
>
> **Additional**:
> - Prediction hint: constructor param in NotificationItem, override query param in `/api/notify`
> - WebSocket debugging: session type (listener/browser) + email in connect/disconnect/emit
> - AgentNotificationDispatcher: `job_id` param on `get_feedback()` and `present_choices()`
>
> **Files Modified (24)**:
> - `agents/agentic_job_base.py`, `agents/deep_research/{cli,cosa_interface,job,voice_io}.py`
> - `agents/deep_research_to_podcast/{agent,job}.py`
> - `agents/podcast_generator/{cosa_interface,job,orchestrator,tts_client,voice_io}.py`
> - `agents/swe_team/{job,voice_io}.py`
> - `agents/utils/{agent_notification_dispatcher,voice_io}.py`
> - `rest/{notification_fifo_queue,todo_fifo_queue,websocket_manager}.py`
> - `rest/routers/{notifications,podcast_generator,queues,websocket}.py`
>
> **Commit**: 727c7e2

---

> **✅ SESSIONS 293-299 COMMIT**: Prediction Engine (Slices 3-5), embedding thread safety, admin CRUD, embeddings auth (2026.03.02)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 293-299** (9 files: 1 new + 8 modified, +1475/-91 lines):
>
> **Universal Prediction Engine — Slice 3: Multi-Select MC (Session 295)**:
> - Added `_tally_multi_select_votes()` method with >= 50% threshold + highest-count fallback
> - Made vote loop type-aware: detects `isinstance(option, list)` and branches to multi-select path
> - Updated `get_comparator()` with data-driven dispatch via optional `actual_value` parameter
> - Updated `record_outcome()` to pass `actual_dict` to comparator for correct multi-select dispatch
>
> **Universal Prediction Engine — Slices 4+5: Open-Ended Prediction (Session 296)**:
> - Two-tier strategy: Tier 1 exact normalized question match (`STRATEGY_CBR_RETRIEVAL`), Tier 2 LLM synthesis via local Phi-4 14B (`STRATEGY_LLM_SYNTHESIS`)
> - Added `_predict_open_ended()` and `_predict_open_ended_batch()` with 3 cold-start guards each
> - Added `_build_synthesis_prompt()`, `_get_llm_client()` lazy loader, `_cosine_similarity()` static helper
> - Added `_enrich_with_embedding_similarity()` — injects transient `_embedding_similarity` key, stripped before DB write
> - Created `OpenEndedSynthesisResponse` BaseXMLModel (`xml_models.py`) for structured LLM I/O
> - Upgraded `compare_open_ended()` with dual strategy: embedding similarity + exact match fallback
> - Added `compare_open_ended_batch()` per-header comparator with average threshold
>
> **Embedding Thread Safety (Session 293)**:
> - Added `_inference_lock = Lock()` class variable to both `CodeEmbeddingEngine` and `ProseEmbeddingEngine`
> - Applied double-checked locking to `_load_model()`, wrapped all public inference methods with the lock
> - Fixes `RuntimeError: tensor size mismatch` crash in concurrent daemon threads
>
> **HTTP Embedding Fallback (Session 294)**:
> - Added `_generate_embedding_via_http()` — falls back to `POST /api/embeddings/generate` when local GPU unavailable
> - Updated embeddings router auth from `get_current_user` to `require_api_key_or_jwt` on all 3 endpoints
> - Added `DEFAULT_EMBEDDING_FALLBACK_PORT` config constant
>
> **Admin User Management (Sessions 298-299)**:
> - Added `admin_create_user()` with auto-email-verification, `admin_delete_user()` with self-protection and sole-admin guard
> - Added `POST /admin/users`, `DELETE /admin/users/{user_id}`, `POST /admin/users/batch-delete` endpoints with Pydantic models
> - Batch delete reuses per-user delete for full safety (self-protection, sole-admin guard, token revocation, audit logging)
>
> **Files Created (1)**:
> - `agents/prediction_engine/xml_models.py`
>
> **Files Modified (8)**:
> - `agents/prediction_engine/accuracy_comparators.py`, `agents/prediction_engine/config.py`
> - `agents/prediction_engine/prediction_engine.py`
> - `memory/local_embedding_engine.py`
> - `rest/admin_service.py`, `rest/routers/admin.py`
> - `rest/routers/embeddings.py`, `rest/routers/notifications.py`

---

> **✅ SESSION 290 COMMIT**: Phase 1 Voice I/O — `user_initiated_message` type whitelist (2026.02.28)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Phase 1 Voice I/O: Notification System Extensions (Session 290)**:
> - Added `user_initiated_message` to `valid_types` whitelist in `POST /api/notify` endpoint — enables voice hook integration to inject user-initiated messages through the existing notification pipeline
>
> **Files Modified (1)**:
> - `rest/routers/notifications.py` (1 line changed)

---

> **✅ SESSIONS 277-286 COMMIT**: Universal Prediction Engine (Slices 0-1.5), target_user notification dispatch, multi-dir podcast source search (2026.02.28)
> **Branch**: `wip-v0.1.5-2026.02.16-tracking-lupin-work`
>
> ### Accomplishments
>
> **Committed accumulated work from Lupin sessions 277-286** (19 files: 7 new + 12 modified, +2115 lines):
>
> **Universal Prediction Engine — Slices 0, 1, 1.5 (Sessions 281, 284)**:
> - Created `agents/prediction_engine/` package (6 files, ~1390 lines): PredictionEngine singleton, PredictionResult dataclass, NotificationCategoryClassifier (6 categories), accuracy comparators (yes_no, multiple_choice, open_ended), config module
> - Slice 0: Foundation — CBR-based prediction with LanceDB similarity retrieval
> - Slice 1: Binary yes/no prediction via majority vote with confidence scoring
> - Slice 1.5: Qualifier comment extraction from highest-similarity winning-side cases
> - Created `PredictionLog` ORM model in postgres_models.py (UUID PK, JSONB predicted/actual values, accuracy tracking)
> - Created `prediction_log_repository.py` with accuracy summary aggregation
> - Integrated prediction hooks in notifications.py: Hook 1 generates prediction before WebSocket push, Hook 2 records outcome on response
> - Added `prediction_hint` field to NotificationItem for UI rendering
>
> **target_user Notification Dispatch (Session 286)**:
> - Added `target_user` attribute to AgentNotificationDispatcher + pass-through in 4 notification methods
> - Added `TARGET_USER` module variable to 4 cosa_interface.py files (claude_code, deep_research, podcast_generator, swe_team)
> - Wired `cosa_interface.TARGET_USER = self.user_email` in 2 job.py files (deep_research, podcast_generator)
> - Added smoke tests for target_user default and mutability
>
> **Multi-Directory Podcast Source Search (Session 280)**:
> - Expanded `_handle_fuzzy_file_match()` in expeditor.py to search multiple directories from config key `podcast generator source search paths`
> - Expanded podcast_generator.py: `is_research_path()` accepts general file paths (.md/.txt/.html), `validate_source_path()` prevents directory traversal, `match_research_docs()` returns `List[dict]` with relative_path keys, `get_user_document_selection()` displays relative paths
> - Updated smoke tests for new path detection and validation functions
>
> **Files Created (7)**:
> - `agents/prediction_engine/__init__.py`, `config.py`, `prediction_result.py`
> - `agents/prediction_engine/notification_category_classifier.py`, `accuracy_comparators.py`, `prediction_engine.py`
> - `rest/db/repositories/prediction_log_repository.py`
>
> **Files Modified (12)**:
> - `agents/claude_code/cosa_interface.py`, `agents/deep_research/cosa_interface.py`
> - `agents/deep_research/job.py`, `agents/podcast_generator/cosa_interface.py`
> - `agents/podcast_generator/job.py`, `agents/runtime_argument_expeditor/expeditor.py`
> - `agents/swe_team/cosa_interface.py`, `agents/utils/agent_notification_dispatcher.py`
> - `rest/notification_fifo_queue.py`, `rest/postgres_models.py`
> - `rest/routers/notifications.py`, `rest/routers/podcast_generator.py`

---

## Archive Navigation

### Monthly Archives
- **[Feb 2026 (Feb 5-26)](history/2026-02-05-to-26-history.md)** - Sessions 135-276: DataFrame CRUD, SWE Team Phases 2-4, Decision Proxy, Notification Proxy, Prediction Engine, voice refactoring, preference learning
- **[Nov 2025 - Feb 2026 (Nov 8, 2025 - Feb 3, 2026)](history/2025-11-08-to-2026-02-03-history.md)** - Sessions 56-126: Conversation Identity, Deep Research Agent, Podcast Generator, Queue Protocol, Directory Analyzer, Lupin sync entries
- **[October 2025 (Oct 4-30)](history/2025-10-history.md)** - Planning workflows, CLI modernization, history management, branch analyzer refactoring (9 sessions)
- **[June-October 2025 (Jun 27 - Oct 3)](history/2025-06-27-to-10-03-history.md)** - Authentication infrastructure, WebSocket implementation, notification system refactor, testing framework (20 sessions)

### Project Context
- **Project Span**: June 2025 - Present (COSA framework within Lupin project)
- **Current Branch**: `wip-v0.1.6-2026.03.12-tracking-lupin-work`
- **Architecture**: Collection of Small Agents (COSA) for Lupin FastAPI application
- **Parent Project**: Lupin (located at `../..`)
