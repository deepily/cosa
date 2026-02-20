"""
SWE Team background job for queue-based execution.

Wraps the SWE Team orchestrator for execution within the COSA queue
system. Enables users to submit engineering tasks via the API and
receive results asynchronously.

Example:
    job = SweTeamJob(
        task       = "Add health check endpoint",
        user_id    = "user123",
        user_email = "user@example.com",
        session_id = "wise-penguin",
        dry_run    = True,
        debug      = True
    )
    result = job.do_all()  # Runs SWE Team and returns conversational answer
"""

import asyncio
from datetime import datetime
from typing import Optional


from cosa.agents.agentic_job_base import AgenticJobBase


class SweTeamJob( AgenticJobBase ):
    """
    Background job for SWE Team multi-agent execution.

    Runs multi-minute engineering tasks with task decomposition,
    coder delegation, and test verification. Sends progress
    notifications via cosa-voice.

    Attributes:
        task: The engineering task to accomplish
        dry_run: Simulate execution without API calls
        lead_model: Model for lead agent (None = use default)
        worker_model: Model for worker agents (None = use default)
        budget: Maximum budget in USD (None = use default)
        timeout: Wall-clock timeout in seconds (None = use default)
        cost_summary: Execution cost summary (set after completion)
    """

    JOB_TYPE   = "swe_team"
    JOB_PREFIX = "swe"

    def __init__(
        self,
        task,
        user_id,
        user_email,
        session_id,
        dry_run=False,
        lead_model=None,
        worker_model=None,
        budget=None,
        timeout=None,
        debug=False,
        verbose=False
    ):
        """
        Initialize a SWE Team job.

        Requires:
            - task is a non-empty string
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with "swe-" prefix
            - All parameters stored for execution

        Args:
            task: The engineering task description
            user_id: System ID of the job owner
            user_email: Email address for notifications
            session_id: WebSocket session for notifications
            dry_run: Simulate execution without API calls
            lead_model: Model for lead agent (None = use default)
            worker_model: Model for worker agents (None = use default)
            budget: Maximum budget in USD (None = use default)
            timeout: Wall-clock timeout in seconds (None = use default)
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

        # Task parameters
        self.task         = task
        self.dry_run      = dry_run
        self.lead_model   = lead_model
        self.worker_model = worker_model
        self.budget       = budget
        self.timeout      = timeout

        # Results (populated after execution)
        self.cost_summary = None

    @property
    def last_question_asked( self ):
        """
        Display string for queue UI.

        Returns truncated task with [SWE Team] prefix.

        Returns:
            str: Human-readable job description
        """
        truncated = self.task[ :50 ] + "..." if len( self.task ) > 50 else self.task
        return f"[SWE Team] {truncated}"

    def do_all( self ):
        """
        Execute SWE Team task and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing results
        """
        if self.debug:
            print( f"[SweTeamJob] Starting do_all() for: {self.task[ :50 ]}..." )

        self.status     = "running"
        self.started_at = datetime.now().isoformat()

        try:
            result = asyncio.run( self._execute() )

            self.status       = "completed"
            self.completed_at = datetime.now().isoformat()
            self.result       = result
            self.answer_conversational = result

            if self.debug:
                duration = self.get_execution_duration_seconds()
                print( f"[SweTeamJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            self.status       = "failed"
            self.completed_at = datetime.now().isoformat()
            self.error        = str( e )

            if self.debug:
                print( f"[SweTeamJob] Failed: {e}" )
                import traceback
                traceback.print_exc()

            # Return error message as conversational answer
            self.answer_conversational = f"SWE Team task failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ):
        """
        Internal async SWE Team execution.

        When dry_run=True, sends breadcrumb notifications and returns mock results.
        When live, delegates to SweTeamOrchestrator.

        Returns:
            str: Conversational summary of results
        """
        from cosa.agents.swe_team import voice_io

        # Handle dry-run mode with breadcrumb notifications
        if self.dry_run:
            return await self._execute_dry_run( voice_io )

        # Set SESSION_ID so sender_id includes job hash suffix for routing
        from cosa.agents.swe_team import cosa_interface
        cosa_interface.SESSION_ID = self.id_hash

        # Live execution: build config and delegate to orchestrator
        from cosa.agents.swe_team.config import SweTeamConfig
        from cosa.agents.swe_team.orchestrator import SweTeamOrchestrator

        config = SweTeamConfig(
            dry_run = False,
        )

        if self.lead_model:
            config.lead_model = self.lead_model
        if self.worker_model:
            config.worker_model = self.worker_model
        if self.budget is not None:
            config.budget_usd = self.budget
        if self.timeout is not None:
            config.wall_clock_timeout_secs = self.timeout

        orchestrator = SweTeamOrchestrator(
            task_description = self.task,
            config           = config,
            session_id       = self.id_hash,
            job_id           = self.id_hash,
            debug            = self.debug,
            verbose          = self.verbose
        )

        # Start notification client for user-initiated messages (Approach D)
        notification_client = None
        if config.enable_user_messages:
            notification_client = self._start_notification_client( orchestrator )

        try:
            result = await orchestrator.run()

            if result is None:
                return "SWE Team task failed or was cancelled."

            return result

        finally:
            # Always clean up notification client
            if notification_client:
                notification_client.stop_sync()
                if self.debug:
                    print( f"[SweTeamJob] Notification client stopped for {self.id_hash}" )

    def _start_notification_client( self, orchestrator ):
        """
        Create and start an OrchestratorNotificationClient.

        Shares the orchestrator's _user_messages queue and _urgent_interrupt
        event so user messages flow from WebSocket → queue → orchestrator.

        Requires:
            - orchestrator has _user_messages and _urgent_interrupt attributes
            - self.user_email is set

        Ensures:
            - Returns started client, or None on failure
            - Client runs in a daemon thread
            - Never raises (logs warning on failure)

        Args:
            orchestrator: SweTeamOrchestrator instance

        Returns:
            OrchestratorNotificationClient or None
        """
        try:
            from cosa.agents.swe_team.notification_client import OrchestratorNotificationClient

            client = OrchestratorNotificationClient(
                user_email    = self.user_email,
                job_id        = self.id_hash,
                message_queue = orchestrator._user_messages,
                urgent_event  = orchestrator._urgent_interrupt,
                debug         = self.debug,
                verbose       = self.verbose,
            )
            client.start()

            if self.debug:
                print( f"[SweTeamJob] Notification client started for {self.id_hash}" )

            return client

        except Exception as e:
            print( f"[SweTeamJob] Warning: Failed to start notification client: {e}" )
            return None

    async def _execute_dry_run( self, voice_io ):
        """
        Execute dry-run mode with breadcrumb notifications.

        Simulates the SWE Team workflow without making API calls.
        Sends low-priority notifications at each phase and returns mock results.

        Args:
            voice_io: Voice I/O module for notifications

        Returns:
            str: Mock conversational summary
        """
        if self.debug:
            print( f"[SweTeamJob] DRY RUN MODE for: {self.task[ :50 ]}..." )

        # Set SESSION_ID so sender_id includes job hash suffix for routing
        from cosa.agents.swe_team import cosa_interface
        cosa_interface.SESSION_ID = self.id_hash

        # Breadcrumb: Starting
        await voice_io.notify( "Dry run: Starting SWE Team simulation", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Task decomposition
        await voice_io.notify( "Dry run: Decomposing task into subtasks", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Coder delegation
        await voice_io.notify( "Dry run: Delegating subtask 1 to coder agent", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Test verification
        await voice_io.notify( "Dry run: Verifying coder output with tester agent", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Review
        await voice_io.notify( "Dry run: Reviewing implementation quality", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Breadcrumb: Summary
        await voice_io.notify( "Dry run: Generating final summary", priority="low", job_id=self.id_hash, queue_name="run" )
        await asyncio.sleep( 1.0 )

        # Mock cost summary
        self.cost_summary = {
            "duration_seconds"    : 6.0,
            "total_cost_usd"      : 0.0,
            "total_input_tokens"  : 0,
            "total_output_tokens" : 0,
        }

        completion_abstract = f"""**Dry Run Complete!**

