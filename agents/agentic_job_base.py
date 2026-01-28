"""
Base class for long-running Claude Code agentic jobs.

Provides shared behaviors across agentic processes that:
- Run asynchronously in the queue system
- Take minutes (not seconds) to complete
- Send progress notifications during execution
- Generate artifacts (reports, audio, etc.)
- Don't cache/snapshot (each run is unique)

This is a parallel hierarchy to AgentBase - agentic jobs have different
execution models (async, long-running) than simple agents (sync, fast).

Examples:
    - DeepResearchJob: Multi-minute web research with synthesis
    - PodcastGenerationJob: Audio generation from content (future)
"""

from abc import ABC, abstractmethod
import uuid
from datetime import datetime
from typing import Optional, Dict, Any


class AgenticJobBase( ABC ):
    """
    Abstract base class for Claude Code agentic background jobs.

    Implements the interface expected by RunningFifoQueue:
    - id_hash: Unique identifier
    - last_question_asked: Display string for UI
    - user_id: Owner of the job
    - session_id: WebSocket session for notifications
    - push_counter: Queue position tracking
    - do_all(): Execute job and return result

    Provides shared functionality:
    - Job ID generation with type prefix
    - Progress notification helpers
    - Execution timing
    - Error handling patterns

    Key Differences from AgentBase:
    - No LLM client factory or prompt template integration
    - No code execution or XML parsing
    - Async internal execution model
    - Always non-cacheable
    - Direct integration with existing CLI tools (e.g., Deep Research CLI)
    """

    # Job type identifier (override in subclasses)
    JOB_TYPE   = "agentic"
    JOB_PREFIX = "aj"

    def __init__(
        self,
        user_id: str,
        user_email: str,
        session_id: str,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a base agentic job.

        Requires:
            - user_id is a valid system ID (uid from auth)
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with type prefix
            - Execution state initialized to "pending"
            - All instance variables set for queue system compatibility

        Args:
            user_id: System ID of the job owner (uid)
            user_email: Email address of the user (for multi-tenancy)
            session_id: WebSocket session ID for notifications
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.user_id      = user_id
        self.user_email   = user_email
        self.session_id   = session_id
        self.debug        = debug
        self.verbose      = verbose

        # Queue system required attributes (compatible with SolutionSnapshot/AgentBase)
        self.id_hash      = self._generate_id()
        self.push_counter = 0
        self.run_date     = datetime.now().isoformat()

        # Execution state tracking
        self.started_at   = None
        self.completed_at = None
        self.status       = "pending"  # pending, running, completed, failed
        self.error        = None

        # Results (populated by subclasses after execution)
        self.result       = None
        self.artifacts    = {}  # e.g., {"report_path": "...", "audio_path": "..."}

        # For compatibility with queue UI display
        self.answer_conversational = None
        self.routing_command       = self.JOB_TYPE

    def _generate_id( self ) -> str:
        """
        Generate unique job ID with type prefix.

        Returns:
            str: Job ID in format "{prefix}-{uuid8}" (e.g., "dr-a1b2c3d4")
        """
        return f"{self.JOB_PREFIX}-{uuid.uuid4().hex[ :8 ]}"

    @property
    @abstractmethod
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Must be overridden by subclasses to provide human-readable
        description of the job for the queue visualization.

        Returns:
            str: Human-readable job description
        """
        pass

    # =========================================================================
    # Unified Interface Properties (for QueueableJob protocol compatibility)
    # =========================================================================

    @property
    def question( self ) -> str:
        """
        Raw question text (unified interface).

        For agentic jobs, this is the same as last_question_asked.
        Provides compatibility with SolutionSnapshot and AgentBase interfaces.

        Returns:
            str: The question/task description
        """
        return self.last_question_asked

    @property
    def answer( self ) -> str:
        """
        Raw answer text (unified interface).

        For agentic jobs, this returns the conversational answer or empty string.
        Provides compatibility with SolutionSnapshot interface.

        Returns:
            str: The answer/result text
        """
        return self.answer_conversational or ""

    @property
    def job_type( self ) -> str:
        """
        Unified job type identifier.

        Returns the JOB_TYPE class attribute for consistent type identification
        across all job types (AgentBase, SolutionSnapshot, AgenticJobBase).

        Returns:
            str: Job type identifier (e.g., "deep_research", "podcast")
        """
        return self.JOB_TYPE

    @property
    def created_date( self ) -> str:
        """
        Creation timestamp (unified interface).

        For agentic jobs, this is the same as run_date since jobs are
        created and queued simultaneously.

        Returns:
            str: ISO format timestamp of job creation
        """
        return self.run_date

    @abstractmethod
    def do_all( self ) -> str:
        """
        Execute the job and return result.

        This is the main entry point called by RunningFifoQueue.
        Must be overridden by subclasses to implement job logic.

        For async jobs, this method should use asyncio.run() to
        bridge to the async _execute() method.

        Returns:
            str: Conversational answer for the queue system
        """
        pass

    @abstractmethod
    async def _execute( self ) -> str:
        """
        Internal async execution logic.

        Override in subclasses to implement the actual job workflow.
        This method runs within asyncio.run() called from do_all().

        Returns:
            str: Result of the job execution
        """
        pass

    @property
    def is_cacheable( self ) -> bool:
        """
        Whether this job type should be cached.

        Agentic jobs are never cached because:
        - Each research query depends on current web content
        - Podcast content may be updated
        - Results are inherently time-sensitive

        Returns:
            bool: Always False for agentic jobs
        """
        return False

    def code_ran_to_completion( self ) -> bool:
        """
        Check if job execution completed successfully.

        Used by RunningFifoQueue._handle_base_agent() for compatibility.
        For agentic jobs, this checks the status field.

        Returns:
            bool: True if status is "completed"
        """
        return self.status == "completed"

    def formatter_ran_to_completion( self ) -> bool:
        """
        Check if output formatting completed.

        For agentic jobs, formatting is done within _execute(),
        so this returns True if the job completed successfully.

        Returns:
            bool: True if answer_conversational is set
        """
        return self.answer_conversational is not None

    def notify_progress( self, message: str, priority: str = "low" ) -> None:
        """
        Send progress notification via cosa-voice.

        Args:
            message: Progress message to send
            priority: Notification priority (low, medium, high, urgent)
        """
        # Import here to avoid circular imports
        try:
            import asyncio
            from cosa.agents.deep_research import voice_io

            # Use asyncio.run() if not in async context, otherwise schedule
            try:
                loop = asyncio.get_running_loop()
                # Already in async context - create task
                asyncio.create_task( voice_io.notify( message, priority=priority ) )
            except RuntimeError:
                # No running loop - use asyncio.run()
                asyncio.run( voice_io.notify( message, priority=priority ) )

        except ImportError as e:
            if self.debug:
                print( f"[AgenticJobBase] Could not import voice_io: {e}" )
        except Exception as e:
            if self.debug:
                print( f"[AgenticJobBase] Notification error: {e}" )

    def notify_completion( self, message: str, abstract: str = None ) -> None:
        """
        Send completion notification with optional abstract.

        Args:
            message: Completion message to send
            abstract: Optional detailed information (markdown)
        """
        try:
            import asyncio
            from cosa.agents.deep_research import voice_io

            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task( voice_io.notify( message, priority="medium", abstract=abstract ) )
            except RuntimeError:
                asyncio.run( voice_io.notify( message, priority="medium", abstract=abstract ) )

        except ImportError as e:
            if self.debug:
                print( f"[AgenticJobBase] Could not import voice_io: {e}" )
        except Exception as e:
            if self.debug:
                print( f"[AgenticJobBase] Notification error: {e}" )

    def get_execution_duration_seconds( self ) -> float:
        """
        Get job execution duration in seconds.

        Returns:
            float: Duration in seconds, or 0 if not started/completed
        """
        if not self.started_at or not self.completed_at:
            return 0.0

        from datetime import datetime
        start = datetime.fromisoformat( self.started_at )
        end   = datetime.fromisoformat( self.completed_at )
        return ( end - start ).total_seconds()

    def get_html( self ) -> str:
        """
        Generate HTML representation for queue visualization.

        Compatible with AgentBase.get_html() for queue display.

        Returns:
            str: HTML list item element
        """
        return f"<li id='{self.id_hash}'>{self.run_date} [{self.JOB_TYPE}] {self.last_question_asked}</li>"

    def __repr__( self ) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__} id={self.id_hash} status={self.status}>"


def quick_smoke_test():
    """
    Quick smoke test for AgenticJobBase.
    """
    import cosa.utils.util as cu

    cu.print_banner( "AgenticJobBase Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.agentic_job_base import AgenticJobBase
        print( "✓ Module imported successfully" )

        # Test 2: Can't instantiate abstract class
        print( "Testing abstract class protection..." )
        try:
            AgenticJobBase( "user1", "test@test.com", "session1" )
            print( "✗ Should not instantiate abstract class!" )
        except TypeError:
            print( "✓ Abstract class correctly prevents instantiation" )

        # Test 3: Create minimal concrete subclass
        print( "Testing concrete subclass..." )

        class TestJob( AgenticJobBase ):
            JOB_TYPE   = "test"
            JOB_PREFIX = "tj"

            def __init__( self, query, *args, **kwargs ):
                super().__init__( *args, **kwargs )
                self.query = query

            @property
            def last_question_asked( self ):
                return f"[Test] {self.query}"

            def do_all( self ):
                self.status = "completed"
                self.answer_conversational = "Test complete"
                return self.answer_conversational

            async def _execute( self ):
                return "executed"

        job = TestJob(
            query      = "test query",
            user_id    = "user123",
            user_email = "test@example.com",
            session_id = "session456",
            debug      = True
        )

        # Test 4: Check ID format
        print( f"Testing ID format: {job.id_hash}" )
        assert job.id_hash.startswith( "tj-" ), "ID should start with tj-"
        assert len( job.id_hash ) == 11, "ID should be 11 chars (prefix + 8)"
        print( f"✓ ID format correct: {job.id_hash}" )

        # Test 5: Check last_question_asked
        print( f"Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[Test]" in lqa
        assert "test query" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # Test 6: Check is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # Test 7: Test do_all()
        print( "Testing do_all() execution..." )
        result = job.do_all()
        assert result == "Test complete"
        assert job.status == "completed"
        assert job.code_ran_to_completion() == True
        assert job.formatter_ran_to_completion() == True
        print( "✓ do_all() executed successfully" )

        # Test 8: Test get_html()
        print( "Testing get_html()..." )
        html = job.get_html()
        assert job.id_hash in html
        assert "[test]" in html
        print( f"✓ get_html() works: {html[ :60 ]}..." )

        # Test 9: Test unified interface properties
        print( "Testing unified interface properties..." )
        assert job.question == job.last_question_asked, "question should equal last_question_asked"
        assert job.answer == "Test complete", "answer should equal answer_conversational"
        assert job.job_type == "test", "job_type should equal JOB_TYPE"
        assert job.created_date == job.run_date, "created_date should equal run_date"
        print( "✓ Unified interface properties work correctly" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
