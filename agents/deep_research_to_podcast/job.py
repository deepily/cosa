"""
Deep Research to Podcast background job for queue-based execution.

Wraps the existing DeepResearchToPodcastAgent functionality for execution
within the COSA queue system. Enables users to submit chained research→podcast
workflows via the API and receive results asynchronously.

Example:
    job = DeepResearchToPodcastJob(
        query          = "State of AI safety in 2026",
        user_id        = "user123",
        user_email     = "user@example.com",
        session_id     = "wise-penguin",
        budget         = 3.00,
        target_languages = [ "en" ],
        max_segments   = None,
        debug          = True
    )
    result = job.do_all()  # Runs full pipeline and returns conversational answer
"""

import asyncio
from datetime import datetime
from typing import Optional, List

from cosa.agents.agentic_job_base import AgenticJobBase


class DeepResearchToPodcastJob( AgenticJobBase ):
    """
    Background job for Deep Research → Podcast pipeline execution.

    Runs a chained workflow:
    1. Deep Research: Web search, synthesis, report generation
    2. Podcast Generation: Script creation, TTS, audio stitching

    Sends progress notifications via cosa-voice and completion notification
    with links to all generated artifacts.

    Attributes:
        query: The research topic/question to investigate
        budget: Maximum budget in USD for Deep Research (None = unlimited)
        target_languages: List of ISO language codes for audio generation
        max_segments: Limit TTS to first N segments (cost control)
        research_path: Path to generated research report (set after completion)
        audio_path: Path to generated audio (set after completion)
        script_path: Path to generated script (set after completion)
        cost_summary: Combined execution cost summary (set after completion)
    """

    JOB_TYPE   = "research_to_podcast"
    JOB_PREFIX = "rp"

    def __init__(
        self,
        query: str,
        user_id: str,
        user_email: str,
        session_id: str,
        budget: Optional[ float ] = None,
        target_languages: Optional[ List[ str ] ] = None,
        max_segments: Optional[ int ] = None,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a Deep Research to Podcast job.

        Requires:
            - query is a non-empty string
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with "rp-" prefix
            - All parameters stored for execution

        Args:
            query: The research topic/question to investigate
            user_id: System ID of the job owner
            user_email: Email address for output storage
            session_id: WebSocket session for notifications
            budget: Maximum budget in USD for Deep Research (None = unlimited)
            target_languages: List of ISO language codes (default: ["en"])
            max_segments: Limit TTS to first N segments (None = all)
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

        # Pipeline parameters
        self.query            = query
        self.budget           = budget
        self.target_languages = target_languages or [ "en" ]
        self.max_segments     = max_segments

        # Results (populated after execution)
        self.research_path = None
        self.audio_path    = None
        self.script_path   = None
        self.cost_summary  = None

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns truncated query with [Research→Podcast] prefix.

        Returns:
            str: Human-readable job description
        """
        truncated = self.query[ :40 ] + "..." if len( self.query ) > 40 else self.query
        return f"[Research→Podcast] {truncated}"

    def do_all( self ) -> str:
        """
        Execute research→podcast pipeline and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing pipeline results
        """
        if self.debug:
            print( f"[DeepResearchToPodcastJob] Starting do_all() for: {self.query[ :50 ]}..." )

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
                print( f"[DeepResearchToPodcastJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            self.status       = "failed"
            self.completed_at = datetime.now().isoformat()
            self.error        = str( e )

            if self.debug:
                print( f"[DeepResearchToPodcastJob] Failed: {e}" )
                import traceback
                traceback.print_exc()

            # Return error message as conversational answer
            self.answer_conversational = f"Research→Podcast pipeline failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Internal async pipeline execution.

        Uses the DeepResearchToPodcastAgent to run the full workflow.

        Returns:
            str: Conversational summary of pipeline results
        """
        # Import pipeline components
        from cosa.agents.deep_research_to_podcast.agent import DeepResearchToPodcastAgent
        from cosa.agents.deep_research_to_podcast.state import PipelineState
        from cosa.agents.deep_research import voice_io, cosa_interface

        # Set sender_id for notifications
        cosa_interface.SENDER_ID = cosa_interface._get_sender_id() + f"#{self.id_hash}"

        if self.debug:
            print( f"[DeepResearchToPodcastJob] Query: {self.query[ :80 ]}..." )
            print( f"[DeepResearchToPodcastJob] Budget: ${self.budget}" if self.budget else "[DeepResearchToPodcastJob] Budget: unlimited" )
            print( f"[DeepResearchToPodcastJob] Target languages: {self.target_languages}" )

        # Notify start
        await voice_io.notify(
            f"Starting research→podcast pipeline: {self.query[ :60 ]}...",
            priority="medium"
        )

        # Create the chained agent
        agent = DeepResearchToPodcastAgent(
            query            = self.query,
            user_email       = self.user_email,
            budget           = self.budget,
            target_languages = self.target_languages,
            max_segments     = self.max_segments,
            cli_mode         = False,  # Voice-driven mode for queue
            debug            = self.debug,
            verbose          = self.verbose,
        )

        # Run the full pipeline
        result = await agent.run_async()

        # Check result state
        if result.state == PipelineState.CANCELLED:
            await voice_io.notify( "Pipeline was cancelled.", priority="medium" )
            return "Research→Podcast pipeline was cancelled by the user."

        if result.state == PipelineState.FAILED:
            error_msg = result.error or "Unknown error"
            await voice_io.notify( f"Pipeline failed: {error_msg[ :80 ]}", priority="urgent" )
            raise Exception( error_msg )

        # Store results
        self.research_path = result.research_path
        self.audio_path    = result.audio_path
        self.script_path   = result.script_path

        # Store artifacts
        self.artifacts[ "research_path" ]     = result.research_path
        self.artifacts[ "research_abstract" ] = result.research_abstract
        self.artifacts[ "audio_path" ]        = result.audio_path
        self.artifacts[ "script_path" ]       = result.script_path

        # Build cost summary
        self.cost_summary = {
            "dr_cost_usd"    : result.dr_cost,
            "pg_cost_usd"    : result.pg_cost,
            "total_cost_usd" : result.total_cost,
        }
        self.artifacts[ "cost_summary" ] = self.cost_summary

        # Return conversational answer
        return f"Pipeline complete! Research report and podcast generated. Total cost: ${result.total_cost:.4f}. Audio: {self.audio_path}"


def quick_smoke_test():
    """
    Quick smoke test for DeepResearchToPodcastJob.
    """
    import cosa.utils.util as cu

    cu.print_banner( "DeepResearchToPodcastJob Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.deep_research_to_podcast.job import DeepResearchToPodcastJob
        print( "✓ Module imported successfully" )

        # Test 2: Instantiation
        print( "Testing job instantiation..." )
        job = DeepResearchToPodcastJob(
            query            = "test query for smoke test",
            user_id          = "user123",
            user_email       = "test@test.com",
            session_id       = "session456",
            budget           = 2.00,
            target_languages = [ "en" ],
            max_segments     = 5,
            debug            = True
        )
        print( f"✓ Job created with id: {job.id_hash}" )

        # Test 3: ID format
        print( "Testing ID format..." )
        assert job.id_hash.startswith( "rp-" ), "ID should start with rp-"
        print( f"✓ ID format correct: {job.id_hash}" )

        # Test 4: last_question_asked
        print( "Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[Research→Podcast]" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # Test 5: is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # Test 6: Check attributes
        print( "Testing job attributes..." )
        assert job.query == "test query for smoke test"
        assert job.budget == 2.00
        assert job.target_languages == [ "en" ]
        assert job.max_segments == 5
        assert job.user_email == "test@test.com"
        assert job.status == "pending"
        print( "✓ All attributes set correctly" )

        # Test 7: Check JOB_TYPE and JOB_PREFIX
        print( "Testing class constants..." )
        assert DeepResearchToPodcastJob.JOB_TYPE == "research_to_podcast"
        assert DeepResearchToPodcastJob.JOB_PREFIX == "rp"
        print( "✓ Class constants correct" )

        # Note: We don't test do_all() here as it requires API keys and network
        print( "\n⚠ Note: do_all() not tested (requires API keys and services)" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
