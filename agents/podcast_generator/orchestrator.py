#!/usr/bin/env python3
"""
Podcast Orchestrator Agent - Top-level coordinator for podcast generation.

This agent manages the entire podcast generation workflow internally as a single
queue entry, yielding control at I/O boundaries via async/await.

Design Pattern: Top-Level Orchestrator
- Single job in queue, multi-phase internal state machine
- Async execution for non-blocking queue behavior
- Queryable state for external monitoring
- Controllable via pause/resume/stop

Phase 1 (This File): Script generation from research documents
Phase 2 (Future): TTS audio generation and stitching
"""

import asyncio
import time
import logging
import os
import uuid
from typing import Optional
from datetime import datetime

from .config import PodcastConfig
from .state import (
    OrchestratorState,
    PodcastState,
    PodcastScript,
    ScriptSegment,
    ContentAnalysis,
    PodcastMetadata,
    create_initial_state,
)
from . import cosa_interface
from .api_client import PodcastAPIClient
from .prompts import (
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    CONTENT_ANALYSIS_SYSTEM_PROMPT,
    get_script_generation_prompt,
    get_content_analysis_prompt,
    get_script_revision_prompt,
    parse_script_response,
    parse_analysis_response,
    get_dynamic_duo_description,
)

logger = logging.getLogger( __name__ )


