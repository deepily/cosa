"""
Bug Fix Expediter background job for queue-based execution.

Takes a dead job's context, diagnoses the failure, proposes fixes,
and optionally applies a fix and retries the original job.

Example:
    job = BugFixExpediterJob(
        dead_job_id = "dr-abc12345::user123",
        user_id     = "user123",
        user_email  = "user@example.com",
        session_id  = "wise-penguin",
        debug       = True
    )
    result = job.do_all()  # Runs pipeline and returns conversational answer
"""

import asyncio
from datetime import datetime
from typing import Optional

from cosa.agents.agentic_job_base import AgenticJobBase
from cosa.rest.job_state import JobState


class BugFixExpediterJob( AgenticJobBase ):
    """
    Background job for Bug Fix Expediter execution.

    Runs the three-phase forensic pipeline (diagnose -> propose -> fix)
    on a dead job's context. Phase 1 foundation: packages dead job context
    and returns a placeholder (orchestrator pipeline is Phase 2+).

    Attributes:
        dead_job_id: The id_hash of the failed/interrupted job to fix
        extra_context: Optional additional context from user
        dead_job_context: Extracted context (set during execution)
        diagnosis: Root cause analysis (set during execution, Phase 2+)
        cost_summary: Execution cost summary (set after completion)
    """

    JOB_TYPE   = "bug_fix_expediter"
    JOB_PREFIX = "bfe"

    def __init__(
        self,
        dead_job_id: str,
        user_id: str,
        user_email: str,
        session_id: str,
        extra_context: str = "",
        dry_run: bool = False,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a Bug Fix Expediter job.

        Requires:
            - dead_job_id is a non-empty string (id_hash from job_history)
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with "bfe-" prefix
            - All parameters stored for execution

        Args:
            dead_job_id: The id_hash of the dead job to fix
            user_id: System ID of the job owner
            user_email: Email address for notification routing
            session_id: WebSocket session for notifications
            extra_context: Optional user-provided context about the failure
            dry_run: Simulate execution without making changes
            debug: Enable debug output
            verbose: Enable verbose output
        """
        super().__init__(
            user_id    = user_id,
            user_email = user_email,
            session_id = session_id,
            debug      = debug,
            verbose    = verbose
        )

        self.dead_job_id      = dead_job_id
        self.extra_context    = extra_context
        self.dry_run          = dry_run

        # Results (populated after execution)
        self.dead_job_context = None    # DeadJobContext
        self.diagnosis        = None    # DiagnosisResult (Phase 2+)
        self.cost_summary     = None

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns:
            str: Human-readable job description
        """
        return f"[Bug Fix Expediter] Fix job: {self.dead_job_id}"

    def do_all( self ) -> str:
        """
        Execute bug fix pipeline and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing results
        """
        if self.debug: print( f"[BugFixExpediterJob] Starting do_all() for dead job: {self.dead_job_id}" )

        self.state      = JobState.RUNNING
        self.started_at = datetime.now().isoformat()

        try:
            result = asyncio.run( self._execute() )

            # Check if cancellation was requested during execution
            if self._cancel_requested:
                self.state                 = JobState.CANCELLED
                self.completed_at          = datetime.now().isoformat()
                self.error                 = "Cancelled by user request"
                self.answer_conversational = result or "Bug fix was cancelled."
                if self.debug: print( "[BugFixExpediterJob] Cancelled by user request" )
                return self.answer_conversational

            self.state        = JobState.COMPLETED
            self.completed_at = datetime.now().isoformat()
            self.result       = result
            self.answer_conversational = result

            if self.debug:
                duration = self.get_execution_duration_seconds()
                print( f"[BugFixExpediterJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()

            self.state        = JobState.FAILED
            self.completed_at = datetime.now().isoformat()
            self.error        = f"{e}\n\n{tb_str}"

            print( f"[BugFixExpediterJob] Failed: {e}" )
            print( tb_str )

            self.answer_conversational = f"Bug fix failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Internal async bug fix execution.

        Phase 1 foundation: packages dead job context and returns placeholder.
        Orchestrator pipeline (diagnose -> propose -> fix) is Phase 2+.

        Returns:
            str: Conversational summary of results
        """
        from cosa.agents.bug_fix_expediter import voice_io, cosa_interface
        from cosa.agents.bug_fix_expediter.dead_job_packager import package_dead_job

        # Re-establish core voice_io binding (import-order race)
        voice_io.reconfigure()

        # Handle dry-run mode
        if self.dry_run:
            return await self._execute_dry_run( voice_io, cosa_interface )

        # Set sender identity
        cosa_interface.SENDER_ID   = cosa_interface._get_sender_id( suffix=self.base_id )
        cosa_interface.TARGET_USER = self.user_email

        # Set job_id for auto-injection into all downstream notify() calls
        voice_io.set_job_id( self.id_hash )

        try:
            # Phase 0: Package dead job context
            await voice_io.notify(
                f"Packaging dead job context: {self.dead_job_id}",
                priority="medium", job_id=self.id_hash, queue_name="run"
            )

            self.dead_job_context = package_dead_job( self.dead_job_id, debug=self.debug )

            if self.dead_job_context is None:
                msg = f"Dead job not found: {self.dead_job_id}"
                await voice_io.notify( msg, priority="high", job_id=self.id_hash, queue_name="run" )
                return msg

            self.artifacts[ "dead_job_context" ] = self.dead_job_context.model_dump()

            await voice_io.notify(
                f"Dead job packaged: {self.dead_job_context.job_type} "
                f"(status={self.dead_job_context.status})",
                priority="medium", job_id=self.id_hash, queue_name="run"
            )

            # Phase 1: Diagnose (Lead agent analyzes failure)
            from cosa.agents.bug_fix_expediter.orchestrator import BFEOrchestrator
            from cosa.agents.bug_fix_expediter.config import BugFixExpediterConfig
            from cosa.config.configuration_manager import ConfigurationManager

            config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            config     = BugFixExpediterConfig.from_config( config_mgr, debug=self.debug )

            orchestrator = BFEOrchestrator(
                dead_job_context = self.dead_job_context,
                extra_context    = self.extra_context,
                config           = config,
                session_id       = self.session_id,
                job_id           = self.id_hash,
                cancel_check     = lambda: self._cancel_requested,
                debug            = self.debug,
                verbose          = self.verbose,
            )

            # Store orchestrator ref for external cancellation (AgenticJobBase protocol)
            self._orchestrator = orchestrator

            self.diagnosis = await orchestrator.run_diagnosis()
            self.artifacts[ "diagnosis" ] = self.diagnosis.model_dump()

            # Phase 2: Propose (Lead agent generates fix proposals)
            proposed_fixes, selected_fix, plan_path = await orchestrator.run_proposal( self.diagnosis )

            self.artifacts[ "proposed_fixes" ] = [ f.model_dump() for f in proposed_fixes ]
            self.artifacts[ "plan_path" ]      = plan_path

            if selected_fix:
                self.artifacts[ "selected_fix" ] = selected_fix.model_dump()

            # Phase 3: Fix (Coder + Tester apply and validate)
            if selected_fix:
                fix_result = await orchestrator.run_fix( self.diagnosis, selected_fix, plan_path )
                self.artifacts[ "fix_result" ] = fix_result.model_dump()
            else:
                from cosa.agents.bug_fix_expediter.state import FixResult
                fix_result = FixResult( applied=False, success=False, details="No fix selected" )

            fix_summary = f"{len( proposed_fixes )} fix(es) proposed"
            if selected_fix:
                fix_summary += f", selected: '{selected_fix.title}'"
            if fix_result.applied:
                fix_summary += f", applied: {'success' if fix_result.success else 'failed'}"

            result = (
                f"Bug Fix Expediter complete for '{self.dead_job_id}'. "
                f"Root cause: {self.diagnosis.root_cause[ :150 ]}. "
                f"{fix_summary}. "
                f"Plan: {plan_path}. "
                f"Retry pipeline not yet implemented (Phase 6+)."
            )

            await voice_io.notify(
                "Fix phase complete." if fix_result.applied else "No fix applied.",
                priority="medium", job_id=self.id_hash, queue_name="run"
            )

            return result

        except Exception as e:
            await voice_io.notify(
                f"Bug Fix Expediter error: {str( e )[ :100 ]}",
                priority="urgent", job_id=self.id_hash, queue_name="run"
            )
            raise

        finally:
            voice_io.clear_job_id()

    async def _execute_dry_run( self, voice_io, cosa_interface ) -> str:
        """
        Execute dry-run mode with breadcrumb notifications.

        Simulates the three-phase pipeline without making changes.
        Sends low-priority notifications at each phase and returns mock results.

        Args:
            voice_io: Voice I/O module for notifications
            cosa_interface: COSA interface module for sender ID

        Returns:
            str: Mock conversational summary
        """
        import asyncio

        cosa_interface.SENDER_ID   = cosa_interface._get_sender_id( suffix=self.base_id )
        cosa_interface.TARGET_USER = self.user_email

        if self.debug: print( f"[BugFixExpediterJob] DRY RUN MODE for dead job: {self.dead_job_id}" )

        # Breadcrumb: Packaging
        await voice_io.notify( "🧪 Dry run: Packaging dead job context...", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Diagnosis
        await voice_io.notify( "🧪 Dry run: Diagnosing root cause...", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Proposal
        await voice_io.notify( "🧪 Dry run: Generating fix proposals...", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Fix application
        await voice_io.notify( "🧪 Dry run: Applying fix (simulated)...", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Retry
        await voice_io.notify( "🧪 Dry run: Retry evaluation (simulated)...", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Mock artifacts
        self.artifacts[ "dead_job_context" ] = {
            "id_hash"  : self.dead_job_id,
            "job_type" : "unknown",
            "status"   : "failed",
            "error"    : "Simulated error for dry run",
        }
        self.artifacts[ "diagnosis" ] = {
            "root_cause"     : "Simulated root cause",
            "error_category" : "unknown",
            "confidence"     : 0.0,
        }

        completion_abstract = f"""**🧪 Dry Run Complete!**

**Dead Job**: {self.dead_job_id}
**Diagnosis**: Simulated root cause (dry run)
**Fix**: Not applied (dry run)
**Stats**: $0.00 | 0 tokens | 5.0s (simulated)"""

        await voice_io.notify(
            "🧪 Dry run complete! No changes made.",
            priority="medium", abstract=completion_abstract,
            job_id=self.id_hash, queue_name="run"
        )

        return "Dry run complete. Bug fix simulation finished."


def quick_smoke_test():
    """Quick smoke test for BugFixExpediterJob."""
    import cosa.utils.util as cu

    cu.print_banner( "BugFixExpediterJob Smoke Test", prepend_nl=True )

    try:
        # 1: Import
        from cosa.agents.bug_fix_expediter.job import BugFixExpediterJob
        print( "✓ Module imported successfully" )

        # 2: Instantiation
        job = BugFixExpediterJob(
            dead_job_id = "dr-test1234::user123",
            user_id     = "user123",
            user_email  = "test@test.com",
            session_id  = "session456",
            debug       = True
        )
        print( f"✓ Job created with id: {job.id_hash}" )

        # 3: ID format
        assert job.id_hash.startswith( "bfe-" ), "ID should start with bfe-"
        print( f"✓ ID format correct: {job.id_hash}" )

        # 4: last_question_asked
        lqa = job.last_question_asked
        assert "[Bug Fix Expediter]" in lqa
        assert "dr-test1234" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # 5: is_cacheable
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # 6: Attributes
        assert job.dead_job_id == "dr-test1234::user123"
        assert job.user_email == "test@test.com"
        assert job.state == JobState.PENDING
        assert job.dry_run == False
        print( "✓ All attributes set correctly" )

        # 7: Class constants
        assert BugFixExpediterJob.JOB_TYPE == "bug_fix_expediter"
        assert BugFixExpediterJob.JOB_PREFIX == "bfe"
        print( "✓ Class constants correct" )

        print( "\n⚠ Note: do_all() not tested (requires running server)" )
        print( "\n✓ BugFixExpediterJob smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
