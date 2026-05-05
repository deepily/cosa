# COSA Development History

### 2026.05.04 - Session 05cf78c4 | CoSA-side wrap of three Lupin parent bodies of work (Multiplexer Phase 1 page route + Voice-persona /clear preservation Phase 3 + docs viewer scope=docs endpoint)

**Context**: CoSA-context session-end commit bundle for three distinct CoSA-side bodies of work whose Lupin-parent counterparts already landed across earlier parent-context sessions on 2026-05-02 through 2026-05-04. Branch: `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Three clearly-scoped thematic commits per `feedback_lupin_only_never_cosa.md` cross-repo separation, each mapping to a named body of work in the parent Lupin `history.md` / `TODO.md` / `bug-fix-queue.md`.

**Commits Landed** (this session-end ritual): `fc86e17` (Commit A — pages.py Multiplexer Phase 1 page route), `6100372` (Commit B — voice_persona.py /clear preservation Phase 3), `e9db3e2` (Commit C — docs_files.py NEW docs viewer scope=docs endpoints), Commit D (this session-end docs commit) — hash backfilled into manifest below.

**Body 1 — Multiplexer Phase 1 page route** (Lupin parent: Multiplexer spine bundle Phase 1; reference in parent TODO.md "FIRST THING IN THE MORNING — 2026.05.05" item #1)

One CoSA file delivers the `/app/multiplexer` page route required for the parent Lupin Multiplexer rebuild to be accessible in deployment. Without this CoSA-side commit, the parent's `multiplexer.html` + multiplexer JS modules (Phases 1-4 already shipped on the parent side per parent `history.md` Session ec746144) cannot be served.

- **`rest/routers/pages.py`** — Adds `"/app/multiplexer" : "html/multiplexer.html"` to `_ROUTE_TABLE` (mirroring the `/app/notifications` line at row 26) and `page_multiplexer()` async handler (mirroring `page_notifications()` at lines 69-71). Both follow the existing `include_in_schema=False` + `_serve_file` pattern. Verified via `py_compile` + GET 200 against the live `:7999` server during parent Phase 1 implementation.

**Body 2 — Voice-persona /clear preservation Phase 3 server side** (Lupin parent: Session aacd24b4 morning of 2026-05-03; reference in parent TODO.md "FIRST THING IN THE MORNING — 2026.05.03" item #4 / Phase 3 "✅ landed Session aacd24b4")

One CoSA file delivers the server-side counterpart of Phase 3 of the voice-persona /clear preservation fix (parent-side: changes in `register_session.py` to thread the previous persona name from the SessionStart hook into the allocate URL via URL-encoded query string).

- **`rest/routers/voice_persona.py`** — Adds `previous_persona_name: Optional[str] = None` query parameter to `allocate_voice_persona_endpoint`. When this parameter is supplied AND a new persona is actually allocated (`newly_allocated=True`), an additional "Voice re-assigned: X → Y" notification is pushed via `notification_queue.push_notification(...)` so the user hears the handoff spoken in the new voice. Used by the SessionStart hook on `/clear-with-overwrite` to make voice changes audible rather than silent. Best-effort try/except: a push failure logs a warning and falls through to the standard JSON response (the bridge write already succeeded; the announcement is purely cosmetic). New optional `Optional` import already imported. Companion to parent Lupin's unit-test suite at `src/tests/unit/test_register_session_preservation.py` (8 passed + 1 xfailed).

**Body 3 — Document viewer scope=docs endpoint** (Lupin parent: Session 2c732075, 2026-05-04 PM; reference in parent `history.md` "2026.05.04 PM - Session 2c732075 | Notification abstract popup auto-sizing + document viewer scope expansion (`scope=docs`)")

One NEW CoSA file delivers the `/api/docs/file` and `/api/docs/health` endpoints serving project source-tree documentation files. Sibling to existing `io_files.py`. Without this CoSA-side commit, the parent Lupin's startup import (`from cosa.rest.routers import ... docs_files, ...` in `main.py`) fails — parent commit ALREADY landed the `app.include_router(docs_files.router)` line + the document-viewer.html scope dispatch + smoke test `src/tests/smoke/test_docs_files_endpoint.py` (7 :7999-eligible tests).

- **`rest/routers/docs_files.py`** (NEW, 176 lines) — Two endpoints:
  - `GET /api/docs/file?path=<relative_path>` — Serves text documents with whitelist + traversal protection. Whitelist enforces exact-match against `ALLOWED_FILES = {history.md, CLAUDE.md, TODO.md, README.md, bug-fix-queue.md}` OR prefix-match against `ALLOWED_PREFIXES = [src/docs/, src/rnd/, src/workflow/]`. URL-decodes the input via `unquote()`. Path normalization via `os.path.normpath()` blocks `..` traversal; resolved path must `startswith( project_root + os.sep )` to stay inside the project root. Allowed extensions in `MEDIA_TYPES`: `.md → text/markdown`, `.txt → text/plain`, `.json → application/json`, `.yaml/.yml → text/yaml`. Returns `PlainTextResponse` with the appropriate media type. Error matrix: 400 (empty path / not whitelisted / traversal / unsupported ext), 404 (file missing on disk), 500 (read failure).
  - `GET /api/docs/health` — Returns `{status, project_root, allowed_files, allowed_prefixes, media_types}` with per-entry `os.path.isfile`/`os.path.isdir` flags so the parent's smoke test can detect (and skip the root-level test cases for) container deployments where the project root isn't bind-mounted.
  - Uses `cu.get_project_root()` per CoSA path-management mandate (no `Path(__file__).parent` chains).

#### Verification

| Layer | Result |
|---|---|
| `py_compile` (all 3 modified .py files) | ✅ 3/3 OK (POST-EDIT VERIFICATION mandate satisfied before staging) |
| Multiplexer page route end-to-end | ✅ Parent Lupin Phase 1 implementation already verified `GET /app/multiplexer → 200` against live `:7999` (per parent `history.md` Multiplexer Phase 1 entry); CoSA-side commit lands the route the parent verified against. |
| Voice-persona `/clear` preservation Phase 3 | ✅ Parent Lupin unit-test suite `src/tests/unit/test_register_session_preservation.py` shows 8 passed + 1 xfailed; the xfail represents the legacy `session_ids[]` case pinned to Phase 1.3 which is still pending (parent TODO.md item carries it forward). |
| Docs viewer `/api/docs/file` + `/api/docs/health` | ✅ Parent Lupin smoke test `src/tests/smoke/test_docs_files_endpoint.py` shows 6 passed + 1 skipped (root-level mount unavailable in :7999 container — health endpoint signals + test correctly skips); covers health-shape, src/docs prefix happy-path, root-level mount-aware skip, whitelist-rejection, traversal-block, unsupported-extension reject, missing-file 404. |

#### Cross-repo separation

Per `CLAUDE.md` and memories `feedback_verify_repo_before_commit` / `feedback_lupin_only_never_cosa`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commits (Multiplexer Phase 1 spine + Session aacd24b4 Phase 3 + Session 2c732075) are owned by the parent context and not amended here. CoSA history mirrors the corresponding parent Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate. Parent Lupin `history.md` already documents Session 2c732075's "Files modified (CoSA subrepo — separate commit required)" caveat naming `docs_files.py`; parent does NOT need an update for this CoSA-context wrap.

#### Open follow-ups (carried by parent Lupin TODO.md + bug-fix-queue.md)

- **Voice-persona /clear preservation Phase 1.2/1.3/1.4 still pending** (parent TODO.md morning-of-2026.05.03 item #4): user must do one /clear on a planning session so the new diagnostics in `register_session.py` can identify which gate failed; then a minimal patch + sweep of `register_session.py:699-703` (idle backoff carry-forward) lands and the xfail flips. Frontend stale-badge propagation (Fix 4) remains PARKED.
- **Multiplexer Phase 5 + post-Phase-4 Q2 promotion to Option A or B** (parent TODO.md): if reload-UX during Phase 4-9 dogfooding produces "I lost notifications on reload" feedback, evaluate Option A (server-side replay buffer in `cosa/rest/websocket_manager.py`) or Option B (full-list persistence in `NotificationStore`). Otherwise Option C stands permanently.
- **`/api/claude-code/ws/{task_id}` endpoint cluster of bugs** (parent `bug-fix-queue.md` "🔥 Top of Queue — IMMEDIATE", filed 2026-05-04 Session ec746144 — 4 distinct bugs catalogued: URL mismatch / no-WS-auth / module-level state / parallel pre-cj-flow path) — user has explicitly promoted to top of queue for tomorrow morning's elimination; affects `src/cosa/rest/routers/claude_code.py`. Multiplexer Phase 4+ has CC out of scope per D1 A-extended ratification 2026-05-04 PM.

---

### 2026.05.02 - Session d29fb192 | CoSA-side wrap of Lupin Sessions 0022baba (WS reconnect circuit-breaker Phase 5 — server close codes) + 4ede5bad-AM (dev-tools voice-persona-reference page /sample endpoint)

**Context**: CoSA-context session-end commit bundle for two distinct bodies of work whose CoSA-side files were deliberately deferred by their parent Lupin sessions per `feedback_lupin_only_never_cosa.md`. Branch: `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Two clearly-scoped thematic commits, each mapping to a named body of work in the parent Lupin `history.md` / `TODO.md`.

