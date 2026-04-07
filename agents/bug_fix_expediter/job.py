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

                # Phase 5: Git strategy (commit / branch / PR based on trust proxy)
                if fix_result.success and orchestrator.last_files_changed:
                    fix_result = await orchestrator.run_git_strategy(
                        fix_result, orchestrator.last_files_changed, plan_path
                    )
                    self.artifacts[ "fix_result" ] = fix_result.model_dump()
            else:
                from cosa.agents.bug_fix_expediter.state import FixResult
                fix_result = FixResult( applied=False, success=False, details="No fix selected" )

            fix_summary = f"{len( proposed_fixes )} fix(es) proposed"
            if selected_fix:
                fix_summary += f", selected: '{selected_fix.title}'"
            if fix_result.applied:
                fix_summary += f", applied: {'success' if fix_result.success else 'failed'}"

            await voice_io.notify(
                "Fix phase complete." if fix_result.applied else "No fix applied.",
                priority="medium", job_id=self.id_hash, queue_name="run"
            )

            # Phase 6: Resubmit original job if fix succeeded
            resubmit_id = None
            if fix_result.success and fix_result.applied:
                resubmit_id = await self._resubmit_original_job( voice_io )
                if resubmit_id:
                    fix_result.resubmitted_job_id = resubmit_id
                    self.artifacts[ "fix_result" ]       = fix_result.model_dump()
                    self.artifacts[ "resubmitted_job_id" ] = resubmit_id

            resubmit_msg = ""
            if resubmit_id:
                resubmit_msg = f" Resubmitted as {resubmit_id}."
            elif fix_result.success and fix_result.applied:
                resubmit_msg = " Resubmit skipped (no auto-fix config or queue unavailable)."

            result = (
                f"Bug Fix Expediter complete for '{self.dead_job_id}'. "
                f"Root cause: {self.diagnosis.root_cause[ :150 ]}. "
                f"{fix_summary}. "
                f"Plan: {plan_path}.{resubmit_msg}"
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

    async def _resubmit_original_job( self, voice_io ) -> Optional[ str ]:
        """
        Phase 6: Resubmit the original failed job after successful fix.

        Reconstructs the original job using its persisted metadata and
        pushes it to the todo queue as the original user.

        Requires:
            - self.dead_job_context is populated (Phase 0 completed)
            - Fix was successful (caller must check)

        Ensures:
            - Returns resubmitted job's id_hash on success, None on failure
            - Job is submitted as the original user (user_id, user_email, session_id)
            - Notifications sent at each stage
            - Never raises — returns None on any error

        Returns:
            str or None: Resubmitted job id_hash, or None if skipped/failed
        """
        from cosa.agents.bug_fix_expediter.state import BFEPhase

        if self.dead_job_context is None:
            if self.debug: print( "[BFE] Cannot resubmit: no dead_job_context" )
            return None

        ctx = self.dead_job_context

        # Check if auto-fix resubmission is enabled
        try:
            from cosa.config.configuration_manager import ConfigurationManager
            config_mgr   = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            auto_enabled = config_mgr.get( "auto fix enabled", default=False, return_type="boolean" )
            if not auto_enabled:
                if self.debug: print( "[BFE] Auto-fix resubmit disabled in config" )
                return None
        except Exception as e:
            if self.debug: print( f"[BFE] Config check failed, skipping resubmit: {e}" )
            return None

        await voice_io.notify(
            f"Resubmitting original {ctx.job_type} job as {ctx.user_email}...",
            priority="medium", job_id=self.id_hash, queue_name="run"
        )

        try:
            from cosa.rest.agentic_job_factory import create_agentic_job
            from cosa.rest.queue_extensions import user_job_tracker

            # Use the original routing command to reconstruct the job
            routing_command = ctx.routing_command
            if not routing_command:
                if self.debug: print( f"[BFE] No routing_command in dead job context, cannot resubmit" )
                await voice_io.notify(
                    "Cannot resubmit: original routing command not found in job history.",
                    priority="high", job_id=self.id_hash, queue_name="run"
                )
                return None

            # Extract original args from metadata_json
            metadata  = ctx.metadata_json or {}
            args_dict = metadata.get( "original_args", {} )

            # If original_args not stored, reconstruct minimal args from question_text
            if not args_dict:
                args_dict = { "query": ctx.question_text }

            # Create the job as the original user
            new_job = create_agentic_job(
                command    = routing_command,
                args_dict  = args_dict,
                user_id    = ctx.user_id,
                user_email = ctx.user_email,
                session_id = ctx.session_id,
                debug      = self.debug,
                verbose    = self.verbose,
            )

            if new_job is None:
                await voice_io.notify(
                    f"Resubmit failed: factory returned None for command '{routing_command}'.",
                    priority="high", job_id=self.id_hash, queue_name="run"
                )
                return None

            # Register scoped ID and push to todo queue
            new_job.id_hash = user_job_tracker.register_scoped_job(
                new_job.id_hash, ctx.user_id, ctx.session_id
            )

            # Get the todo queue from the app module singleton
            import fastapi_app.main as main_module
            todo_queue = main_module.jobs_todo_queue
            if todo_queue is None:
                await voice_io.notify(
                    "Resubmit failed: todo queue not available.",
                    priority="high", job_id=self.id_hash, queue_name="run"
                )
                return None

            todo_queue.push( new_job )

            await voice_io.notify(
                f"Original job resubmitted as {new_job.id_hash}. Notifications will route to your UI.",
                priority="high", job_id=new_job.id_hash, queue_name="todo"
            )

            if self.debug:
                print( f"[BFE] Resubmitted job: {new_job.id_hash} "
                       f"(type={ctx.job_type}, user={ctx.user_email})" )

            return new_job.id_hash

        except Exception as e:
            print( f"[BFE] Resubmit failed: {e}" )
            await voice_io.notify(
                f"Resubmit failed: {str( e )[ :100 ]}",
                priority="high", job_id=self.id_hash, queue_name="run"
            )
            return None

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
