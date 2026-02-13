"""
Claude Code background job for queue-based execution.

Wraps the existing ClaudeCodeDispatcher functionality for execution
within the CJ Flow (COSA Job Flow) queue system. Enables users to submit
Claude Code tasks via the API and receive results asynchronously.

Supports both task types:
    - BOUNDED: Fire-and-forget, runs to completion
    - INTERACTIVE: Bidirectional via notification service

Example:
    job = ClaudeCodeJob(
        prompt      = "Run the tests and fix any failures",
        project     = "lupin",
        user_id     = "user123",
        user_email  = "user@example.com",
        session_id  = "wise-penguin",
        task_type   = "BOUNDED",
        max_turns   = 50,
        debug       = True
    )
    result = job.do_all()  # Runs task and returns conversational answer
"""

import asyncio
from datetime import datetime
from typing import Optional

from cosa.agents.agentic_job_base import AgenticJobBase


class ClaudeCodeJob( AgenticJobBase ):
    """
    Background job for Claude Code execution via CJ Flow.

    Wraps ClaudeCodeDispatcher for queue-based execution with full
    notification support via cosa-voice MCP tools.

    Attributes:
        prompt: The task prompt for Claude Code
        project: Target project name (e.g., "lupin", "cosa")
        task_type: "BOUNDED" or "INTERACTIVE"
        max_turns: Maximum agentic turns (default 50)
        cost_usd: Execution cost (set after completion)
        output_text: Task output (set after completion)
    """

    JOB_TYPE   = "claude_code"
    JOB_PREFIX = "cc"

    # Config-driven defaults (loaded once at class level, overridden per-instance)
    _config_defaults_loaded = False
    _default_max_turns      = 50
    _default_timeout        = 3600

    @classmethod
    def _load_config_defaults( cls ):
        """Load defaults from ConfigurationManager (once per process)."""
        if cls._config_defaults_loaded:
            return
        try:
            from cosa.app.configuration_manager import ConfigurationManager
            config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            cls._default_max_turns = config_mgr.get( "claude code job max turns default", default=50, return_type="int" )
            cls._default_timeout   = config_mgr.get( "claude code job timeout seconds default", default=3600, return_type="int" )
        except Exception:
            pass  # Fall back to hardcoded defaults if config unavailable
        cls._config_defaults_loaded = True

    def __init__(
        self,
        prompt: str,
        project: str,
        user_id: str,
        user_email: str,
        session_id: str,
        task_type: str = "BOUNDED",
        max_turns: int = None,
        timeout_seconds: int = None,
        dry_run: bool = False,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a Claude Code job.

        Requires:
            - prompt is a non-empty string
            - project is a valid project name
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID
            - task_type is "BOUNDED" or "INTERACTIVE"

        Ensures:
            - Job ID generated with "cc-" prefix
            - All parameters stored for execution
            - Defaults loaded from ConfigurationManager when params are None

        Args:
            prompt: The task prompt for Claude Code
            project: Target project name (e.g., "lupin", "cosa")
            user_id: System ID of the job owner
            user_email: Email address for user association
            session_id: WebSocket session for notifications
            task_type: "BOUNDED" (default) or "INTERACTIVE"
            max_turns: Maximum agentic turns (None = load from config, default 50)
            timeout_seconds: Task timeout (None = load from config, default 3600)
            dry_run: If True, simulate execution without running Claude Code
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

        # Load config defaults if not yet loaded
        self._load_config_defaults()

        # Claude Code task parameters (use config defaults when not explicitly provided)
        self.prompt          = prompt
        self.project         = project
        self.task_type       = task_type.upper()
        self.max_turns       = max_turns if max_turns is not None else self._default_max_turns
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self._default_timeout
        self.dry_run         = dry_run

        # Results (populated after execution)
        self.task_result  = None
        self.cost_usd     = None
        self.output_text  = None
        self.cost_summary = None  # Required by queues.py for unified job interface

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns truncated prompt with task type prefix.

        Returns:
            str: Human-readable job description
        """
        prefix = "Bounded" if self.task_type == "BOUNDED" else "Interactive"
        truncated = self.prompt[ :50 ] + "..." if len( self.prompt ) > 50 else self.prompt
        return f"[Claude Code - {prefix}] {truncated}"

    def do_all( self ) -> str:
        """
        Execute Claude Code task and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing results
        """
        if self.debug:
            print( f"[ClaudeCodeJob] Starting do_all() for: {self.prompt[ :50 ]}..." )

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
                print( f"[ClaudeCodeJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            self.status       = "failed"
            self.completed_at = datetime.now().isoformat()
            self.error        = str( e )

            if self.debug:
                print( f"[ClaudeCodeJob] Failed: {e}" )
                import traceback
                traceback.print_exc()

            # Return error message as conversational answer
            self.answer_conversational = f"Claude Code task failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Internal async task execution.

        Uses ClaudeCodeDispatcher to run the task with MCP voice tools.
        Notifications route through the notification service with job_id
        for proper job card association.

        Returns:
            str: Conversational summary of task results
        """
        # Check for dry-run mode first
        if self.dry_run:
            return await self._execute_dry_run()

        from cosa.orchestration.claude_code import ClaudeCodeDispatcher, Task, TaskType

        # Import cosa_interface for notifications (uses notification API directly)
        from cosa.agents.claude_code import cosa_interface

        # Notify start
        await cosa_interface.notify_progress(
            f"Starting Claude Code task: {self.prompt[ :60 ]}...",
            priority="low",
            job_id=self.id_hash
        )

        if self.debug:
            print( f"[ClaudeCodeJob] Dispatching {self.task_type} task" )
            print( f"[ClaudeCodeJob] Project: {self.project}" )
            print( f"[ClaudeCodeJob] Max turns: {self.max_turns}" )

        # Create dispatcher
        dispatcher = ClaudeCodeDispatcher(
            on_message=self._on_message_callback
        )

        # Create task
        task_type_enum = TaskType.BOUNDED if self.task_type == "BOUNDED" else TaskType.INTERACTIVE

        task = Task(
            id              = self.id_hash,
            project         = self.project,
            prompt          = self.prompt,
            type            = task_type_enum,
            max_turns       = self.max_turns,
            timeout_seconds = self.timeout_seconds
        )

        # Dispatch and collect result
        result = await dispatcher.dispatch( task )

        # Store task result
        self.task_result = result

        if result.success:
            # Store artifacts
            self.cost_usd     = result.cost_usd or 0.0
            self.output_text  = result.result or ""
            self.cost_summary = {
                "total_cost_usd" : self.cost_usd
            }

            self.artifacts = {
                "cost_usd"    : self.cost_usd,
                "output_text" : self.output_text[ :500 ] if self.output_text else "",
                "task_type"   : self.task_type,
                "project"     : self.project,
                "session_id"  : result.session_id,
                "duration_ms" : result.duration_ms
            }

            # Format completion message
            cost_str = f"${self.cost_usd:.4f}" if self.cost_usd else "$0.00"
            duration_str = f"{result.duration_ms / 1000:.1f}s" if result.duration_ms else "N/A"

            completion_abstract = f"""**Claude Code Task Complete!**

**Task**: {self.prompt[ :100 ]}...

**Stats**: {cost_str} | {duration_str}

**Output**: {self.output_text[ :200 ] if self.output_text else "No output"}..."""

            # Notify completion
            await cosa_interface.notify_progress(
                f"Claude Code task complete. Cost: {cost_str}",
                priority="medium",
                abstract=completion_abstract,
                job_id=self.id_hash
            )

            return f"Claude Code task completed. Cost: {cost_str}. {self.output_text[ :200 ] if self.output_text else ''}"

        else:
            # Task failed
            error_msg = result.error or "Unknown error"
            self.artifacts = {
                "error"     : error_msg,
                "task_type" : self.task_type,
                "project"   : self.project,
                "exit_code" : result.exit_code
            }

            await cosa_interface.notify_progress(
                f"Claude Code task failed: {error_msg[ :80 ]}",
                priority="urgent",
                job_id=self.id_hash
            )

            raise RuntimeError( f"Claude Code task failed: {error_msg}" )

    async def _execute_dry_run( self ) -> str:
        """
        Simulate ClaudeCodeJob execution for testing queue flow.

        Sends breadcrumb notifications and returns mock results.
        Does NOT invoke actual Claude Code execution.

        Ensures:
            - Sends 5 breadcrumb notifications
            - Sets mock results with $0.00 cost
            - Returns mock completion message

        Returns:
            str: Mock completion message
        """
        from cosa.agents.claude_code import cosa_interface
        import asyncio

        task_type_display = "Bounded" if self.task_type == "BOUNDED" else "Interactive"

        # Breadcrumb 1: Initialization
        await cosa_interface.notify_progress(
            f"Dry run: Initializing Claude Code ({task_type_display})",
            priority="low",
            job_id=self.id_hash
        )
        await asyncio.sleep( 1.0 )

        # Breadcrumb 2: Task parsing
        await cosa_interface.notify_progress(
            f"Dry run: Parsing task prompt ({len( self.prompt )} chars)",
            priority="low",
            job_id=self.id_hash
        )
        await asyncio.sleep( 1.0 )

        # Breadcrumb 3: Project setup
        await cosa_interface.notify_progress(
            f"Dry run: Preparing project '{self.project}'",
            priority="low",
            job_id=self.id_hash
        )
        await asyncio.sleep( 1.0 )

        # Breadcrumb 4: Simulated execution
        await cosa_interface.notify_progress(
            f"Dry run: Simulating {task_type_display.lower()} execution",
            priority="low",
            job_id=self.id_hash
        )
        await asyncio.sleep( 1.0 )

        # Breadcrumb 5: Completion
        await cosa_interface.notify_progress(
            f"Dry run: Generating completion report",
            priority="low",
            job_id=self.id_hash
        )
        await asyncio.sleep( 1.0 )

        # Set mock results
        self.output_text  = f"Mock {task_type_display} execution completed for: {self.prompt[ :100 ]}..."
        self.cost_usd     = 0.0
        self.cost_summary = {
            "total_cost_usd" : 0.0
        }
        self.artifacts    = {
            "cost_usd"   : 0.0,
            "output_text": self.output_text,
            "task_type"  : self.task_type,
            "project"    : self.project,
            "dry_run"    : True
        }
        self.status = "completed"

        # Completion notification with abstract
        completion_abstract = f"""**Mock Claude Code Job Complete**

- **Job ID**: {self.id_hash}
- **Type**: {task_type_display}
- **Project**: {self.project}
- **Cost**: $0.00 (dry-run)
- **Duration**: ~5s (simulated)

This was a dry-run simulation. No actual Claude Code execution occurred."""

        await cosa_interface.notify_progress(
            f"Dry run complete: {self.id_hash}",
            priority="medium",
            abstract=completion_abstract,
            job_id=self.id_hash
        )

        return self.output_text

    def _on_message_callback( self, task_id: str, message ) -> None:
        """
        Callback for streaming messages from dispatcher.

        Logs messages in debug mode. Messages are primarily for
        WebSocket streaming in direct mode; in queue mode, notifications
        use the cosa-voice MCP tools instead.

        Args:
            task_id: The task ID
            message: Message object (dict or SDK type)
        """
        if self.debug:
            msg_type = message.get( "type", "unknown" ) if isinstance( message, dict ) else type( message ).__name__
            print( f"[ClaudeCodeJob] Message: {msg_type}" )


def quick_smoke_test():
    """
    Quick smoke test for ClaudeCodeJob.
    """
    import cosa.utils.util as cu

    cu.print_banner( "ClaudeCodeJob Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.claude_code.job import ClaudeCodeJob
        print( "✓ Module imported successfully" )

        # Test 2: Instantiation
        print( "Testing job instantiation..." )
        job = ClaudeCodeJob(
            prompt     = "Run the tests",
            project    = "lupin",
            user_id    = "user123",
            user_email = "test@test.com",
            session_id = "session456",
            task_type  = "BOUNDED",
            debug      = True
        )
        print( f"✓ Job created with id: {job.id_hash}" )

        # Test 3: ID format
        print( "Testing ID format..." )
        assert job.id_hash.startswith( "cc-" ), "ID should start with cc-"
        assert len( job.id_hash ) == 11, f"ID should be 11 chars, got {len( job.id_hash )}"
        print( f"✓ ID format correct: {job.id_hash}" )

        # Test 4: last_question_asked
        print( "Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[Claude Code - Bounded]" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # Test 5: is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # Test 6: Check attributes
        print( "Testing job attributes..." )
        assert job.prompt == "Run the tests"
        assert job.project == "lupin"
        assert job.task_type == "BOUNDED"
        assert job.max_turns == 50
        assert job.status == "pending"
        print( "✓ All attributes set correctly" )

        # Test 7: Check JOB_TYPE and JOB_PREFIX
        print( "Testing class constants..." )
        assert ClaudeCodeJob.JOB_TYPE == "claude_code"
        assert ClaudeCodeJob.JOB_PREFIX == "cc"
        print( "✓ Class constants correct" )

        # Test 8: Test INTERACTIVE mode
        print( "Testing INTERACTIVE mode..." )
        job_interactive = ClaudeCodeJob(
            prompt     = "Let's work on the auth refactor",
            project    = "cosa",
            user_id    = "user456",
            user_email = "user@test.com",
            session_id = "session789",
            task_type  = "INTERACTIVE",
            max_turns  = 200,
            debug      = False
        )
        assert job_interactive.task_type == "INTERACTIVE"
        assert job_interactive.max_turns == 200
        assert "[Claude Code - Interactive]" in job_interactive.last_question_asked
        print( f"✓ INTERACTIVE job created: {job_interactive.id_hash}" )

        # Test 9: Test unified interface properties
        print( "Testing unified interface properties..." )
        assert job.question == job.last_question_asked, "question should equal last_question_asked"
        assert job.job_type == "claude_code", "job_type should equal JOB_TYPE"
        assert job.created_date == job.run_date, "created_date should equal run_date"
        print( "✓ Unified interface properties work correctly" )

        # Test 10: Test dry_run flag
        print( "Testing dry_run flag..." )
        assert job.dry_run == False, "Default dry_run should be False"
        job_dry = ClaudeCodeJob(
            prompt     = "Test dry run",
            project    = "lupin",
            user_id    = "user789",
            user_email = "dry@test.com",
            session_id = "session_dry",
            dry_run    = True
        )
        assert job_dry.dry_run == True, "dry_run should be True when set"
        print( "✓ dry_run flag works correctly" )

        # Test 11: Test cost_summary attribute
        print( "Testing cost_summary attribute..." )
        assert hasattr( job, 'cost_summary' ), "Job should have cost_summary attribute"
        assert job.cost_summary is None, "cost_summary should be None initially"
        print( "✓ cost_summary attribute exists and is None by default" )

        # Note: We don't test do_all() here as it requires Claude Code CLI
        print( "\n* Note: do_all() not tested (requires Claude Code CLI)" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