**Task**: {self.task[ :80 ]}

**Subtasks**: 1 simulated (0 real API calls)

**Stats**: $0.00 | 0 tokens | 6.0s (simulated)"""

        # Notify completion
        await voice_io.notify(
            "Dry run complete! No cost incurred.",
            priority="medium",
            abstract=completion_abstract,
            job_id=self.id_hash,
            queue_name="run"
        )

        return "Dry run complete. SWE Team simulation finished."


def quick_smoke_test():
    """
    Quick smoke test for SweTeamJob.
    """
    import cosa.utils.util as cu

    cu.print_banner( "SweTeamJob Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.swe_team.job import SweTeamJob
        print( "✓ Module imported successfully" )

        # Test 2: Instantiation
        print( "Testing job instantiation..." )
        job = SweTeamJob(
            task       = "test task for smoke test",
            user_id    = "user123",
            user_email = "test@test.com",
            session_id = "session456",
            dry_run    = True,
            debug      = True
        )
        print( f"✓ Job created with id: {job.id_hash}" )

        # Test 3: ID format
        print( "Testing ID format..." )
        assert job.id_hash.startswith( "swe-" ), "ID should start with swe-"
        print( f"✓ ID format correct: {job.id_hash}" )

        # Test 4: last_question_asked
        print( "Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[SWE Team]" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # Test 5: is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # Test 6: Check attributes
        print( "Testing job attributes..." )
        assert job.task == "test task for smoke test"
        assert job.dry_run == True
        assert job.user_email == "test@test.com"
        assert job.status == "pending"
        print( "✓ All attributes set correctly" )

        # Test 7: Check JOB_TYPE and JOB_PREFIX
        print( "Testing class constants..." )
        assert SweTeamJob.JOB_TYPE == "swe_team"
        assert SweTeamJob.JOB_PREFIX == "swe"
        print( "✓ Class constants correct" )

        # Note: We don't test do_all() here as it requires orchestrator setup
        print( "\n⚠ Note: do_all() not tested (requires orchestrator)" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
