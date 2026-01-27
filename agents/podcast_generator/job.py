"""
Podcast Generator background job for queue-based execution.

Wraps the existing PodcastOrchestratorAgent functionality for execution
within the COSA queue system. Enables users to submit podcast generation
requests via the API and receive results asynchronously.

Example:
    job = PodcastGeneratorJob(
        research_path  = "/io/deep-research/user@email/2026.01.26-topic.md",
        user_id        = "user123",
        user_email     = "user@example.com",
        session_id     = "wise-penguin",
        target_languages = [ "en" ],
        max_segments   = None,
        debug          = True
    )
    result = job.do_all()  # Runs podcast generation and returns conversational answer
"""

import asyncio
from datetime import datetime
from typing import Optional, List

from cosa.agents.agentic_job_base import AgenticJobBase


class PodcastGeneratorJob( AgenticJobBase ):
    """
    Background job for Podcast Generator execution.

    Runs multi-phase podcast generation from a research document:
    1. Script generation from research content
    2. Script review and optional revision
    3. TTS audio generation
    4. Audio stitching into final podcast

    Sends progress notifications via cosa-voice and completion notification
    with links to generated artifacts.

    Attributes:
        research_path: Path to the Deep Research markdown document
        target_languages: List of ISO language codes for audio generation
        max_segments: Limit TTS to first N segments (cost control)
        audio_path: Path to generated audio (set after completion)
        script_path: Path to generated script (set after completion)
        cost_summary: Execution cost summary (set after completion)
    """

    JOB_TYPE   = "podcast"
    JOB_PREFIX = "pg"

    def __init__(
        self,
        research_path: str,
        user_id: str,
        user_email: str,
        session_id: str,
        target_languages: Optional[ List[ str ] ] = None,
        max_segments: Optional[ int ] = None,
        debug: bool = False,
        verbose: bool = False
    ) -> None:
        """
        Initialize a Podcast Generator job.

        Requires:
            - research_path is a valid path to a research document
            - user_id is a valid system ID
            - user_email is a valid email address
            - session_id is a WebSocket session ID

        Ensures:
            - Job ID generated with "pg-" prefix
            - All parameters stored for execution

        Args:
            research_path: Path to the Deep Research markdown document
            user_id: System ID of the job owner
            user_email: Email address for output storage
            session_id: WebSocket session for notifications
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

        # Podcast parameters
        self.research_path    = research_path
        self.target_languages = target_languages or [ "en" ]
        self.max_segments     = max_segments

        # Results (populated after execution)
        self.audio_path    = None
        self.script_path   = None
        self.cost_summary  = None

    @property
    def last_question_asked( self ) -> str:
        """
        Display string for queue UI.

        Returns truncated research path with [Podcast] prefix.

        Returns:
            str: Human-readable job description
        """
        # Extract filename from path for display
        import os
        filename = os.path.basename( self.research_path )
        truncated = filename[ :40 ] + "..." if len( filename ) > 40 else filename
        return f"[Podcast] {truncated}"

    def do_all( self ) -> str:
        """
        Execute podcast generation and return conversational answer.

        This is the main entry point called by RunningFifoQueue.
        Bridges to the async _execute() method via asyncio.run().

        Returns:
            str: Conversational answer summarizing generation results
        """
        if self.debug:
            print( f"[PodcastGeneratorJob] Starting do_all() for: {self.research_path}" )

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
                print( f"[PodcastGeneratorJob] Completed in {duration:.1f}s" )

            return result

        except Exception as e:
            self.status       = "failed"
            self.completed_at = datetime.now().isoformat()
            self.error        = str( e )

            if self.debug:
                print( f"[PodcastGeneratorJob] Failed: {e}" )
                import traceback
                traceback.print_exc()

            # Return error message as conversational answer
            self.answer_conversational = f"Podcast generation failed: {str( e )}"
            return self.answer_conversational

    async def _execute( self ) -> str:
        """
        Internal async podcast generation execution.

        Uses the PodcastOrchestratorAgent to run the full workflow.

        Returns:
            str: Conversational summary of generation results
        """
        # Import podcast components
        from cosa.agents.podcast_generator.orchestrator import PodcastOrchestratorAgent
        from cosa.agents.podcast_generator.config import PodcastConfig
        from cosa.agents.podcast_generator import voice_io, cosa_interface
        import cosa.utils.util as cu
        import os

        # Validate research document exists
        if not self.research_path.startswith( "/" ):
            full_path = cu.get_project_root() + "/" + self.research_path
        else:
            full_path = self.research_path

        if not os.path.exists( full_path ):
            raise FileNotFoundError( f"Research document not found: {self.research_path}" )

        # Set sender_id for notifications
        cosa_interface.SENDER_ID = cosa_interface._get_sender_id() + f"#{self.id_hash}"

        if self.debug:
            print( f"[PodcastGeneratorJob] Research document: {full_path}" )
            print( f"[PodcastGeneratorJob] Target languages: {self.target_languages}" )
            if self.max_segments:
                print( f"[PodcastGeneratorJob] Max segments: {self.max_segments}" )

        # Notify start
        await voice_io.notify(
            f"Starting podcast generation from: {os.path.basename( full_path )}",
            priority="medium"
        )

        # Create config
        config = PodcastConfig()

        # Create orchestrator
        agent = PodcastOrchestratorAgent(
            research_doc_path = full_path,
            user_id           = self.user_email,
            config            = config,
            target_languages  = self.target_languages,
            max_segments      = self.max_segments,
            debug             = self.debug,
            verbose           = self.verbose,
        )

        # Run the full workflow
        script = await agent.do_all_async()

        if script is None:
            await voice_io.notify( "Podcast generation was cancelled.", priority="medium" )
            return "Podcast generation was cancelled by the user."

        # Extract results from agent state
        state = agent._podcast_state
        self.audio_path  = state.get( "final_audio_path" )
        self.script_path = state.get( "final_script_path" )

        # Store artifacts
        self.artifacts[ "audio_path" ]  = self.audio_path
        self.artifacts[ "script_path" ] = self.script_path
        self.artifacts[ "podcast_id" ]  = agent.podcast_id

        # Build cost summary
        api_cost = agent.api_client.cost_estimate.estimated_cost_usd if agent._api_client else 0.0
        self.cost_summary = {
            "script_cost_usd" : api_cost,
            "audio_cost_usd"  : 0.0,  # TODO: Calculate from TTS results
            "total_cost_usd"  : api_cost,
        }
        self.artifacts[ "cost_summary" ] = self.cost_summary

        # Return conversational answer
        duration = script.estimated_duration_minutes
        return f"Podcast complete! Generated {script.get_segment_count()} segments, ~{duration:.1f} minutes. Audio: {self.audio_path}"


def quick_smoke_test():
    """
    Quick smoke test for PodcastGeneratorJob.
    """
    import cosa.utils.util as cu

    cu.print_banner( "PodcastGeneratorJob Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import
        print( "Testing module import..." )
        from cosa.agents.podcast_generator.job import PodcastGeneratorJob
        print( "✓ Module imported successfully" )

        # Test 2: Instantiation
        print( "Testing job instantiation..." )
        job = PodcastGeneratorJob(
            research_path    = "/io/deep-research/test@test.com/test-report.md",
            user_id          = "user123",
            user_email       = "test@test.com",
            session_id       = "session456",
            target_languages = [ "en" ],
            max_segments     = 5,
            debug            = True
        )
        print( f"✓ Job created with id: {job.id_hash}" )

        # Test 3: ID format
        print( "Testing ID format..." )
        assert job.id_hash.startswith( "pg-" ), "ID should start with pg-"
        print( f"✓ ID format correct: {job.id_hash}" )

        # Test 4: last_question_asked
        print( "Testing last_question_asked..." )
        lqa = job.last_question_asked
        assert "[Podcast]" in lqa
        print( f"✓ last_question_asked: {lqa}" )

        # Test 5: is_cacheable
        print( "Testing is_cacheable property..." )
        assert job.is_cacheable == False
        print( "✓ is_cacheable correctly returns False" )

        # Test 6: Check attributes
        print( "Testing job attributes..." )
        assert job.research_path == "/io/deep-research/test@test.com/test-report.md"
        assert job.target_languages == [ "en" ]
        assert job.max_segments == 5
        assert job.user_email == "test@test.com"
        assert job.status == "pending"
        print( "✓ All attributes set correctly" )

        # Test 7: Check JOB_TYPE and JOB_PREFIX
        print( "Testing class constants..." )
        assert PodcastGeneratorJob.JOB_TYPE == "podcast"
        assert PodcastGeneratorJob.JOB_PREFIX == "pg"
        print( "✓ Class constants correct" )

        # Note: We don't test do_all() here as it requires API keys and files
        print( "\n⚠ Note: do_all() not tested (requires API keys and research doc)" )

        print( "\n✓ Smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