**Commits Landed** (this session-end ritual): `0cc4ee8` (Body 1 voice-persona /sample), `3551ed3` (Body 2 WS Phase 5 close codes).

**Body 1 — Voice-persona `/sample` endpoint for dev-tools persona-reference page** (Lupin parent: Session 4ede5bad morning arc; Lupin-side files committed separately by parent context — `dev-tools.html`, `voice-persona-reference.html`)

One CoSA file delivers the server-side counterpart of the new dev-tools page that lets an admin audition each persona voice without spinning up a live notification session.

- **`rest/routers/voice_persona.py`** — New `POST /api/cosa-voice/voice-persona/sample` endpoint. JWT-gated via `require_api_key_or_jwt`. Pool-membership check rejects out-of-pool `voice_id` with HTTP 400 — prevents the endpoint being repurposed as a general-purpose TTS oracle that burns ElevenLabs quota on arbitrary voice ids. Calls the ElevenLabs HTTP TTS API directly (vs. the streaming `/api/get-speech-elevenlabs` WS path which requires an open audio session and is heavier than this static-page use case warrants). Returns `audio/mpeg` bytes inline so the page can `<audio>.src = blobURL` it. Profile defaults (`stability=0.5`, `similarity_boost=0.8`, `model_id=eleven_turbo_v2_5`) mirror the streaming path's "balanced" profile so reference samples sound representative. Upstream errors surface as HTTP 503 with a redacted snippet of the ElevenLabs response body. New imports: `httpx`, `Body`, `Response`, `BaseModel`, `cosa.utils.util as du` (for `du.get_api_key("eleven11")`). `VoicePersonaSampleRequest` Pydantic model declares the request shape.

**Body 2 — WS reconnect circuit-breaker Phase 5: server close codes 4001/4002** (Lupin parent: Session 0022baba commit `1a9e3e0`, CoSA commits this session)

Two CoSA files implement the server side of the close-code semantics that the parent Lupin client (`ws-channel.js` PERMANENT_CLOSE_CODES + `notifications.js` banner-reason differentiation + Layer-2/3 close-code tests) consumes. RFC 6455 §7.4.2 application range 4000-4999 reserved for Lupin auth semantics.

- **`rest/routers/websocket.py`** — Top-of-file constants `CLOSE_CODE_AUTH_INVALID_TOKEN=4001`, `CLOSE_CODE_AUTH_SESSION_CONFLICT=4002`, `CLOSE_CODE_AUTH_SUBSCRIPTION_DENIED=4003` with comment block reserving the 4000-4999 application range and documenting per-code semantics (4001 = invalid/expired/missing token, client treats as PERMANENT and tries token refresh first; 4002 = session conflict, client shows "Another session has taken over"; 4003 = RBAC reject, reserved for future enforcement). Replaced 10 generic `await websocket.close()` calls in the queue auth path (lines 367-499 in modified file) with `await websocket.close(code=4001, reason=<specific>)`. Reason strings used: `invalid_auth_request_json`, `invalid_auth_request`, `invalid_auth_request_shape`, `auth_protocol_violation`, `missing_token`, `invalid_token_type`, `empty_token`, `token_expired` (×2 — body + outer except), `invalid_token`, `auth_error`. Audio path (`:249-254`) was deliberately left as-is — it doesn't close on auth failure today.
- **`rest/websocket_manager.py:147`** — Single-session-per-user displaced socket close changed from `code=1000, reason="New session opened"` to `code=4002, reason="session_conflict_displaced"`. The displaced client now recognizes the close as PERMANENT (browser-side `ws-channel.js` PERMANENT_CLOSE_CODES set) and does NOT auto-retry. Pre-fix, the client treated the 1000 as a normal close and entered exponential-backoff reconnect — exactly the flapping we wanted to prevent.

#### Verification

| Layer | Result |
|---|---|
| `py_compile` (all 3 modified .py files) | ✅ 3/3 OK |
| End-to-end coverage of close codes | ✅ Parent Lupin `src/tests/websocket_smoke/core/test_close_codes.py::test_invalid_token_close_code` connects to live `:7999` with junk token, asserts server closes with code=4001. Layer-3 browser tests (`src/tests/ws_channel_browser/test_ws_close_codes.py`, 4 tests) verify client-side state machine + banner copy + token-refresh path triggered by 4001. |
| Voice-persona `/sample` smoke | ✅ Hand-verified via parent Lupin's `voice-persona-reference.html` page during Session 4ede5bad morning arc (per parent `TODO.md` "MORNING FINISHED — 2026.05.02" ✅ entries: page renders six persona tiles, ▶ Play sample button per tile, "Play all in sequence" toolbar). |
| Per-cluster details | See parent Lupin `history.md` Session 0022baba (5-phase WS circuit-breaker milestone, 85 tests + 1 conditional skip) and `TODO.md` "MORNING FINISHED — 2026.05.02" (voice-persona-reference page deliverables). |

#### Cross-repo separation

Per `CLAUDE.md` and memories `feedback_verify_repo_before_commit` / `feedback_lupin_only_never_cosa`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commit `1a9e3e0` (WS Phase 5) explicitly excludes these two CoSA files in its commit body and TODO.md morning-of-2026.05.03 item #1 names them as the pending CoSA-context commit work. The voice-persona-reference page Lupin-side files (`dev-tools.html`, `voice-persona-reference.html`) are committed separately by the parent context. CoSA history mirrors the corresponding Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate.

#### Open follow-ups (carried by parent Lupin TODO.md + bug-fix-queue.md)

