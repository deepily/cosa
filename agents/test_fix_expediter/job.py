"""
TestFixExpediter background job for queue-based execution.

Session 1cfcdf73 (2026-04-10): Parallel to BFE's job.py. Takes a remediation
snapshot (from a failed TestSuiteJob), runs the TFE pipeline (cluster →
diagnose → propose → fix → git → rerun), and returns a conversational answer.

**Step 6 scaffolding**: `_execute()` loads the snapshot, runs the orchestrator
phase stubs, and returns a placeholder conversational answer. Full pipeline
wiring lands incrementally in steps 7-12.

Example:
    job = TestFixExpediterJob(
        remediation_snapshot_path = "test-suite/2026.04.10-at-14:53-e2e-remediation.json",
        source_test_suite_job_id  = "ts-abc12345",
        user_id                   = "user123",
        user_email                = "user@example.com",
        session_id                = "wise-penguin",
        debug                     = True,
    )
    result = job.do_all()
"""

import asyncio
import traceback
from datetime import datetime
from typing import Optional

import cosa.utils.util as cu

from cosa.agents.agentic_job_base import AgenticJobBase
from cosa.rest.job_state import JobState


class TestFixExpediterJob( AgenticJobBase ):
    """
    Background job for TestFixExpediter execution.

    Runs the TFE pipeline on a remediation snapshot from a failed
    TestSuiteJob. **Step 6 scaffolding**: `_execute()` exercises the
    orchestrator phase stubs to prove end-to-end wiring. Full pipeline
    lands in steps 7-12 per the approved plan.

    Attributes:
        remediation_snapshot_path: Path to the snapshot JSON (relative to io/)
        source_test_suite_job_id:  The TestSuiteJob that produced the snapshot
        remediation_context:       Parsed TestRemediationContext (set during _execute)
        orchestrator:              TFEOrchestrator instance (set during _execute)
        cost_summary:              Execution cost summary (set after completion)
    """

    JOB_TYPE   = "test_fix_expediter"
    JOB_PREFIX = "tfe"

    def __init__(
        self,
        remediation_snapshot_path: str,
        source_test_suite_job_id: str,
        user_id: str,
        user_email: str,
        session_id: str,
        original_test_types: Optional[ list ] = None,
        original_pytest_args: Optional[ list ] = None,
        dry_run: bool = False,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a TestFixExpediter job.

        Requires:
            - remediation_snapshot_path is a non-empty path (relative to io/)
            - source_test_suite_job_id is a non-empty string
            - user_id, user_email, session_id are non-empty

        Ensures:
            - Job ID generated with "tfe-" prefix (via AgenticJobBase)
            - All parameters stored for execution

        Args:
            remediation_snapshot_path: Path to the remediation JSON
            source_test_suite_job_id: ID of the TestSuiteJob that produced the snapshot
            user_id: System ID of the job owner
            user_email: Email address for notification routing
            session_id: WebSocket session for notifications
            original_test_types: Suites the original job ran (for Phase 6 rerun)
            original_pytest_args: Original pytest args (for Phase 6 rerun)
            dry_run: Simulate execution without making changes
            debug: Enable debug output
            verbose: Enable verbose output
        """
        super().__init__(
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            debug      = debug,
            verbose    = verbose,
        )

        self.remediation_snapshot_path = remediation_snapshot_path
        self.source_test_suite_job_id  = source_test_suite_job_id
        self.original_test_types       = original_test_types or []
        self.original_pytest_args      = original_pytest_args or []
        self.dry_run                   = dry_run

        # Results (populated during execution)
        self.remediation_context = None    # TestRemediationContext
        self.orchestrator        = None    # TFEOrchestrator
        self.cost_summary        = None

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns:
            str: Concise description of the remediation source
        """
        return f"TFE: fix failures from {self.source_test_suite_job_id}"

    def do_all( self ) -> str:
        """
        Synchronous entry point for queue consumer.

        Runs `_execute()` in an event loop, sets the `AgenticJobBase` lifecycle
        state (`self.state`), captures full Python traceback into `self.error`
        on failure, and returns a conversational answer string. Exception
        handling follows the BFE pattern (`bug_fix_expediter/job.py:107-157`)
        so dead TFE jobs carry complete forensic data for queue serialization
        + job_history persistence.

        Returns:
            str: Conversational answer for UI display
        """
        if self.debug:
            print( f"[TestFixExpediterJob] Starting do_all() for: {self.source_test_suite_job_id}" )

        self.state      = JobState.RUNNING
        self.started_at = cu.get_current_datetime_iso()

        try:
            result = asyncio.run( self._execute() )

            if self._cancel_requested:
                self.state                 = JobState.CANCELLED
                self.completed_at          = cu.get_current_datetime_iso()
                self.error                 = "Cancelled by user request"
                self.answer_conversational = result or "TFE was cancelled by the user."
                if self.debug: print( f"[TestFixExpediterJob] Cancelled by user request" )
                return self.answer_conversational

            self.state                 = JobState.COMPLETED
            self.completed_at          = cu.get_current_datetime_iso()
            self.result                = result
            self.answer_conversational = result

            if self.debug:
                duration = self.get_execution_duration_seconds()
                print( f"[TestFixExpediterJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            tb_str = traceback.format_exc()

            self.state        = JobState.FAILED
            self.completed_at = cu.get_current_datetime_iso()
            self.error        = f"{e}\n\n{tb_str}"

            # Unconditional stdout (not gated behind self.debug) so dockered
            # server logs always capture the traceback regardless of the
            # job's debug flag. Production submissions run with debug=False.
            print( f"[TestFixExpediterJob] Failed: {e}" )
            print( tb_str )

            self.answer_conversational = f"TFE failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Run the TFE pipeline.

        Sets cosa-voice routing (SENDER_ID + TARGET_USER) for BFE's delegated
        notification dispatcher, then wraps phase orchestration in a try/except
        that emits an urgent voice notification with the full traceback on
        crash before re-raising (do_all's handler captures self.error).

        **Step 6 scaffolding**: loads the snapshot, instantiates the
        orchestrator, walks the phase stubs, and returns a placeholder.
        Full pipeline wiring lands in steps 7-12.
        """
        from cosa.agents.test_fix_expediter.config import TestFixExpediterConfig
        from cosa.agents.test_fix_expediter.snapshot_loader import (
            load_from_path,
            SnapshotLoadError,
        )
        from cosa.agents.test_fix_expediter.orchestrator import TFEOrchestrator
        from cosa.agents.test_fix_expediter import voice_io
        # TFE's cosa_interface.py is a thin delegator that forwards to BFE's
        # cosa_interface module. BFE's dispatcher reads SENDER_ID and TARGET_USER
        # from its OWN module-level state, so we must set them on BFE's module
        # directly for TFE notifications to route correctly. This was the root
        # cause of tfe-d9e6b50f's "present_choices failed: Cannot resolve
        # target_user" crash at the Phase 2 voice gate.
        # See: src/rnd/v0.1.6/2026.04.11-tfe-forensics-capture-plan.md (Fix 7)
        from cosa.agents.bug_fix_expediter import cosa_interface as _bfe_ci

        _bfe_ci.TARGET_USER = self.user_email
        _bfe_ci.SENDER_ID   = _bfe_ci._get_sender_id( suffix=self.base_id )

        # Config load has its own fallback; not inside the main try/except
        # because using defaults is acceptable, not a TFE failure.
        try:
            from cosa.config.configuration_manager import ConfigurationManager
            config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            config     = TestFixExpediterConfig.from_config( config_mgr, debug=self.debug )
        except Exception as e:
            if self.debug: print( f"[TestFixExpediterJob] from_config failed, using defaults: {e}" )
            config = TestFixExpediterConfig()

        try:
            # Load the remediation snapshot
            try:
                self.remediation_context = load_from_path(
                    snapshot_path             = self.remediation_snapshot_path,
                    source_test_suite_job_id  = self.source_test_suite_job_id,
                    user_id                   = self.user_id,
                    user_email                = self.user_email,
                    session_id                = self.session_id,
                    original_test_types       = self.original_test_types,
                    original_pytest_args      = self.original_pytest_args,
                )
            except SnapshotLoadError as e:
                raise RuntimeError( f"Failed to load remediation snapshot: {e}" )

            # Instantiate the orchestrator
            self.orchestrator = TFEOrchestrator(
                remediation_context = self.remediation_context,
                config              = config,
                user_id             = self.user_id,
                user_email          = self.user_email,
                session_id          = self.session_id,
                job_id              = self.id_hash,
                dry_run             = self.dry_run,
                debug               = self.debug,
                verbose             = self.verbose,
            )

            # Walk the phase stubs (step 6 — proves wiring end-to-end)
            clusters = await self.orchestrator.run_phase0_cluster()
            diagnoses = await self.orchestrator.run_phase1_diagnose()
            _propose_result = await self.orchestrator.run_phase2_propose()

            # Fix 8a: Surface the Phase 2 plan path for dead-queue card. Storing
            # it here (before Phase 3) ensures the artifact survives if a later
            # phase crashes — tfe-d9e6b50f died at the Phase 2 voice gate with a
            # complete plan on disk but no link to it in the UI.
            if self.orchestrator.last_plan_path:
                self.artifacts[ "plan_path" ] = self.orchestrator.last_plan_path

            fix_results = await self.orchestrator.run_phase3_fix()
            _git_result = await self.orchestrator.run_phase5_git()
            validation_run_job_id = await self.orchestrator.run_phase6_validation()

            # Populate artifacts for UI
            self.artifacts[ "remediation_snapshot_path" ] = self.remediation_snapshot_path
            self.artifacts[ "source_test_suite_job_id" ] = self.source_test_suite_job_id
            self.artifacts[ "cluster_count" ] = len( clusters )
            self.artifacts[ "fix_count" ] = len( fix_results )
            self.artifacts[ "validation_run_job_id" ] = validation_run_job_id

            return (
                f"TFE scaffolding run complete ({len( clusters )} clusters stubbed, "
                f"phases 0-6 walked). Full pipeline lands in steps 7-12. "
                f"Source TestSuiteJob: {self.source_test_suite_job_id}."
            )

        except Exception as e:
            # Emit urgent voice notification with full traceback in the abstract
            # field (UI-only, not spoken via TTS) so the user gets in-UI access
            # to the failure without having to grep docker logs. Re-raises so
            # do_all()'s handler captures the traceback into self.error too.
            # See: src/rnd/v0.1.6/2026.04.11-tfe-forensics-capture-plan.md (Fix 3)
            tb_str = traceback.format_exc()
            try:
                await voice_io.notify(
                    f"Test Fix Expediter error: {str( e )[ :100 ]}",
                    priority = "urgent",
                    job_id   = self.id_hash,
                    abstract = tb_str,
                )
            except Exception as notify_err:
                # Never let the notify failure mask the original exception
                print( f"[TestFixExpediterJob] voice_io.notify failed during error path: {notify_err}" )
            raise


def quick_smoke_test():
    """Quick smoke test for TestFixExpediterJob."""
    cu.print_banner( "TestFixExpediterJob Smoke Test", prepend_nl=True )

    try:
        # 1: JOB_TYPE and JOB_PREFIX constants
        assert TestFixExpediterJob.JOB_TYPE == "test_fix_expediter"
        assert TestFixExpediterJob.JOB_PREFIX == "tfe"
        print( "✓ JOB_TYPE and JOB_PREFIX constants correct" )

        # 2: Instantiation
        job = TestFixExpediterJob(
            remediation_snapshot_path = "test-suite/fake-remediation.json",
            source_test_suite_job_id  = "ts-abc12345",
            user_id                   = "u1",
            user_email                = "t@t.com",
            session_id                = "s1",
            original_test_types       = [ "e2e" ],
            dry_run                   = True,
            debug                     = False,
        )
        assert job.remediation_snapshot_path == "test-suite/fake-remediation.json"
        assert job.source_test_suite_job_id == "ts-abc12345"
        assert job.dry_run == True
        assert job.remediation_context is None  # not loaded yet
        assert job.orchestrator is None
        print( "✓ Instantiation works" )

        # 3: id_hash format (from AgenticJobBase)
        assert job.id_hash.startswith( "tfe-" ), f"id_hash should start with tfe-, got {job.id_hash}"
        print( f"✓ id_hash format correct: {job.id_hash}" )

        # 4: last_question_asked property
        q = job.last_question_asked
        assert "ts-abc12345" in q
        print( f"✓ last_question_asked: {q}" )

        print( "\n✓ TestFixExpediterJob smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