class PodcastOrchestratorAgent:
    """
    Top-level orchestrator for podcast generation - single job, multi-phase, async.

    This is a standalone class (not inheriting from AgentBase) because:
    - AgentBase is synchronous, this is async
    - Different execution model (yields on await vs blocking)
    - Composition over inheritance for COSA integration

    Requires:
        - research_doc_path points to a valid file
        - user_id is a valid system identifier

    Ensures:
        - Manages entire podcast workflow internally
        - Yields control at I/O boundaries (await points)
        - State is queryable via get_state()
        - Can be paused, resumed, or stopped externally
    """

    def __init__(
        self,
        research_doc_path: str,
        user_id: str,
        config: Optional[ PodcastConfig ] = None,
        debug: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the podcast orchestrator.

        Args:
            research_doc_path: Path to the Deep Research markdown document
            user_id: System user ID for event routing
            config: Podcast configuration (uses defaults if None)
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.research_doc_path = research_doc_path
        self.user_id           = user_id
        self.config            = config or PodcastConfig()
        self.debug             = debug
        self.verbose           = verbose

        # State management
        self.state = OrchestratorState.LOADING_RESEARCH
        self._pause_requested = False
        self._stop_requested  = False

        # Initialize internal state (TypedDict for tracking)
        self._podcast_state = create_initial_state( research_doc_path, user_id )

        # Generate podcast ID
        self.podcast_id = f"podcast-{uuid.uuid4().hex[ :8 ]}"

        # Initialize API client (lazy - created on first use)
        self._api_client: Optional[ PodcastAPIClient ] = None

        # Metrics
        self.metrics = {
            "start_time"  : None,
            "end_time"    : None,
            "api_calls"   : 0,
            "tokens_used" : 0,
        }

        if self.debug:
            print( f"[PodcastOrchestratorAgent] Initialized for: {research_doc_path}" )
            print( f"[PodcastOrchestratorAgent] Podcast ID: {self.podcast_id}" )

    @property
    def api_client( self ) -> PodcastAPIClient:
        """Lazy initialization of API client."""
        if self._api_client is None:
            self._api_client = PodcastAPIClient(
                config  = self.config,
                debug   = self.debug,
                verbose = self.verbose,
            )
        return self._api_client

    async def do_all_async( self ) -> Optional[ PodcastScript ]:
        """
        Main execution - yields on I/O, doesn't block other jobs.

        Phase 1 Implementation:
        1. Load research document
        2. Analyze content for key topics
        3. Generate podcast script
        4. Wait for script review
        5. Save script to file

        Requires:
            - Research document exists and is readable
            - COSA interface is configured (for human feedback)

        Ensures:
            - Executes complete script generation workflow
            - Returns PodcastScript on success, None on cancellation
            - Updates state throughout execution

        Returns:
            PodcastScript or None: Generated script, or None if cancelled
        """
        self.metrics[ "start_time" ] = time.time()

        try:
            # =================================================================
            # Phase 1: Load Research Document
            # =================================================================
            self.state = OrchestratorState.LOADING_RESEARCH
            await cosa_interface.notify_progress(
                "Starting podcast generation - loading research document..."
            )

            research_content = await self._load_research_async()
            if not research_content:
                raise ValueError( f"Could not load research document: {self.research_doc_path}" )

            self._podcast_state[ "research_content" ] = research_content

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 2: Analyze Content
            # =================================================================
            self.state = OrchestratorState.ANALYZING_CONTENT
            await cosa_interface.notify_progress( "Analyzing content for key topics..." )

            analysis = await self._analyze_content_async( research_content )
            self._podcast_state[ "content_analysis" ] = analysis
            self._podcast_state[ "topics_extracted" ] = True

            if self.debug:
                print( f"[PodcastOrchestratorAgent] Analysis complete: {analysis.main_topic}" )
                print( f"[PodcastOrchestratorAgent] Key subtopics: {analysis.key_subtopics}" )

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 3: Generate Script
            # =================================================================
            self.state = OrchestratorState.GENERATING_SCRIPT
            await cosa_interface.notify_progress(
                f"Generating podcast script about {analysis.main_topic}..."
            )

            script = await self._generate_script_async( research_content, analysis )
            self._podcast_state[ "draft_script" ] = script

            if self.debug:
                print( f"[PodcastOrchestratorAgent] Script generated: {script.get_segment_count()} segments" )

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 4: Script Review
            # =================================================================
            self.state = OrchestratorState.WAITING_SCRIPT_REVIEW

            # Present script preview for approval
            script_preview = self._get_script_preview( script )
            choice = await cosa_interface.present_choices(
                questions = [ {
                    "question"    : "Podcast script is ready. How would you like to proceed?",
                    "header"      : "Script Review",
                    "multiSelect" : False,
                    "options"     : [
                        { "label": "Approve script", "description": "Save and continue" },
                        { "label": "Revise script", "description": "Provide feedback for changes" },
                        { "label": "Cancel", "description": "Discard and stop" }
                    ]
                } ],
                abstract = script_preview,
            )

            review_choice = choice.get( "answers", {} ).get( "Script Review", "" )

            if review_choice == "Cancel":
                self.state = OrchestratorState.STOPPED
                await cosa_interface.notify_progress( "Podcast generation cancelled." )
                return None

            if review_choice == "Revise script":
                # Get revision feedback
                feedback = await cosa_interface.get_feedback(
                    "What changes would you like to the script?",
                    timeout = self.config.feedback_timeout_seconds
                )

                if feedback:
                    self._podcast_state[ "human_feedback" ] = feedback
                    self._podcast_state[ "revision_count" ] += 1

                    # Revise script
                    self.state = OrchestratorState.GENERATING_SCRIPT
                    await cosa_interface.notify_progress( "Revising script based on your feedback..." )

                    script = await self._revise_script_async( script, feedback )
                    self._podcast_state[ "draft_script" ] = script

            self._podcast_state[ "script_approved" ] = True

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 5: Save Script
            # =================================================================
            script_path = await self._save_script_async( script )
            self._podcast_state[ "final_script_path" ] = script_path

            # =================================================================
            # Completion (Phase 1)
            # =================================================================
            self.state = OrchestratorState.COMPLETED
            self.metrics[ "end_time" ] = time.time()

            duration = self.metrics[ "end_time" ] - self.metrics[ "start_time" ]

            # Create metadata
            metadata = PodcastMetadata(
                podcast_id            = self.podcast_id,
                user_id               = self.user_id,
                research_doc_path     = self.research_doc_path,
                script_path           = script_path,
                generated_at          = datetime.now().isoformat(),
                generation_duration_seconds = duration,
                api_calls_count       = self.api_client.cost_estimate.total_api_calls,
                total_tokens_used     = (
                    self.api_client.cost_estimate.total_input_tokens +
                    self.api_client.cost_estimate.total_output_tokens
                ),
                estimated_cost_usd    = self.api_client.cost_estimate.estimated_cost_usd,
                script_revision_count = self._podcast_state[ "revision_count" ],
            )
            self._podcast_state[ "metadata" ] = metadata

            await cosa_interface.notify_progress(
                f"Podcast script complete! Saved to {script_path}",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: ~{script.estimated_duration_minutes:.1f} minutes\n"
                           f"**Cost**: ${metadata.estimated_cost_usd:.4f}"
            )

            return script

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = time.time()
            logger.error( f"Podcast generation failed: {e}" )
            await cosa_interface.notify_progress(
                f"Podcast generation failed: {str( e )[ :100 ]}",
                priority = "urgent"
            )
            raise

    def get_state( self ) -> dict:
        """
        Query current orchestrator state for external monitoring.

        Returns:
            dict: Current state summary
        """
        return {
            "state"          : self.state.value,
            "progress_pct"   : self._calculate_progress(),
            "podcast_id"     : self.podcast_id,
            "research_doc"   : self.research_doc_path,
            "revision_count" : self._podcast_state.get( "revision_count", 0 ),
            "script_approved": self._podcast_state.get( "script_approved", False ),
            "metrics"        : self.metrics,
        }

    async def pause( self ) -> bool:
        """Request graceful pause at next yield point."""
        self._pause_requested = True
        return True

    async def resume( self ) -> bool:
        """Resume from paused state."""
        if self.state == OrchestratorState.PAUSED:
            self._pause_requested = False
            return True
        return False

    async def stop( self ) -> dict:
        """Cancel and return partial results."""
        self._stop_requested = True
        self.state = OrchestratorState.STOPPED
        return {
            "partial_script" : self._podcast_state.get( "draft_script" ),
            "stopped_at"     : self.state.value,
            "analysis"       : self._podcast_state.get( "content_analysis" ),
        }

    # =========================================================================
    # Private Methods - Phase 1 Implementation
    # =========================================================================

    def _check_stop( self ) -> bool:
        """Check if stop was requested."""
        return self._stop_requested

    async def _handle_stop( self ) -> None:
        """Handle stop request gracefully."""
        await cosa_interface.notify_progress( "Podcast generation stopped by user request." )
        self.state = OrchestratorState.STOPPED
        return None

    def _calculate_progress( self ) -> int:
        """Calculate completion percentage based on current state."""
        state_progress = {
            OrchestratorState.LOADING_RESEARCH      : 10,
            OrchestratorState.ANALYZING_CONTENT     : 30,
            OrchestratorState.GENERATING_SCRIPT     : 60,
            OrchestratorState.WAITING_SCRIPT_REVIEW : 80,
            OrchestratorState.GENERATING_AUDIO      : 85,
            OrchestratorState.STITCHING_AUDIO       : 95,
            OrchestratorState.COMPLETED             : 100,
            OrchestratorState.FAILED                : 0,
            OrchestratorState.PAUSED                : 0,
            OrchestratorState.STOPPED               : 0,
        }
        return state_progress.get( self.state, 0 )

    async def _load_research_async( self ) -> Optional[ str ]:
        """
        Load and validate the research document.

        Returns:
            str or None: Document content, or None if loading fails
        """
        try:
            # Run file I/O in thread pool
            def read_file():
                import cosa.utils.util as cu

                # Handle relative paths
                if self.research_doc_path.startswith( "/" ):
                    path = self.research_doc_path
                else:
                    path = cu.get_project_root() + "/" + self.research_doc_path

                if not os.path.exists( path ):
                    logger.error( f"Research document not found: {path}" )
                    return None

                with open( path, "r", encoding="utf-8" ) as f:
                    content = f.read()

                return content

            content = await asyncio.to_thread( read_file )

            if content and self.debug:
                print( f"[PodcastOrchestratorAgent] Loaded research doc: {len( content )} chars" )

            return content

        except Exception as e:
            logger.error( f"Failed to load research document: {e}" )
            return None

    async def _analyze_content_async( self, research_content: str ) -> ContentAnalysis:
        """
        Analyze research content to extract key topics and discussion points.

        Args:
            research_content: The research document text

        Returns:
            ContentAnalysis: Structured analysis of the content
        """
        try:
            prompt = get_content_analysis_prompt(
                research_content = research_content,
                max_topics       = self.config.key_topics_to_extract,
            )

            response = await self.api_client.call_for_analysis(
                system_prompt = CONTENT_ANALYSIS_SYSTEM_PROMPT,
                user_message  = prompt,
            )
            self.metrics[ "api_calls" ] += 1

            result = parse_analysis_response( response.content )

            return ContentAnalysis(
                main_topic                 = result.get( "main_topic", "Unknown Topic" ),
                key_subtopics              = result.get( "key_subtopics", [] ),
                interesting_facts          = result.get( "interesting_facts", [] ),
                discussion_questions       = result.get( "discussion_questions", [] ),
                analogies_suggested        = result.get( "analogies_suggested", [] ),
                target_audience            = result.get( "target_audience", "general audience" ),
                complexity_level           = result.get( "complexity_level", "intermediate" ),
                estimated_coverage_minutes = result.get( "estimated_coverage_minutes", 10.0 ),
            )

        except Exception as e:
            logger.error( f"Content analysis failed: {e}" )
            if self.debug:
                print( f"[PodcastOrchestratorAgent] Analysis error: {e}" )

            # Return minimal analysis
            return ContentAnalysis(
                main_topic    = "Research Topic",
                key_subtopics = [],
            )

    async def _generate_script_async(
        self,
        research_content: str,
        analysis: ContentAnalysis
    ) -> PodcastScript:
        """
        Generate the podcast script using Claude.

        Args:
            research_content: The research document text
            analysis: Content analysis results

        Returns:
            PodcastScript: Generated script with dialogue segments
        """
        try:
            # Build system prompt with host personalities
            duo_description = get_dynamic_duo_description(
                host_a = self.config.host_a_personality,
                host_b = self.config.host_b_personality,
            )
            system_prompt = SCRIPT_GENERATION_SYSTEM_PROMPT + "\n\n" + duo_description

            # Build user prompt
            user_prompt = get_script_generation_prompt(
                content_analysis       = analysis.model_dump(),
                research_content       = research_content,
                host_a_personality     = self.config.host_a_personality,
                host_b_personality     = self.config.host_b_personality,
                target_duration_minutes = self.config.target_duration_minutes,
                min_exchanges          = self.config.min_exchanges,
                max_exchanges          = self.config.max_exchanges,
            )

            response = await self.api_client.call_for_script(
                system_prompt = system_prompt,
                user_message  = user_prompt,
            )
            self.metrics[ "api_calls" ] += 1

            result = parse_script_response( response.content )

            # Convert to PodcastScript
            segments = [
                ScriptSegment(
                    speaker         = seg.get( "speaker", "Host" ),
                    role            = seg.get( "role", "curious" ),
                    text            = seg.get( "text", "" ),
                    prosody         = seg.get( "prosody", [] ),
                    topic_reference = seg.get( "topic_reference" ),
                )
                for seg in result.get( "segments", [] )
            ]

            return PodcastScript(
                title                      = result.get( "title", f"Podcast: {analysis.main_topic}" ),
                research_source            = self.research_doc_path,
                host_a_name                = self.config.get_host_a_name(),
                host_b_name                = self.config.get_host_b_name(),
                segments                   = segments,
                estimated_duration_minutes = result.get( "estimated_duration_minutes", 10.0 ),
                key_topics                 = result.get( "key_topics", analysis.key_subtopics ),
            )

        except Exception as e:
            logger.error( f"Script generation failed: {e}" )
            if self.debug:
                print( f"[PodcastOrchestratorAgent] Script generation error: {e}" )

            # Return minimal script
            return PodcastScript(
                title           = f"Podcast: {analysis.main_topic}",
                research_source = self.research_doc_path,
                host_a_name     = self.config.get_host_a_name(),
                host_b_name     = self.config.get_host_b_name(),
                segments        = [],
            )

    async def _revise_script_async(
        self,
        current_script: PodcastScript,
        feedback: str
    ) -> PodcastScript:
        """
        Revise the script based on user feedback.

        Args:
            current_script: Current script to revise
            feedback: User feedback on changes needed

        Returns:
            PodcastScript: Revised script
        """
        try:
            revision_prompt = get_script_revision_prompt(
                current_script  = current_script.to_markdown(),
                feedback        = feedback,
                revision_number = self._podcast_state[ "revision_count" ],
            )

            response = await self.api_client.call_for_revision(
                system_prompt = SCRIPT_GENERATION_SYSTEM_PROMPT,
                user_message  = revision_prompt,
            )
            self.metrics[ "api_calls" ] += 1

            result = parse_script_response( response.content )

            # Convert to PodcastScript
            segments = [
                ScriptSegment(
                    speaker         = seg.get( "speaker", "Host" ),
                    role            = seg.get( "role", "curious" ),
                    text            = seg.get( "text", "" ),
                    prosody         = seg.get( "prosody", [] ),
                    topic_reference = seg.get( "topic_reference" ),
                )
                for seg in result.get( "segments", [] )
            ]

            revised = PodcastScript(
                title                      = result.get( "title", current_script.title ),
                research_source            = current_script.research_source,
                host_a_name                = current_script.host_a_name,
                host_b_name                = current_script.host_b_name,
                segments                   = segments if segments else current_script.segments,
                estimated_duration_minutes = result.get( "estimated_duration_minutes",
                                                          current_script.estimated_duration_minutes ),
                key_topics                 = result.get( "key_topics", current_script.key_topics ),
                revision_count             = current_script.revision_count + 1,
            )

            return revised

        except Exception as e:
            logger.error( f"Script revision failed: {e}" )
            # Return original script unchanged
            return current_script

    async def _save_script_async( self, script: PodcastScript ) -> str:
        """
        Save the script to a markdown file.

        Args:
            script: The script to save

        Returns:
            str: Path to saved file
        """
        try:
            import cosa.utils.util as cu

            # Generate output path
            topic_slug = script.title.replace( "Podcast: ", "" )[ :40 ]
            output_path = self.config.get_output_path(
                user_id   = self.user_id,
                topic     = topic_slug,
                file_type = "script",
            )

            # Ensure directory exists
            output_dir = os.path.dirname( output_path )

            def write_file():
                os.makedirs( output_dir, exist_ok=True )
                with open( output_path, "w", encoding="utf-8" ) as f:
                    f.write( script.to_markdown() )
                return output_path

            path = await asyncio.to_thread( write_file )

            if self.debug:
                print( f"[PodcastOrchestratorAgent] Script saved to: {path}" )

            return path

        except Exception as e:
            logger.error( f"Failed to save script: {e}" )
            raise

    def _get_script_preview( self, script: PodcastScript ) -> str:
        """
        Generate a preview summary of the script for review.

        Args:
            script: The script to preview

        Returns:
            str: Markdown preview summary
        """
        word_counts = script.get_speaker_word_counts()
        word_summary = "\n".join( [
            f"- **{speaker}**: {count} words"
            for speaker, count in word_counts.items()
        ] )

        # Get first few segments as sample
        sample_segments = script.segments[ :3 ] if len( script.segments ) >= 3 else script.segments
        sample_text = "\n\n".join( [ seg.to_markdown() for seg in sample_segments ] )

        return f"""## Script Preview: {script.title}

**Segments**: {script.get_segment_count()}
**Estimated Duration**: {script.estimated_duration_minutes:.1f} minutes
**Key Topics**: {', '.join( script.key_topics[ :5 ] )}

### Word Distribution
{word_summary}

### Sample Dialogue
{sample_text}

---
*Full script contains {script.get_segment_count()} dialogue segments.*"""


def quick_smoke_test():
    """Quick smoke test for PodcastOrchestratorAgent."""
    import cosa.utils.util as cu

    cu.print_banner( "Podcast Orchestrator Smoke Test", prepend_nl=True )

    try:
        # Test 1: Instantiation
        print( "Testing instantiation..." )
        agent = PodcastOrchestratorAgent(
            research_doc_path = "/tmp/test-research.md",
            user_id           = "test-user@example.com",
            debug             = True,
        )
        assert agent.state == OrchestratorState.LOADING_RESEARCH
        assert "test-research.md" in agent.research_doc_path
        print( f"✓ Agent instantiated (ID: {agent.podcast_id})" )

        # Test 2: get_state
        print( "Testing get_state..." )
        state = agent.get_state()
        assert "state" in state
        assert "progress_pct" in state
        assert "podcast_id" in state
        assert state[ "state" ] == "loading_research"
        print( f"✓ get_state works (state={state[ 'state' ]}, progress={state[ 'progress_pct' ]}%)" )

        # Test 3: _calculate_progress
        print( "Testing _calculate_progress..." )
        assert agent._calculate_progress() == 10  # LOADING_RESEARCH = 10%
        agent.state = OrchestratorState.GENERATING_SCRIPT
        assert agent._calculate_progress() == 60  # GENERATING_SCRIPT = 60%
        agent.state = OrchestratorState.COMPLETED
        assert agent._calculate_progress() == 100  # COMPLETED = 100%
        print( "✓ _calculate_progress returns correct values" )

        # Test 4: pause/stop methods
        print( "Testing control methods..." )

        async def test_control():
            agent2 = PodcastOrchestratorAgent(
                research_doc_path = "/tmp/test.md",
                user_id           = "test-user",
            )

            # Test pause
            paused = await agent2.pause()
            assert paused is True
            assert agent2._pause_requested is True

            # Test stop
            result = await agent2.stop()
            assert agent2.state == OrchestratorState.STOPPED
            assert "partial_script" in result

            return True

        import asyncio
        result = asyncio.run( test_control() )
        assert result is True
        print( "✓ Control methods (pause/stop) work correctly" )

        # Test 5: _get_script_preview
        print( "Testing _get_script_preview..." )
        agent.state = OrchestratorState.LOADING_RESEARCH  # Reset state

        test_script = PodcastScript(
            title           = "Test Podcast",
            research_source = "/test.md",
            host_a_name     = "Alex",
            host_b_name     = "Jordan",
            segments        = [
                ScriptSegment( speaker="Alex", role="curious", text="Hello!" ),
                ScriptSegment( speaker="Jordan", role="expert", text="Hi there!" ),
            ],
            estimated_duration_minutes = 5.0,
            key_topics      = [ "topic1", "topic2" ],
        )

        preview = agent._get_script_preview( test_script )
        assert "Test Podcast" in preview
        assert "2" in preview  # 2 segments
        assert "Alex" in preview
        print( "✓ _get_script_preview generates proper markdown" )

        print( "\n✓ Podcast Orchestrator smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