- Voice-persona `/clear` preservation fix — design + execution-log scaffold at `src/rnd/v0.1.7/2026.05.02-voice-persona-clear-preservation/` (parent Lupin TODO morning-of-2026.05.03 item #3). Three server-side fixes scoped to `register_session.py`; this session's `voice_persona.py` change is unrelated to that work — it's the dev-tools page support, not the preservation fix.
- WS reconnect circuit-breaker E2E visual snapshot on `:8000` — already established + verified per parent Lupin Session 0022baba summary table (commits `27bcacd` + `92da8e2`).

---

### 2026.05.01 - Session d05e50fb | CoSA-side wrap of Lupin Sessions 31172845 (Post-mortem remediation 2026.04.30 22:15-EDT) + 911b1cdc (display_name helper + conv-mode exit-reminder push) + 5b732efe (María override)

**Context**: Session-end commit bundle for the CoSA-side work accumulated across **three** Lupin-parent sessions on 2026-05-01, on branch `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Two clearly-scoped thematic commits per `feedback_lupin_only_never_cosa.md` cross-repo separation, each mapping to a named body of work in the parent Lupin `history.md`.

**Commits Landed** (this session-end ritual): `5eff28b` (A), `08e6c1b` (B), `f161e23` (C session-end docs).

**Body 1 — Persona `display_name` plumbing + cross-session conv-mode exit-reminder action push** (Lupin parents: Session 911b1cdc commit `449e06c` + Session 5b732efe commit `044c5ff`, CoSA commit `5eff28b`)

Three files cover the persona-rename + cross-session conversation-mode work that landed parent-side under two Lupin sessions but maps to one tightly-coupled CoSA thematic commit (the helper, its overrides table, and the resolver consumers all touch the same display-name pipeline).

- **`rest/voice_persona_helpers.py`** — New `display_name_for(pool_name)` helper with `_HONORIFIC_TOKENS = {mr, mrs, ms, dr, prof, sr, jr, st}` (converts pool key form `mr radio` → display `Mr. Radio`) and `_DISPLAY_OVERRIDES = {"maria": "María"}` map for diacritics/punctuation that the lowercase-no-punctuation INI key convention strips. Whole-string overrides win over per-token rendering. `display_name` field stamped at all three persona-dict construction sites: `load_persona_pool_from_config` returns it directly; `borrowed_persona_for_sid` and `pick_unallocated_persona` use `base.get("display_name") or display_name_for(base["name"])` for safety on legacy pool dicts.
- **`rest/routers/notifications.py`** — `_voice_persona_for_sender_id` defensively stamps `display_name` on the returned dict if the bridge file predates the lowercase-key rename (legacy bridges have only `name`). Imports `display_name_for` lazily via try/except so old call paths still work if the helper module is missing.
- **`rest/routers/conversation_mode.py`** — At displacement time inside the activate critical-section, pushes a parallel `user_initiated_message` with `title="action:exit_conversation_mode"` + `job_id=other_sid[:8]` after the broadcast push. Best-effort try/except: action push failure does NOT block the activate path. The Lupin-side listener (`cc_notification_listener._handle_action`) routes it to inject a `<system-reminder>` block into the displaced session's tmux pane, correcting the model's stale in-context assumption that conversation mode is still active even after the bridge has flipped.

**Body 2 — Post-mortem 2026.04.30 22:15-EDT remediation: clusters B + D + G + C** (Lupin parent: Session 31172845 commit `431690b`, CoSA commit `08e6c1b`)

Four CoSA files covering four post-mortem clusters from the 2026-04-30 22:15-EDT all-suite run (9 smoke failures, 4732 passed, 51 skipped). Each cluster fix is independently verifiable; bundling preserves the post-mortem narrative on the CoSA side.

- **`rest/todo_fifo_queue.py`** — **Phase 2 / Cluster D defensive fix**: reordered `get_user_mode` branches so AGENTIC_MODE_MAP is checked BEFORE MODE_TO_AGENT. Several mode keys (`test_suite`, `deep_research`, `podcast`, `research_to_podcast`, `claude_code`, `swe_team`, `presentation`, `research_to_presentation`) appear in BOTH dicts. The original ordering hit MODE_TO_AGENT first and produced `f"agent router go to {user_mode}"` with an underscore form (e.g. `"agent router go to test_suite"`) that doesn't match any registered command — landing in the else branch downstream and triggering HTTP 500 with `'NoneType' .split`. AGENTIC_MODE_MAP holds the canonical space-form (`"agent router go to test suite"`). NOTE: this is a defensive belt; the real `NoneType.split()` source was not identified upstream — filed for follow-up.
- **`rest/routers/mock_job.py`** — **Phase 3 / Cluster G presentation keyword fallback**: in `_handle_expeditor_test`, partial-match cascade reordered specific (compound) → general (single token). Presentation cases now come BEFORE the bare "research" elif, otherwise `"research and present it"` would match `"agent router go to deep research"` instead of `"agent router go to research to presentation"`. Two new branches added: `"presentation" + "research"` → `"agent router go to research to presentation"`; bare `"presentation"` → `"agent router go to presentation generator"`.
- **`agents/test_suite/job.py`** — **Phase 6 / Cluster B INI-driven per-suite extra pytest_args**: best-effort ConfigurationManager read of `test suite {suite_type} extra pytest args` after the `--bg` strip step. The smoke suite needs `--auto-proxy` + `--cost-cap-usd` to satisfy the `pre_run_hook` of the two `live_smoke` tests (presentation + R2P); other suites are empty by default. Failure to load INI is logged and continues with caller-supplied args only — the augmentation is best-effort. `src/tests/smoke/conftest.py` registers the corresponding flags (`--auto-proxy`, `--cost-cap-usd`, `--no-confirm`, `--group`, `--scenario-id`) so pytest accepts them without erroring.
- **`rest/routers/test_suite.py`** — **Phase 7 / Cluster C preflight surrogate (doc-only)**: docstring addendum on `submit_test_suite` documenting the architectural blocker — the canonical safeguard `src/scripts/preflight-test-container.sh` CANNOT be invoked from this endpoint because the FastAPI server runs INSIDE the test container and the docker daemon is not reachable. Until a server-side surrogate (e.g. a `/api/preflight` endpoint that checks fixture presence + bind-mount paths from within the container) lands, callers MUST run preflight on the host BEFORE submitting an `all` or live-smoke schedule. Tracked as a follow-up bug in parent Lupin's `bug-fix-queue.md`.

#### Verification

| Layer | Result |
|---|---|
| `py_compile` (all 7 modified .py files) | ✅ all 7/7 OK |
| Per-cluster details | See parent Lupin `history.md` Sessions 31172845, 911b1cdc, 5b732efe (33 new unit tests, 1 smoke red→green, 5 follow-up bugs filed) |

#### Cross-repo separation

Per `CLAUDE.md` and memories `feedback_verify_repo_before_commit` / `feedback_lupin_only_never_cosa`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commits (`431690b`, `449e06c`, `044c5ff`) are owned by the parent context and not amended here. CoSA history mirrors the corresponding Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate.

#### Open follow-ups (carried by parent Lupin TODO.md + bug-fix-queue.md)

- Cluster D real `NoneType.split()` source — current fix is defensive only; a separate code path may still produce the original symptom under different conditions (filed in parent Lupin `bug-fix-queue.md` Queued).
- Cluster A 503 cascade design conversation — `/api/notify` returns 503 when offline + no `response_default`; expediter `_batch_collect_args` doesn't set one (4 fix options documented; user-facing decision pending).
- Cluster C preflight surrogate — server-side `/api/preflight` endpoint (3 design options filed).
- `claude-agent-sdk` install state — separately filed.
- Smoke harness label improvement — separately filed.

---

### 2026.04.30 - Session 9ae7718a | CoSA-side wrap of Lupin Session b195a160 PM (Postmortem clusters B + F + J + K + slow-test)

**Context**: Single CoSA-context session-end commit mirroring the afternoon arc of Lupin-parent Session **b195a160** (2026-04-30). Parent ran a postmortem of the 2026-04-29 :8000 all-test-run (15 failures) and closed Tier-1+2 follow-ups across 8 CoSA files. Per `feedback_lupin_only_never_cosa`, the parent committed only Lupin-side files (test rewrites, fixtures, postmortem + slow-test R&D docs, history.md); these 8 CoSA files were deliberately deferred to this CoSA-context session. Branch: `wip-v0.1.7-2026.04.23-tracking-lupin-work`.

**Single thematic commit** — all 8 files map to one afternoon arc; bundling preserves traceability without splitting across artificial boundaries.

**Cluster B — `auto_round` import gate** (1 file, closes 3 smoke fails)

- `training/quantizer.py` — line 8 un-gated `from auto_round import AutoRound` replaced with try/except + `AUTO_ROUND_AVAILABLE` flag (mirrors `training/peft_trainer.py` pattern). `quantize_model()` now raises a clear `RuntimeError` if called without `auto_round` installed.

**Cluster F — `slide_count` propagation** (4 files, Path 1 — formal field through state machine, NOT dict-passthrough hack)

- `agents/presentation_generator/job.py` — `self.artifacts["slide_count"] = presentation.total_slides` written in LIVE branch (line 290); sentinel `0` in dry-run branch.
- `agents/deep_research_to_presentation/state.py` — added `slide_count: Optional[int] = None` field to `ChainedResult`.
- `agents/deep_research_to_presentation/agent.py` — orchestrator at line 214 reads `pg_artifacts.get("slide_count")` into `self.result.slide_count`.
- `agents/deep_research_to_presentation/job.py` — line 256 writes `self.artifacts["slide_count"] = result.slide_count` (LIVE + dry-run branches).

**Cluster J — runtime-arg expediter `'NoneType' object has no attribute 'split'`** (1 file, +8 regression tests in parent Lupin)

- `agents/runtime_argument_expeditor/expeditor.py` — extracted `_resolve_display_name(agent_entry)` static method with proper short-circuit (display_name → cli_module derivation → "agent" sentinel). Fixed eager `dict.get` default evaluation that ran `None.split(".")` for the `test_suite` registry entry where `cli_module=None` by design. Both call sites (lines 340 + 588) now use the helper. Parent Lupin added `TestResolveDisplayName` (8 tests) covering the registry shape; full expediter unit suite 155/0 fail (was 147 → +8).

**Cluster K — verifier 3-attempt retry with gentle backoff** (1 file)

- `agents/notification_proxy/verification.py` — verification loop bumped from 2-attempt to 3-attempt with `time.sleep(0.5 * attempt)` between attempts (0.5s, then 1.0s). Insurance against transient vLLM empty-XML responses (yesterday's `FUZZY_BUDGET_2` failure pattern). Worst-case adds 1.5s for triply-flaky scenarios.

**Slow-test rewrite — `test_swe_team_orchestrator.py::TestDryRunRegression` 196s → 0.58s** (1 CoSA file + parent test rewrite)

- `agents/swe_team/mock_clients.py` — added `DELAY_MULTIPLIER = 1.0` class constant on `MockAgentSDKSession`. Test fixtures in parent Lupin's rewritten `TestDryRunRegression` (now 7 small tests + class-autouse fixture) zero this multiplier so mock async calls collapse to ~0ms.
- Parent diagnosed the original test was a covert end-to-end test that hit the real `cosa_interface.notify_progress` dispatcher: 7 breadcrumbs × ~28s under load ≈ 196s. **~1700× speedup** for that test cluster. Parent also authored a Tier-2 smoke at `src/tests/smoke/test_swe_team_dry_run_e2e.py` (`:8000`-scheduled, 240s budget) that retains real-dispatcher coverage.
- Plan doc (parent): `src/rnd/v0.1.7/2026.04.30-swe-team-orchestrator-test-perf-fix.md`.

#### Verification

| Layer | Result |
|---|---|
| `py_compile` (all 8 modified .py files) | ✅ all 8/8 OK |
| Per-cluster details | See parent Lupin `history.md` Session b195a160 PM entry (8 unit tests for swe_team in 0.58s, 22/22 swe_team_job, 155/0 expediter unit suite) |

#### Cross-repo separation

Per `CLAUDE.md` and memories `feedback_verify_repo_before_commit` / `feedback_lupin_only_never_cosa`: this CoSA-context session ONLY commits files inside `src/cosa/`. Parent Lupin commit (Session b195a160 PM, 9 Lupin-side files including test fixtures + R&D docs + history.md) is owned by the parent context. CoSA history mirrors the corresponding parent Lupin entry per CoSA `CLAUDE.md` cross-repo duplication mandate.

#### Open follow-ups (carried by parent Lupin TODO.md)

- Cluster I config audit — verify after tonight's `ts-0fb8e488` :8000 all-test-run (scheduled 21:30 EDT) whether `EXP_PRES_MISSING` still returns "Could not match voice command".
- Adjacent dev infra: investigate why dev `:7999` cannot reach `192.168.1.21:3001` (vLLM for runtime-arg expediter); test `:8000` could reach it yesterday.
- Architectural: per-test-file `pytest_args` declarations the scheduler could merge (so `test_presentation_live*` always get `--auto-proxy --cost-cap-usd N` without manual repetition).

---

### 2026.04.29 - Session 613652e0 | CoSA-side wrap of Lupin Sessions ba7138c4-cont (Test-Suite Phase 1+2) + d34f2f74 (TFE Phase 3 + Phase 4 backlog) + 78abd1aa (bcrypt pin) + 9977a1ba (WS-event cleanup + Rachel TTS sentinel)

**Context**: Session-end commit bundle for the CoSA-side work accumulated across **four** Lupin-parent sessions on 2026-04-29, on branch `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Seven clearly-scoped thematic commits per `feedback_lupin_only_never_cosa.md` cross-repo separation, each mapping to a named body of work in the parent Lupin `history.md`. **Note**: CoSA `history.md` was at 92.7% of the 25k token limit going into this session-end — entry kept terse + archive deferred to a dedicated future session (TODO captured in feedback memory).

**Body 1 — Test-suite remediation Phase 1+2 cluster fixes** (Lupin parent: Session ba7138c4-cont, commit `7df56e3`)

Five fix clusters from the post-RUN-2 triage (14 surviving smoke FAILs across 9 issue clusters per `07-final-execution-plan.md`).

- **`agents/test_fix_expediter/job.py`** — **cluster 2.1 OOS-1A**: TFE cluster-count typo at line 549 (`getattr(c, "failure_count", len(getattr(c, "failures", []) or []))` → `len(c.failure_indices)`); plus full-block defensive-programming cleanup (lines 540-565) — removed redundant `try/except` wrappers, dead `getattr` fallbacks, dead `summary` field (replaced with `c.shared_error_signature`). **Also Phase 4 #5**: `do_all` exception handler re-raises after persisting state/error.
- **`agents/notification_proxy/verification.py`** — **cluster 2.4**: single retry on `Exception` from `from_xml` parse in `AnswerVerifier.verify` to absorb vLLM transient empty-XML responses.
- **`agents/runtime_argument_expeditor/agent_registry.py`** — **cluster 2.8**: early-return guard on `cli_module=None` in `get_cli_help` and `get_user_visible_args` (test_suite intentionally has no CLI; expediter caller already handles `help_text=None`).
- **`training/peft_trainer.py`** — **cluster 2.1 LoRA env update**: extended the existing WG-4 `peft` import guard pattern to also wrap `trl` and `auto_round` imports.

**Body 2 — TFE Phase 3: INI proposal-cap (OOS-1B)** (Lupin parent: Session d34f2f74, commit `7e8be00`)

Cap on TFE proposal generation via INI knob, addressing OOS-1B's "unbounded proposal storms when failure cluster count is high".

- **`agents/test_fix_expediter/config.py`** — new `proposal_cap` field + INI key map entry.
- **`agents/test_fix_expediter/orchestrator.py`** — `_apply_proposal_cap()` truncates proposals to the configured cap before voice-gate.
- **`agents/test_fix_expediter/prompts/proposal.py`** — prompt updates referencing the cap.

**Body 3 — Cross-job sender_id ContextVar isolation** (Lupin parent: Session d34f2f74, Phase 4 backlog #1)

Concurrent DR jobs in the agentic pool were sharing `cosa_interface.SENDER_ID` (module global) and `_dispatcher.sender_id` (shared instance attribute), so the most-recently-launched job's sender leaked onto earlier still-running jobs' notifications.

- **`agents/utils/agent_notification_dispatcher.py`** — added `ContextVar`s for sender_id / target_user / session_name. Resolver methods prefer ContextVar over `self.*`. ContextVars are asyncio-task-local AND thread-local so the agentic pool's per-worker `asyncio.run()` contexts are naturally isolated.
- **`agents/deep_research/cosa_interface.py`** — `set_dispatch_context()` helper exposed.
- **`agents/deep_research/job.py`** — calls `set_dispatch_context()` at execution start; **also Phase 4 #5**: `do_all` re-raises after persisting state.

**Body 4 — Agentic pool error path + do_all re-raise across 8 subclasses** (Lupin parent: Session d34f2f74, Phase 4 backlog #2 + #4 + #5)

Three converging changes that make the agentic pool's error path canonical and observable.

- **`rest/running_fifo_queue.py`** — **Phase 4 #4**: refactored 4 non-canonical dead-queue write paths (`_process_job` exception handler, `_handle_error_case`, two paths in legacy `_handle_agentic_job`) to delegate to canonical `_transition_to_dead`. ~150 lines of duplicate metadata-build / WS-emit / queue-push logic collapsed to ~5 one-line calls. Only one `jobs_dead_queue.push` site remains. Plus **cluster 2.3** FAILED-state branch in `_on_agentic_complete` retained as defensive belt.
- **`rest/queue_consumer.py`** — **Phase 4 #2**: bound previously-indefinite `condition.wait()` to `idle_wake_interval_secs` (= `stall_threshold // 4` = 30s default); heartbeat ticked at top of EACH inner loop iteration. Healthy idle consumer now refreshes heartbeat at least every 30s instead of going stale on empty queue.
- **`agents/{podcast_generator,presentation_generator,deep_research_to_podcast,deep_research_to_presentation,swe_team,test_suite,bug_fix_expediter,claude_code}/job.py`** — **Phase 4 #5**: re-raise from `do_all` exception handler after persisting state/error/answer_conversational. `Future.exception()` now correctly carries the real exception; pool callback's exception branch fires directly. (`test_fix_expediter/job.py` and `deep_research/job.py` got the same change in Body 1 and Body 3 above.)

**Body 5 — bcrypt pin to 4.3.0** (Lupin parent: Session 78abd1aa, Lupin commit `093b7ca`)

- **`requirements.txt`** — `bcrypt==5.0.0` → `bcrypt==4.3.0`. Resolves passlib 1.7.4 + bcrypt 5.0.0 incompatibility (passlib reads `bcrypt.__about__.__version__`; bcrypt 5.0.0 removed `__about__`). Lupin Docker build resolves from `pyproject.toml` + `uv.lock` (already correctly pinned to 4.3.0); CoSA `requirements.txt` change is informational/parity. Per pyca/bcrypt issue [#1079](https://github.com/pyca/bcrypt/issues/1079).

**Body 6 — WS-event cleanup migration to push_notification subsystem** (Lupin parent: Session 9977a1ba, Lupin commit `70959c5`)

Four ad-hoc `ws_manager.emit_to_user(...)` callsites migrated to the canonical `push_notification(type=..., payload={...})` subsystem.

- **`rest/notification_fifo_queue.py`** — `NotificationItem.payload: Optional[dict]` field added; `to_dict()` includes it; `push_notification` accepts it as a kwarg.
- **`rest/routers/notifications.py`** — `valid_types` extended for `voice_persona_assigned` / `voice_persona_released` / `conversation_mode_changed`. Senders-visible response carries `voice_persona` for refresh-survival (Layer B persona hydration).
- **`rest/routers/voice_persona.py`** — allocate/release migrated from `emit_to_user` to `push_notification(type="voice_persona_assigned"/"voice_persona_released", payload={...})`.
- **`rest/routers/conversation_mode.py`** — `conversation_mode_changed` (including displaced-by payload) migrated to `push_notification`.

**Body 7 — Rachel voice-id sentinel fix** (Lupin parent: Session 9977a1ba)

- **`rest/routers/speech.py`** — legacy code special-cased Rachel's `voice_id 21m00Tcm4TlvDq8ikWAM` as the "no voice specified" sentinel, overriding it with the configured default (Sam) — so Rachel sessions silently spoke as Sam despite badges showing Rachel. Replaced with `None` sentinel; explicit voice_ids pass through unchanged.

#### Verification

Per-body verification was driven from Lupin parent — see Lupin `history.md` Sessions ba7138c4-cont / d34f2f74 / 78abd1aa / 9977a1ba for full test counts. Local `py_compile` clean 25/25 across all modified `.py` files in this CoSA-context wrap.

#### Commits Landed

- `64b05bc` — Commit A (Test-suite Phase 1+2 cluster fixes) — 4 files, +71/−47
- `70d44bc` — Commit B (TFE Phase 3 INI proposal-cap) — 3 files, +72/−24
- `de34182` — Commit C (sender_id ContextVar isolation) — 3 files, +180/−20
- `e7f27b5` — Commit D (Agentic pool error path + heartbeat + re-raise×8) — 10 files, +129/−225
- `5ad369b` — Commit E (bcrypt 4.3.0 pin) — 1 file, +1/−1
- `466ad30` — Commit F (WS-event cleanup migration to push_notification) — 4 files, +103/−52
- `7fa685f` — Commit G (Rachel TTS sentinel fix) — 1 file, +19/−7
- (Commit H session-end docs pending this commit)

#### Cross-repo separation

Per `CLAUDE.md` and memory `feedback_verify_repo_before_commit.md` / `feedback_lupin_only_never_cosa.md`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commits (`7df56e3`, `7e8be00`, `093b7ca`, `70959c5`, etc.) are owned by the parent context and not amended here. CoSA history mirrors the corresponding Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate.

---

### 2026.04.28 - Session 9dd6631b | CoSA-side wrap of Lupin Sessions ba7138c4 (Test-Suite Anomaly Remediation WG-2..9) + c7333045 (Conversation Mode v1.1 + EmbeddingProvider HTTP-routing) + 30072c25 (Voice Personas) + ba53b0d2 (Conv-mode ack receipt — docs only)

**Context**: Session-end commit bundle for the CoSA-side work accumulated across **four** Lupin-parent sessions on 2026-04-28, on branch `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Five clearly-scoped thematic commits per `feedback_lupin_only_never_cosa.md` cross-repo separation, each mapping to a named body of work documented in the parent Lupin `history.md` for unambiguous attribution.

**Body 1 — Voice Personas: per-session voice allocation** (Lupin parent: Session 30072c25)

NEW feature so multiple parallel Claude Code sessions can be told apart audibly + visually. 6-persona pool (Nora, Quentin, Rachel, Adam, Domi, Arnold) with random allocation; deterministic hash-modulo borrow on pool exhaustion. Sam reserved as the system-wide TTS default for any request lacking a `voice_id` — NOT in the allocatable pool.

- **`rest/voice_persona_helpers.py` (NEW)** — pure-function module: `load_pool` (reads INI [Voice Personas]), `pick_unallocated` (random.choice from pool − occupied), `borrowed_for_sid` (deterministic hash-modulo when pool exhausted), `allocate` (composes the prior three).
- **`rest/routers/voice_persona.py` (NEW)** — JWT/API-key gated endpoint set under `/api/cosa-voice/voice-persona/{session_id}`: `GET /pool` (returns full 6-persona pool with metadata), `GET /{sid}` (current allocation by session_id), `POST /{sid}/allocate` (atomic via `asyncio.Lock` so concurrent SessionStart hooks don't race), `POST /{sid}/release` (frees slot at SessionEnd).
- **`rest/notification_fifo_queue.py`** — `NotificationItem.voice_persona` field added; `to_dict()` includes it; `push_notification` accepts it as a kwarg so the persona rides the outbound WS envelope.
- **`rest/routers/notifications.py`** — `_voice_persona_for_sender_id` resolver looks up the bridge file (via the persona endpoint flow) for the sender_id on every notification dispatch. Three callsite injections: queued path (`notify_user`), response-required path, cc-listener inline broadcast.

**Body 2 — Conversation Mode v1.1: mutex auto-displace + Bug A WS dispatch dedup** (Lupin parent: Session c7333045)

Two CoSA-side changes layered on top of the v1 conversation-mode router from Session aabece5e (committed `2081452` last cycle).

- **`rest/routers/conversation_mode.py`** — Phase 2 of the mutex plan (`~/.claude/plans/drifting-skipping-porcupine.md`). The activate POST takes a module-level `asyncio.Lock`, scans bridge files for other active conversation-mode sessions via `find_active_conversation_sessions()` (parent Lupin helper), deactivates each + broadcasts `conversation_mode_changed {session_id, active=false, displaced=true, displaced_by=<sid>}`, then activates ours and broadcasts. Response gains `displaced_sessions` array. Mutual exclusion across CC sessions: only one session can monopolize the mic at a time. (Multi-worker uvicorn note — module-level `asyncio.Lock` only serializes within one process; Redis or DB advisory lock would be needed if `--workers N` is ever introduced.)
- **`rest/websocket_manager.py`** — Bug A fix: duplicate "Received:" echo on every voice message. `emit_to_user_or_listener_sync` was double-emitting when the cc-listener authenticated as the same user as the sender — the listener session was already in `user_sessions[user_id]` so `emit_to_user_sync` reached it via fan-out, and then `emit_to_session_sync` delivered the same envelope a second time. Added a `listener_in_user_fanout` check that skips the targeted listener emit when the session is already covered by user fan-out. Verified live: every voice message now produces exactly one `_handle_event` invocation in the listener log instead of two.

**Body 3 — EmbeddingProvider: process-aware HTTP routing + dynamic LUPIN_APP_SERVER_URL** (Lupin parent: Session c7333045 21:00 EDT checkpoint)

Architectural enforcement that eliminates accidental GPU loads from non-FastAPI processes. Before this change, `SolutionSnapshot.__init__()` called `generate_embedding()` up to 5 times per construction (question/code/solution/thoughts), and with config `embedding provider = local` + `local embedding device = cuda:0`, the first such call lazy-loaded `nomic-embed-text-v1.5` + `nomic-ai/CodeRankEmbed` onto cuda:0 — a non-FastAPI process holding a duplicate GPU model. The canonical path is the FastAPI `/api/embeddings/{generate,batch}` endpoints that already use the in-process singleton.

- **`memory/embedding_provider.py`** (+232 lines):
  - New `_is_in_process_engine_owner` class flag (default False).
  - `declare_in_process_engine_owner()` classmethod flipped True only by FastAPI startup after engines load (parent Lupin wires this in `src/fastapi_app/main.py` immediately after `prose_engine` warmup).
  - `generate_embedding()` and `generate_embeddings_batch()` route locally only when flag=True; otherwise HTTP-route to `/api/embeddings/generate` or `/api/embeddings/batch` via X-API-Key auth (mirrors `prediction_engine._generate_embedding_via_http` pattern). HTTP failures raise clear `RuntimeError` with URL + cause — fail-fast beats silent GPU grab.
  - `_resolve_server_url()` reads `LUPIN_APP_SERVER_URL` env var at every call (NOT module load). A test running on `:8000` can `export LUPIN_APP_SERVER_URL=http://localhost:8000` and route there mid-process without restarting Python. Default `http://localhost:7999`.
  - `SolutionSnapshot.__init__()` requires zero changes — same `generate_embedding()` calls; routing is now context-aware automatically.

**Body 4 — CJ Flow pool hardening: OOS-4 dead-letter fix + WG-8b consumer heartbeat + CalculatorAgent codeless replay** (Lupin parent: Session ba7138c4)

Three pool-related fixes from the morning checkpoint `bb9298c` + 19:35 EDT checkpoint `892652c`.

- **`rest/running_fifo_queue.py`** — Two changes:
  - **(WG-8b)** consumer-thread heartbeat field: new `last_consumer_heartbeat_at` updated by `consumer_worker` at the top of each loop iteration. `/api/queue/pool-status` now reports `last_consumer_heartbeat_at`, `seconds_since_heartbeat`, `consumer_stall_threshold_secs`, `consumer_stalled`. Stalled consumer is now observable for operators (or future watchdogs) without requiring runtime instrumentation.
  - **(OOS-4 hotfix Parts A + B)** dead-letter mis-attribution at line 276/294 area: consumer's bare-exception handler had `failed_job = self.head()` which mis-attributed Calculator crashes to whatever `test_suite_job` was sitting in the agentic pool, dead-lettering the wrong job. Part A: `failed_job = job` (use the parameter, mirror happy-path fix already in place at line 203). Part B: added `failed_job.error = str(e)` so dead-queue listings have populated error fields (was empty for the 8 reaped Calc jobs in the 22:35 baseline). Verified via `:8000 ts-976bdc44` re-run (test_suite_job survived 5 calc dead-letters with proper error fields populated).
- **`rest/queue_consumer.py`** — WG-8b heartbeat write at consumer-loop top. Wrapped in `try/except AttributeError` so unit-test Mocks and older `running_queue` implementations are never fatal.
- **`memory/solution_snapshot.py`** — CalculatorAgent codeless replay short-circuit in `run_code()`. CalculatorAgent dispatches CalcIntent to pure-Python helpers — no Python source to save — so its snapshots persist with `code = ['']` BY DESIGN. Replay path's empty-code guard was raising on this legitimate state, dead-lettering the job. Fix mirrors the existing CalculatorAgent special-case in `run_formatter()` at lines 943-953: synthesize `code_response_dict = {"return_code": 0, "output": self.answer}` when `agent_class_name == "CalculatorAgent"`.

**Body 5 — Test-suite anomaly remediation WG-4/7/9: peft guard + websocket parser fallback + voice-gate timeout policy** (Lupin parent: Session ba7138c4)

Four CoSA-side changes from the postmortem of the 2026-04-27 22:35 EDT scheduled `:8000` run `ts-90890bae` (4422 P / 23 F / 19 E / 47 S, 1 orphaned Calculator job in `run`, 8 reaped Calc jobs in `dead`, stalled downstream TFE). Working-group docs at `src/rnd/v0.1.7/2026.04.28-test-suite-anomaly-remediation/`.

- **`training/peft_trainer.py`** — **WG-4**: optional `peft` import guard. Wrapped the `from peft import LoraConfig, prepare_model_for_kbit_training, PeftModel` line in `try/except ImportError` with a `PEFT_AVAILABLE` flag + None fallbacks (matches the `claude-agent-sdk` pattern in `dispatcher.py`). Effect: 3 `test_lora_env_update_smoke` collection-time failures resolved when `peft` is not installed in the test container.
- **`agents/test_suite/job.py`** — **WG-7**: websocket false-FAIL parser fix. The websocket runner emits `[INFO] Total Tests: N / Passed: X / Failed: Y / ALL SMOKE TESTS PASSED!` rather than JUnit XML, so `_parse_junit_xml(None)` returned zero-counts and the suite was classified FAIL despite passing. Added `_parse_non_pytest_stdout(suite_type, stdout)` called as a fallback. Effect: the 22:35 websocket suite (which logged 50/50 PASS) now classifies PASS instead of 0/0/0/0 FAIL. `ts-976bdc44` re-run confirmed websocket: 0/0/0/0 FAIL → 50P PASS.
- **`agents/test_fix_expediter/config.py`** — **WG-9**: voice-gate timeout policy config. Two new fields: `voice_gate_timeout_policy` (one of `stall|top_1|top_n|none`) and `voice_gate_auto_ratify_top_n`. Two new INI keys in the key map. Default policy = `"stall"` preserves prior production behavior.
- **`agents/test_fix_expediter/orchestrator.py`** — **WG-9**: timeout-policy branch + `_delegate_to_predictor` stub. On `VoiceGateTimeoutError` the orchestrator branches via `_apply_voice_gate_timeout_policy(proposals)` — sorts by confidence (input order tiebreak), returns 0/1/N proposals or re-raises per policy. After-hours autonomous TFE runs can now opt into auto-ratifying the highest-confidence proposal instead of stalling and discarding all proposals. Plus `_delegate_to_predictor()` forward-compat stub raising `NotImplementedError` with a pointer to the design doc at `05-voice-gate-policy-evolution.md` (UPE online-learning integration is ~2 dev branches out per user).

#### Verification

| Layer | Result |
|---|---|
| py_compile (all 14 modified/new .py files) | ✅ all 14/14 OK |
| Lupin parent verification (Session 30072c25 voice personas) | ✅ 102/102 PASS in 0.80s — 25 new unit + 7 new live :7999 smoke + 70 regression |
| Lupin parent verification (Session c7333045 conv-mode v1.1) | ✅ 130/130 PASS across 5 test files (22 net new tests) |
| Lupin parent verification (Session c7333045 EmbeddingProvider) | ✅ 56/56 (40 prior + 16 new). Full conv-mode + embedding sweep: 192/192 |
| Lupin parent verification (Session ba7138c4 morning + 19:35) | ✅ 23 new + 147 regression PASS. ts-976bdc44 :8000 re-run: 4524P / 15F / 12E / 54S |

#### Commits Landed

- `2116566` — Commit A (Voice Personas) — 4 files, +604/−6
- `f9bc577` — Commit B (Conv Mode v1.1 mutex + Bug A WS dedup) — 2 files, +74/−8
- `e7b3df2` — Commit C (EmbeddingProvider HTTP-routing) — 1 file, +232/−12
- `e90cb3d` — Commit D (CJ Flow pool hardening) — 3 files, +98/−11
- `6e99494` — Commit E (Test-suite WG-4/7/9) — 4 files, +197/−3
- (Commit F session-end docs pending this commit)

#### Cross-repo separation

Per `CLAUDE.md` and memory `feedback_verify_repo_before_commit.md` / `feedback_lupin_only_never_cosa.md`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commits are owned by the parent context and not amended here. CoSA history mirrors the corresponding Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate.

---

### 2026.04.27 - Session c2b5912f | CoSA-side wrap of Lupin Sessions aabece5e (Conversation Mode) + 49c27830 (Notification Dispatch Unification + CJ Flow card-rendering wrap) + deferred 2026-04-26 podcast tuning

**Context**: Session-end commit bundle for the CoSA-side work from three Lupin-parent commits, on branch `wip-v0.1.7-2026.04.23-tracking-lupin-work`. Three clearly-scoped commits per `feedback_lupin_only_never_cosa.md` cross-repo separation, each mapping unambiguously to a named parent commit.

**Body 1 — Conversation Mode for Claude Code** (Lupin parent commit: `48dc03e`, session `aabece5e`)

Claude Code now has a per-session "conversation mode" toggle backed by the cosa-voice session-bridge file at `~/.claude/sessions/cc-{PPID}.json`. When `conversation_mode_active=True`, Claude auto-`notify(full_text, suppress_ding=True)` after every turn so the user can hold a voice dialogue at a distance via TTS rather than reading the terminal. Four convergent activation surfaces (voice phrase "enter conversation mode", `/conversation-mode-on` slash command, MCP `enter_conversation_mode()` tool, UI toggle button per-session in the sender card header). All paths converge on the bridge file as canonical state; UI clients hold a localStorage read-through cache hydrated by the GET endpoint and the `conversation_mode_changed` WebSocket event broadcast on POST.

- **`rest/routers/conversation_mode.py` (NEW)** — JWT/API-key gated endpoint pair under `/api/cosa-voice/conversation-mode/{session_id}`:
  - `GET` — reads `conversation_mode_active` from the bridge file via `find_session_path_by_id()` + `get_conversation_mode()`. Returns 404 if no bridge matches the session_id.
  - `POST` — writes the flag via `set_conversation_mode()` and broadcasts a `conversation_mode_changed` WebSocket event to the authenticated user's sessions so all UI tabs sync. Bridge write is canonical; broadcast is best-effort (failures logged but non-fatal — bridge write succeeded).
  - Pulls bridge helpers from the parent Lupin tree (`from lupin_cli.claude_code.hooks.lib.session_bridge import ...`); imports across the cross-repo boundary are fine, only git ops are restricted.

**Body 2 — Notification Dispatch Unification (Phases A-F)** (Lupin parent commit: `f28b63b`, session `49c27830`)

USER-REPORTED bug — 3 user-initiated messages from the LookML CC notifications panel UI targeting CC session `b2ce9133` were silently dropped. Forensic dive surfaced a duplicated dispatch pattern across 6 sites with inconsistent behavior: `notify_user` short-circuited on `is_user_connected(target_system_id)=False` even though `cc-listener-{job_id}` was right there in `active_connections` under a different shared service-account user_id (`claude.code@lupin.deepily.ai`). Day's arc: narrow fix → audit → planned full unification → executed Phases A-F.

- **`rest/websocket_manager.py`** — new `emit_to_user_or_listener_sync()` helper (~95 lines incl. Design-by-Contract docstring), sibling to the canonical `emit_to_user_and_admins_sync` precedent. Always tries the primary user emit (when user_id is provided AND `is_user_connected()`); independently tries the cc-listener path when job_id is provided AND `cc-listener-{job_id}` is in `active_connections`. Returns `{user_delivered, listener_delivered, any_delivered}` dict. Errors in either underlying call are logged and never re-raised (consistent with sibling sync helpers).
- **`rest/routers/notifications.py`** — Migrations 1, 2, 3:
  - Migration 1 (`notify_user` fire-and-forget): replaces the inline narrow fix from earlier in the day. When `is_connected=False` AND `job_id` is set, the helper attempts the cross-user listener fallback before falling through to `user_not_available`. State updated to 'delivered' on success; idempotency cache populated.
  - Migration 2 (`notification_expired` SSE timeout broadcast): swapped `await ws_manager.emit_to_user(...)` for the helper — gains the listener fallback that was missing.
  - Migration 3 (`notification_responded` response-submission broadcast): same swap; captures `notification.job_id` before session closes so the helper has it for the cross-user emit.
- **`rest/routers/queues.py`** — Migration 4 (`send_job_message`): collapses the 40-line dual-emit (one `emit_to_user_sync` + one cross-user `emit_to_session_sync`) to a single helper call. Also adds Body 3's `_count_interactions_for_jobs()` helper + done/dead-bucket consumers (see below).
- **`rest/notification_fifo_queue.py`** — Migration 5 (`_emit_notification_added`): collapsed targeted-user + listener emits into the helper. Broadcast path (when `notification.user_id is None`) still fires `emit()` to all connected clients but ALSO routes explicitly via the helper with `user_id=None` to ensure listener-only delivery when `job_id` is set.
- **`tests/unit/rest/test_notifications_router.py`** — small alignment fix: `app_timezone` → `app timezone` (matches the actual `lupin-app.ini` key name with space, not underscore).

**Body 3 — CJ Flow card-rendering wrap** (Lupin parent commit: `f28b63b`, same session `49c27830`)

Three orthogonal hardening pieces that landed in the same parent commit as Body 2:

- **`rest/db/repositories/notification_repository.py`** — new `count_by_job_ids(job_ids)` method. Single batched SQL query (`func.count(Notification.id).group_by(Notification.job_id)`) excluding soft-hidden rows for parity with the lazy-load endpoint at `/api/get-job-interactions/{job_id}`. Returns `{job_id: int}` dict with every input job_id present (zero-fill for missing). Used to populate `has_interactions` accurately without N+1 queries.
- **`rest/routers/queues.py`** — new `_count_interactions_for_jobs()` private helper wrapping `NotificationRepository.count_by_job_ids` with graceful failure (returns `{}` on DB error, logged). Done- and dead-bucket handlers in `get_queue` now compute `notif_counts = _count_interactions_for_jobs([j.id_hash for j in jobs])` once per request, then set `"has_interactions": notif_counts.get(job.id_hash, 0) > 0`. Replaces the old `bool(job.session_id)` proxy that gave false positives whenever a job had a session but no notifications.
- **`rest/job_persistence.py`** — `/api/job-history` shape parity with `/api/get-queue/done`:
  - New `_count_notifications_for_jobs(session, job_ids)` — bulk count using the active SQLAlchemy session (avoids pulling NotificationRepository into the persistence module's import surface).
  - New `_unpack_metadata_json(md)` — flattens rich fields out of the JSONB blob: `response_text` (with legacy `answer_conversational` fallback), `abstract`, `report_path` (with legacy `report_link` alias), `remediation_snapshot_path`, `yaml_path`, `pptx_path`, `cost_summary`, `scheduled_at`, `monopolize`.
  - New `_build_history_row(row, has_interactions)` — converts a `JobHistory` ORM row into the flat dict shape the frontend renderer expects: top-level identity/column fields + flattened metadata + `has_interactions` from the bulk count + `paused=False` (history is terminal). `metadata_json` retained as backward-compat (additive, not removed).
  - `query_job_history()` rewritten to call the bulk-count helper once and the row-builder per row. Net effect: `/api/job-history` cards now render with the same affordances as `/api/get-queue/done` cards (interaction badge, abstract, scheduled-at, monopolize flag, etc.) and history-list shows accurate has_interactions instead of the legacy session_id proxy.
- **`rest/running_fifo_queue.py`** — pool-path stall fix (Bug 11 port to v0.1.7 pool dispatcher). New `_transition_to_stalled(job, formatted_output)` method mirrors `_transition_to_done`'s structure but emits `JobState.STALLED` with `checkpoint` + `plan_path` in the metadata blob (instead of `JobState.COMPLETED` with no checkpoint). Persistence dispatch in `queue_util.emit_job_state_transition` routes `to_state == JobState.STALLED` to `persist_job_stalled_from_metadata`, which writes `status='stalled'` to `job_history` and preserves the checkpoint blob in `metadata_json` for later resume. Early-return added to `_on_agentic_complete` at line ~466: `if job.state == JobState.STALLED: self._transition_to_stalled(job, formatted_output); return`. Background: Bug 11 (2026-04-15) added the equivalent stall handling in the legacy serial `_handle_agentic_job` path (~line 898). Phase 2's pool refactor moved agentic dispatch to `_on_agentic_complete` but did not port the stall check, leaving status='completed' as the unconditional outcome for ALL agentic jobs going through the pool — including TFE and BFE voice-gate stalls. This closes that gap; checkpoint-resume now works under the pool.

**Body 4 — Podcast persona tone tuning** (Lupin parent commit: `cb6c2c4`, deferred from 2026-04-26)

CoSA-side companion to yesterday's Lupin checkpoint that tuned podcast TTS style values in `lupin-app.ini` (Nora 0.40→0.65, Quentin 0.50→0.70). The CoSA persona-config tone strings are read by the host setup logic to seed character voice direction:

- **`agents/podcast_generator/config.py`** — `DEFAULT_CURIOUS_HOST.tone`: "enthusiastic and inquisitive" → "highly animated, fast-paced, and inquisitive". `DEFAULT_EXPERT_HOST.tone`: "warm and authoritative" → "energetic, warm, and authoritative". 4 lines changed total.

#### Verification

| Layer | Result |
|---|---|
| py_compile (all 10 modified .py files) | ✅ all OK |
| AST symbol probe (10 new symbols across 8 files) | ✅ all present |
| Live `:7999` endpoint registration check (`/api/cosa-voice/conversation-mode/{id}`) | ✅ 401 (auth-required, route registered) |
| Lupin parent verification (per `48dc03e`) | ✅ 23 new pytest tests across 3 files, 52/52 pass incl. pre-existing session_bridge suite |
| Lupin parent verification (per `f28b63b`) | ✅ Lupin unit suite **3672 pass / 1 xfail / 0 fail** (was 3638 pre-session → +34 tests). With CoSA notification fifo queue tests: **3677 pass**. WebSocket smoke 50/50. Final grep audit: zero `emit_to_session_sync` in 3 migrated routers; helper is the single chokepoint. |

#### Cross-repo separation

Per `CLAUDE.md` and memory `feedback_verify_repo_before_commit.md` / `feedback_lupin_only_never_cosa.md`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent commits (`48dc03e`, `f28b63b`, `cb6c2c4`) are owned by the parent context and not amended here. CoSA history mirrors the corresponding Lupin entries per CoSA `CLAUDE.md` cross-repo duplication mandate.

#### Files in this commit bundle (CoSA only)

**Commit A — Conversation mode router** (Lupin parent: `48dc03e`):
- `rest/routers/conversation_mode.py` (NEW)

**Commit B — Notification dispatch unification + CJ Flow card-rendering wrap** (Lupin parent: `f28b63b`):
- `rest/websocket_manager.py`
- `rest/routers/notifications.py`
- `rest/routers/queues.py`
- `rest/notification_fifo_queue.py`
- `tests/unit/rest/test_notifications_router.py`
- `rest/db/repositories/notification_repository.py`
- `rest/job_persistence.py`
- `rest/running_fifo_queue.py`

**Commit C — Podcast persona tone tuning** (Lupin parent: `cb6c2c4`):
- `agents/podcast_generator/config.py`

**Commit D (session-end docs)**:
- `history.md`
- `.claude-session.md`

**Commit A**: `2081452` (1 file, +168/-0) — Conversation mode router
**Commit B**: `1de2084` (8 files, +543/-67) — Notification dispatch unification + CJ Flow card-rendering wrap
**Commit C**: `aec2713` (1 file, +2/-2) — Podcast persona tone tuning
**Commit D**: (this entry — session-end docs with backfilled hashes)

---

### 2026.04.25 - Session c608199a | CoSA-side wrap of Lupin Session 6c798a07 (Podcast generator completion abstract — clickable URLs)

**Context**: Session-end commit for the CoSA-side work from Lupin-parent Session `6c798a07` (2026-04-25). User submitted a podcast generation job (`pg-6bcf412d`), it completed, but the completion notification's abstract showed bare filesystem paths in backticks instead of clickable URLs — no way to play or download the generated MP3 from the UI. Two-stage fix in one session: (1) build clickable Markdown links + switch artifacts to relative paths, (2) point Listen at canonical in-app player route after a brief detour through the raw-file API endpoint.

**Body — Podcast completion abstract clickable URLs** (Lupin parent session `6c798a07`)

- **`agents/podcast_generator/job.py`** — at line ~277-310 in the success-path block of `_run_orchestrator()`:
  - Added `_to_rel()` local helper that normalizes 3 input shapes (abs paths under `cu.get_project_root() + "/io/"`, `"io/"`-prefixed relatives, `"/"`-prefixed paths) to clean relative paths under `io/`. Mirrors the receiving logic in `rest/routers/io_files.py:88-98` and the convention already used by `agents/presentation_generator/job.py:301-341`.
  - Switched `self.artifacts[ "audio_path" ]` and `self.artifacts[ "script_path" ]` from absolute filesystem paths to relative paths (so the UI job-card consumer at `cosa/rest/routers/queues.py` builds correct URLs).
  - Added new `self.artifacts[ "report_path" ] = script_rel` so the queue-card metadata exposes the script as a "report link" artifact (renderReportLinkSection consumes this on the Lupin frontend).
  - Replaced the 2 bare-backtick path lines (`f"**Script**: \`{self.script_path}\`"`, `f"**Audio**: \`{self.audio_path}\`"`) in the rich-markdown abstract with 3 clickable Markdown links:
    - Listen: `[🎧 Listen](/app/audio?path=...)` (routes to canonical in-app HTML5 audio player at `static/html/audio-player.html` — full player UI with title, subtitle from script H1, file size, embedded download button)
    - Download: `[⬇️ Download](/api/io/file?path=...&download=true)` (forces `Content-Disposition: attachment` via `download=true` query param)
    - View Script: `[📝 View Script](/app/docs?path=...)`
  - URL-encodes path components via `urllib.parse.quote()`.

**Stage-2 detour + revert** (no CoSA-side change — recorded for completeness):
- First iteration of Stage 2 pointed Listen at `/api/io/file?path=...` (the raw-file endpoint). User noted this forced download because Starlette `FileResponse(filename=...)` defaults to `Content-Disposition: attachment`. Briefly fixed `io_files.py` with `content_disposition_type="inline"` then **reverted** when user clarified Listen should target the canonical `/app/audio` route alias. Final Listen URL: `/app/audio?path=...` (player page, no API change needed). The CoSA `io_files.py` was never modified in the final state.

#### Verification (parent-side, replicated here)

| Layer | Result |
|---|---|
| py_compile (`agents/podcast_generator/job.py`) | ✅ OK |
| Import chain (`from cosa.agents.podcast_generator.job import PodcastGeneratorJob`) | ✅ OK |
| Lupin podcast completion unit tests (`test_podcast_completion_report.py`) | ✅ 6/6 (URL-link assertions + parametrized `test_completion_url_path_normalization` covering 3 input shapes) |
| Lupin broader podcast-related unit regression | ✅ 26/26 |
| Manual smoke (parent): `/app/audio?path=...mp3` | ✅ HTTP 200 `text/html` (player page) |
| Manual smoke (parent): `/api/io/file?path=...mp3&download=true` | ✅ `Content-Disposition: attachment` |
| Manual smoke (parent): `/api/io/file?path=...mp3` (raw) | ✅ Still works for media-element consumption inside player |

#### Cross-repo separation
Per `CLAUDE.md` and memory `feedback_verify_repo_before_commit.md`: this CoSA-context session ONLY commits files inside `src/cosa/`. The Lupin-parent test updates (`src/tests/unit/test_podcast_completion_report.py`) and history-archive bookkeeping (`history/2026-04-14-to-21-history.md`, `history.md`, `TODO.md`) belong to parent context and are not amended here. CoSA history mirrors the Lupin entry per CoSA `CLAUDE.md` cross-repo duplication mandate.

#### Files in this commit (CoSA only)

- `agents/podcast_generator/job.py` (+39/−7)
- `history.md`
- `.claude-session.md`

**Commit**: 32c55ed (3 files, +124/-8)

---

---

## Archive Navigation

### Monthly Archives
- **[Feb 28 → Apr 24, 2026](history/2026-02-28-to-04-24-history.md)** - v0.1.5 → v0.1.6 → v0.1.7 milestone arc: Prediction Engine, TestFixExpediter, BFE Phase 6, CJ Flow async pool, MCP nested-repo detection
- **[Feb 2026 (Feb 5-26)](history/2026-02-05-to-26-history.md)** - Sessions 135-276: DataFrame CRUD, SWE Team Phases 2-4, Decision Proxy, Notification Proxy, Prediction Engine, voice refactoring, preference learning
- **[Nov 2025 - Feb 2026 (Nov 8, 2025 - Feb 3, 2026)](history/2025-11-08-to-2026-02-03-history.md)** - Sessions 56-126: Conversation Identity, Deep Research Agent, Podcast Generator, Queue Protocol, Directory Analyzer, Lupin sync entries
- **[October 2025 (Oct 4-30)](history/2025-10-history.md)** - Planning workflows, CLI modernization, history management, branch analyzer refactoring (9 sessions)
- **[June-October 2025 (Jun 27 - Oct 3)](history/2025-06-27-to-10-03-history.md)** - Authentication infrastructure, WebSocket implementation, notification system refactor, testing framework (20 sessions)

### Project Context
- **Project Span**: June 2025 - Present (COSA framework within Lupin project)
- **Current Branch**: `wip-v0.1.7-2026.04.23-tracking-lupin-work`
- **Architecture**: Collection of Small Agents (COSA) for Lupin FastAPI application
- **Parent Project**: Lupin (located at `../..`)
