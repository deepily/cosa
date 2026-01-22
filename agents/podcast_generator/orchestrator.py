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
import urllib.parse
import uuid
from typing import Optional, List, Tuple
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
from . import voice_io
from .api_client import PodcastAPIClient
from .tts_client import PodcastTTSClient, TTSSegmentResult
from .audio_stitcher import PodcastAudioStitcher, StitchingResult
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

# ElevenLabs pricing (standard tier)
ELEVENLABS_COST_PER_1K_CHARS = 0.30  # $0.30 per 1000 characters


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
        max_segments: Optional[ int ] = None,
        debug: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the podcast orchestrator.

        Args:
            research_doc_path: Path to the Deep Research markdown document
            user_id: System user ID for event routing
            config: Podcast configuration (uses defaults if None)
            max_segments: Limit TTS to first N segments (for cost control)
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.research_doc_path = research_doc_path
        self.user_id           = user_id
        self.config            = config or PodcastConfig()
        self.max_segments      = max_segments
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

        # Initialize TTS client and audio stitcher (lazy - created on first use)
        self._tts_client: Optional[ PodcastTTSClient ] = None
        self._audio_stitcher: Optional[ PodcastAudioStitcher ] = None

        # Track original script path for revisions (to preserve filename)
        self._original_script_path: Optional[ str ] = None

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

    @property
    def tts_client( self ) -> PodcastTTSClient:
        """Lazy initialization of TTS client."""
        if self._tts_client is None:
            self._tts_client = PodcastTTSClient(
                config_mgr        = None,  # Will use defaults from config
                progress_callback = self._audio_progress_callback,
                retry_callback    = self._audio_retry_callback,
                debug             = self.debug,
                verbose           = self.verbose,
            )
        return self._tts_client

    @property
    def audio_stitcher( self ) -> PodcastAudioStitcher:
        """Lazy initialization of audio stitcher."""
        if self._audio_stitcher is None:
            self._audio_stitcher = PodcastAudioStitcher(
                silence_between_speakers_ms = self.config.silence_between_speakers_ms,
                audio_bitrate               = self.config.audio_bitrate,
                debug                       = self.debug,
                verbose                     = self.verbose,
            )
        return self._audio_stitcher

    @classmethod
    async def from_saved_script(
        cls,
        script_path: str,
        user_id: str,
        config: Optional[ PodcastConfig ] = None,
        max_segments: Optional[ int ] = None,
        debug: bool = False,
        verbose: bool = False
    ) -> "PodcastOrchestratorAgent":
        """
        Create orchestrator from a saved script, skipping generation phases.

        Loads an existing script markdown file and creates an orchestrator
        ready to enter the review/revision workflow directly.

        Requires:
            - script_path points to a valid podcast script markdown file
            - user_id is a valid identifier

        Ensures:
            - Returns orchestrator with script pre-loaded
            - State is set to WAITING_SCRIPT_REVIEW
            - Revision count is preserved from loaded script

        Args:
            script_path: Path to saved script markdown file
            user_id: User identifier for output directory
            config: Podcast configuration (uses defaults if None)
            max_segments: Limit TTS to first N segments (for cost control)
            debug: Enable debug output
            verbose: Enable verbose output

        Returns:
            PodcastOrchestratorAgent: Ready for review workflow
        """
        import cosa.utils.util as cu

        # Resolve path
        if not script_path.startswith( "/" ):
            script_path = cu.get_project_root() + "/" + script_path

        # Load and parse script
        with open( script_path, "r", encoding="utf-8" ) as f:
            markdown_content = f.read()

        script = PodcastScript.from_markdown( markdown_content )

        # Create orchestrator with dummy research path (not used in edit mode)
        agent = cls(
            research_doc_path = script.research_source or "edit-mode",
            user_id           = user_id,
            config            = config,
            max_segments      = max_segments,
            debug             = debug,
            verbose           = verbose,
        )

        # Pre-populate state
        agent._podcast_state[ "draft_script" ]      = script
        agent._podcast_state[ "draft_script_path" ] = script_path
        agent._podcast_state[ "revision_count" ]    = script.revision_count
        agent.state = OrchestratorState.WAITING_SCRIPT_REVIEW

        # Preserve original path for revisions (prevents filename changes)
        agent._original_script_path = script_path

        if debug:
            print( f"[PodcastOrchestratorAgent] Loaded script from: {script_path}" )
            print( f"[PodcastOrchestratorAgent] Title: {script.title}" )
            print( f"[PodcastOrchestratorAgent] Segments: {script.get_segment_count()}" )

        return agent

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
            await voice_io.notify(
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
            await voice_io.notify( "Analyzing content for key topics..." )

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
            await voice_io.notify(
                f"Generating podcast script about {analysis.main_topic}..."
            )

            script = await self._generate_script_async( research_content, analysis )
            self._podcast_state[ "draft_script" ] = script

            if self.debug:
                print( f"[PodcastOrchestratorAgent] Script generated: {script.get_segment_count()} segments" )

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 4: Script Review - ITERATIVE LOOP
            # =================================================================
            script_approved = False
            script_path     = None  # Track current script location

            while not script_approved:
                self.state = OrchestratorState.WAITING_SCRIPT_REVIEW

                # Generate display path for preview (don't save yet - only save after user decision)
                if script_path:
                    display_path = script_path
                elif self._original_script_path:
                    display_path = self._original_script_path
                else:
                    # Preview of where it WOULD be saved (first generation)
                    topic_slug   = script.title.replace( "Podcast: ", "" )[ :40 ]
                    display_path = self.config.get_output_path(
                        user_id   = self.user_id,
                        topic     = topic_slug,
                        file_type = "script",
                    )

                # Present script preview for approval, including file path
                script_preview = self._get_script_preview( script )
                script_preview += f"\n\n**Will save to**: `{display_path}`"

                revision_label = f" (Revision {self._podcast_state[ 'revision_count' ]})" if self._podcast_state[ "revision_count" ] > 0 else ""

                choice = await voice_io.present_choices(
                    questions = [ {
                        "question"    : "Podcast script is ready. How would you like to proceed?",
                        "header"      : "Script Review",
                        "multiSelect" : False,
                        "options"     : [
                            { "label": "Approve script", "description": "Keep script and continue" },
                            { "label": "Revise script", "description": "Provide feedback for changes" },
                            { "label": "Cancel", "description": "Discard script and stop" }
                        ]
                    } ],
                    abstract = script_preview,
                    title    = f"Script Review{revision_label}",
                )

                review_choice = choice.get( "answers", {} ).get( "Script Review", "" )

                if review_choice == "Cancel":
                    self.state = OrchestratorState.STOPPED
                    await voice_io.notify( "Podcast generation cancelled." )
                    return None

                elif review_choice == "Approve script":
                    # Explicit approval - save and exit loop
                    script.revision_count = self._podcast_state[ "revision_count" ]
                    script_path = await self._save_script_async( script )
                    self._podcast_state[ "draft_script_path" ] = script_path
                    script_approved = True

                else:
                    # "Revise script" or "Other" with custom text
                    if review_choice == "Revise script":
                        feedback = await voice_io.get_input(
                            "What changes would you like to the script?",
                            timeout = self.config.feedback_timeout_seconds
                        )
                    else:
                        # "Other" - custom text IS the feedback
                        feedback = review_choice

                    if feedback:
                        self._podcast_state[ "human_feedback" ] = feedback
                        self._podcast_state[ "revision_count" ] += 1

                        # Revise script
                        self.state = OrchestratorState.GENERATING_SCRIPT
                        await voice_io.notify( f"Revising script (revision {self._podcast_state[ 'revision_count' ]})..." )

                        script = await self._revise_script_async( script, feedback )
                        self._podcast_state[ "draft_script" ] = script

                        # Save revision with version suffix (e.g., -v2.md)
                        script.revision_count = self._podcast_state[ "revision_count" ]
                        script_path = await self._save_script_async( script, is_revision=True )
                        self._podcast_state[ "draft_script_path" ] = script_path

                        # Loop continues - will show revised script for review again

                if self._check_stop(): return await self._handle_stop()

            self._podcast_state[ "script_approved" ] = True
            self._podcast_state[ "final_script_path" ] = script_path

            # =================================================================
            # Phase 5: Generate Audio
            # =================================================================
            self.state = OrchestratorState.GENERATING_AUDIO

            # Initialize progress milestone tracking (for 10% increment notifications)
            self._reported_milestones = set()

            segment_count = script.get_segment_count()
            await voice_io.notify(
                f"Starting audio generation for {segment_count} segments. This may take 1-3 minutes.",
                priority = "medium"
            )

            tts_results, failed_indices = await self._generate_audio_async( script )

            # Handle partial failures
            if failed_indices:
                continue_anyway = await voice_io.ask_yes_no(
                    f"{len( failed_indices )} segments failed. Continue with partial audio?",
                    default  = "yes",
                    abstract = f"**Failed**: {len( failed_indices )}\n**Successful**: {len( tts_results ) - len( failed_indices )}"
                )
                if not continue_anyway:
                    self.state = OrchestratorState.STOPPED
                    await voice_io.notify( "Audio generation cancelled by user." )
                    return script

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 6: Stitch Audio
            # =================================================================
            self.state = OrchestratorState.STITCHING_AUDIO
            await voice_io.notify( "Stitching audio segments into final podcast..." )

            audio_path = await self._stitch_audio_async( tts_results, script )
            self._podcast_state[ "final_audio_path" ] = audio_path

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Completion
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
                audio_path            = audio_path,
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

            # Calculate audio duration
            audio_duration_mins = script.estimated_duration_minutes
            if audio_path and os.path.exists( audio_path ):
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_mp3( audio_path )
                    audio_duration_mins = len( audio ) / 1000.0 / 60.0
                except Exception:
                    pass  # Use script estimate if audio read fails

            # Build clickable links for notification abstract
            import cosa.utils.util as cu
            io_base = cu.get_project_root() + "/io/"

            # Convert absolute paths to relative for API endpoint
            script_link   = script_path
            audio_link    = audio_path
            research_link = self.research_doc_path

            if script_path and script_path.startswith( io_base ):
                rel_path    = script_path.replace( io_base, "" )
                script_link = f"[View Script](/api/io/file?path={urllib.parse.quote( rel_path )})"
            if audio_path and audio_path.startswith( io_base ):
                rel_path   = audio_path.replace( io_base, "" )
                audio_link = f"[Download MP3](/api/io/file?path={urllib.parse.quote( rel_path )})"
            if self.research_doc_path and self.research_doc_path.startswith( io_base ):
                rel_path      = self.research_doc_path.replace( io_base, "" )
                research_link = f"[View Research](/api/io/file?path={urllib.parse.quote( rel_path )})"

            # Calculate audio cost from TTS character usage
            tts_results = self._podcast_state.get( "tts_results", [] )
            total_chars = sum( r.character_count for r in tts_results if r.success )
            audio_cost  = ( total_chars / 1000.0 ) * ELEVENLABS_COST_PER_1K_CHARS
            total_cost  = metadata.estimated_cost_usd + audio_cost

            await voice_io.notify(
                f"Podcast complete! Duration: {audio_duration_mins:.1f} minutes",
                priority = "high",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: {audio_duration_mins:.1f} minutes\n"
                           f"**Script Cost**: ${metadata.estimated_cost_usd:.4f}\n"
                           f"**Audio Cost**: ${audio_cost:.4f} ({total_chars:,} chars)\n"
                           f"**Total Cost**: ${total_cost:.4f}\n"
                           f"**Audio**: {audio_link}\n"
                           f"**Script**: {script_link}\n"
                           f"**Research**: {research_link}"
            )

            return script

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = time.time()
            logger.error( f"Podcast generation failed: {e}" )
            await voice_io.notify(
                f"Podcast generation failed: {str( e )[ :100 ]}",
                priority = "urgent"
            )
            raise

    async def do_review_only_async( self ) -> Optional[ PodcastScript ]:
        """
        Run only the review/revision workflow (skip generation phases).

        Used when resuming from a saved script via --edit-script flag.
        Enters directly at Phase 4 (WAITING_SCRIPT_REVIEW).

        Requires:
            - Script already loaded via from_saved_script()
            - State is WAITING_SCRIPT_REVIEW

        Ensures:
            - Executes review/revision workflow
            - Returns updated PodcastScript on success
            - Returns None on cancellation

        Returns:
            PodcastScript or None: Updated script, or None if cancelled
        """
        self.metrics[ "start_time" ] = time.time()

        try:
            script = self._podcast_state.get( "draft_script" )
            if not script:
                raise ValueError( "No script loaded - use from_saved_script() first" )

            draft_script_path = self._podcast_state.get( "draft_script_path", "" )

            await voice_io.notify(
                f"Loaded script: {script.title}",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: ~{script.estimated_duration_minutes:.1f} minutes\n"
                           f"**Revisions**: {script.revision_count}"
            )

            # =================================================================
            # Phase 4: Script Review - ITERATIVE LOOP (edit mode entry point)
            # =================================================================
            script_approved = False
            script_path     = self._original_script_path  # Track current script location

            while not script_approved:
                self.state = OrchestratorState.WAITING_SCRIPT_REVIEW

                # Generate display path (don't save yet - only save after user decision)
                display_path = script_path or self._original_script_path

                # Present script preview for approval
                script_preview = self._get_script_preview( script )
                script_preview += f"\n\n**Full script**: `{display_path}`"

                revision_label = f" (Revision {self._podcast_state[ 'revision_count' ]})" if self._podcast_state[ "revision_count" ] > 0 else ""

                choice = await voice_io.present_choices(
                    questions = [ {
                        "question"    : "How would you like to proceed with this script?",
                        "header"      : "Script Review",
                        "multiSelect" : False,
                        "options"     : [
                            { "label": "Approve script", "description": "Keep script and finish" },
                            { "label": "Revise script", "description": "Provide feedback for changes" },
                            { "label": "Cancel", "description": "Discard changes and stop" }
                        ]
                    } ],
                    abstract = script_preview,
                    title    = f"Script Review{revision_label}",
                )

                review_choice = choice.get( "answers", {} ).get( "Script Review", "" )

                if review_choice == "Cancel":
                    self.state = OrchestratorState.STOPPED
                    await voice_io.notify( "Script editing cancelled." )
                    return None

                elif review_choice == "Approve script":
                    # Explicit approval - save and exit loop
                    script.revision_count = self._podcast_state[ "revision_count" ]
                    script_path = await self._save_script_async( script )
                    self._podcast_state[ "draft_script_path" ] = script_path
                    script_approved = True

                else:
                    # "Revise script" or "Other" with custom text
                    if review_choice == "Revise script":
                        feedback = await voice_io.get_input(
                            "What changes would you like to the script?",
                            timeout = self.config.feedback_timeout_seconds
                        )
                    else:
                        # "Other" - custom text IS the feedback
                        feedback = review_choice

                    if feedback:
                        self._podcast_state[ "human_feedback" ] = feedback
                        self._podcast_state[ "revision_count" ] += 1

                        # Revise script
                        self.state = OrchestratorState.GENERATING_SCRIPT
                        await voice_io.notify( f"Revising script (revision {self._podcast_state[ 'revision_count' ]})..." )

                        script = await self._revise_script_async( script, feedback )
                        self._podcast_state[ "draft_script" ] = script

                        # Save revision with version suffix (e.g., -v2.md)
                        script.revision_count = self._podcast_state[ "revision_count" ]
                        script_path = await self._save_script_async( script, is_revision=True )
                        self._podcast_state[ "draft_script_path" ] = script_path

                        # Loop continues - will show revised script for review again

            self._podcast_state[ "script_approved" ] = True
            self._podcast_state[ "final_script_path" ] = script_path

            # =================================================================
            # Completion
            # =================================================================
            self.state = OrchestratorState.COMPLETED
            self.metrics[ "end_time" ] = time.time()

            # Build clickable link for script
            import cosa.utils.util as cu
            io_base = cu.get_project_root() + "/io/"

            script_link = script_path
            if script_path and script_path.startswith( io_base ):
                rel_path    = script_path.replace( io_base, "" )
                script_link = f"[View Script](/api/io/file?path={urllib.parse.quote( rel_path )})"

            await voice_io.notify(
                f"Script editing complete!",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: ~{script.estimated_duration_minutes:.1f} minutes\n"
                           f"**Revisions**: {script.revision_count}\n"
                           f"**Script**: {script_link}"
            )

            return script

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = time.time()
            logger.error( f"Script editing failed: {e}" )
            await voice_io.notify(
                f"Script editing failed: {str( e )[ :100 ]}",
                priority = "urgent"
            )
            raise

    async def do_audio_only_async( self ) -> Optional[ PodcastScript ]:
        """
        Run only the audio generation workflow (skip script review).

        Used when resuming from a saved script via --generate-audio flag.
        Enters directly at Phase 5 (GENERATING_AUDIO).

        Requires:
            - Script already loaded via from_saved_script()

        Ensures:
            - Executes audio generation and stitching only
            - Returns PodcastScript on success
            - Returns None on cancellation

        Returns:
            PodcastScript or None: Script with audio path, or None if cancelled
        """
        self.metrics[ "start_time" ] = time.time()

        try:
            script = self._podcast_state.get( "draft_script" )
            if not script:
                raise ValueError( "No script loaded - use from_saved_script() first" )

            script_path = self._podcast_state.get( "draft_script_path", "" )

            await voice_io.notify(
                f"Loaded script: {script.title}",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: ~{script.calculated_duration_minutes:.1f} minutes"
            )

            # =================================================================
            # Phase 5: Generate Audio
            # =================================================================
            self.state = OrchestratorState.GENERATING_AUDIO

            # Initialize progress milestone tracking (for 10% increment notifications)
            self._reported_milestones = set()

            segment_count = script.get_segment_count()
            await voice_io.notify(
                f"Starting audio generation for {segment_count} segments. This may take 1-3 minutes.",
                priority = "medium"
            )

            tts_results, failed_indices = await self._generate_audio_async( script )

            # Handle partial failures - HIGH priority for TTS announcement
            if failed_indices:
                continue_anyway = await voice_io.ask_yes_no(
                    f"{len( failed_indices )} segments failed. Continue with partial audio?",
                    default  = "yes",
                    timeout  = 120,
                    abstract = f"**Failed**: {len( failed_indices )}\n**Successful**: {len( tts_results ) - len( failed_indices )}"
                )
                if not continue_anyway:
                    self.state = OrchestratorState.STOPPED
                    await voice_io.notify( "Audio generation cancelled by user." )
                    return None

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 6: Stitch Audio
            # =================================================================
            self.state = OrchestratorState.STITCHING_AUDIO
            await voice_io.notify( "Stitching audio segments into final podcast..." )

            audio_path = await self._stitch_audio_async( tts_results, script )
            self._podcast_state[ "final_audio_path" ] = audio_path

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Completion
            # =================================================================
            self.state = OrchestratorState.COMPLETED
            self.metrics[ "end_time" ] = time.time()

            duration = self.metrics[ "end_time" ] - self.metrics[ "start_time" ]

            # Calculate audio duration
            audio_duration_mins = script.calculated_duration_minutes
            if audio_path and os.path.exists( audio_path ):
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_mp3( audio_path )
                    audio_duration_mins = len( audio ) / 1000.0 / 60.0
                except Exception:
                    pass  # Use script estimate if audio read fails

            # Build clickable links for notification abstract
            import cosa.utils.util as cu
            io_base = cu.get_project_root() + "/io/"

            # Convert absolute paths to relative for API endpoint
            script_link   = script_path
            audio_link    = audio_path
            research_link = self.research_doc_path

            if script_path and script_path.startswith( io_base ):
                rel_path    = script_path.replace( io_base, "" )
                script_link = f"[View Script](/api/io/file?path={urllib.parse.quote( rel_path )})"
            if audio_path and audio_path.startswith( io_base ):
                rel_path   = audio_path.replace( io_base, "" )
                audio_link = f"[Download MP3](/api/io/file?path={urllib.parse.quote( rel_path )})"
            if self.research_doc_path and self.research_doc_path.startswith( io_base ):
                rel_path      = self.research_doc_path.replace( io_base, "" )
                research_link = f"[View Research](/api/io/file?path={urllib.parse.quote( rel_path )})"

            # Calculate audio cost from TTS character usage
            tts_results = self._podcast_state.get( "tts_results", [] )
            total_chars = sum( r.character_count for r in tts_results if r.success )
            audio_cost  = ( total_chars / 1000.0 ) * ELEVENLABS_COST_PER_1K_CHARS

            await voice_io.notify(
                f"Podcast audio complete! Duration: {audio_duration_mins:.1f} minutes",
                priority = "high",
                abstract = f"**Segments**: {script.get_segment_count()}\n"
                           f"**Duration**: {audio_duration_mins:.1f} minutes\n"
                           f"**Audio Cost**: ${audio_cost:.4f} ({total_chars:,} chars)\n"
                           f"**Audio**: {audio_link}\n"
                           f"**Script**: {script_link}\n"
                           f"**Research**: {research_link}"
            )

            return script

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = time.time()
            logger.error( f"Audio generation failed: {e}" )
            await voice_io.notify(
                f"Audio generation failed: {str( e )[ :100 ]}",
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
        await voice_io.notify( "Podcast generation stopped by user request." )
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

    async def _save_script_async( self, script: PodcastScript, is_revision: bool = False ) -> str:
        """
        Save the script to a markdown file.

        For new scripts, generates a new path and stores it.
        For revisions, appends version suffix (e.g., -v2.md) to preserve history.
        For approval (final save), uses original path.

        Args:
            script: The script to save
            is_revision: If True, append version suffix (e.g., -v2.md) to filename

        Returns:
            str: Path to saved file
        """
        try:
            import cosa.utils.util as cu

            # Determine output path based on context
            if self._original_script_path and is_revision:
                # Generate versioned path: original-script-v2.md (suffix before .md)
                base_path    = self._original_script_path
                revision_num = self._podcast_state.get( "revision_count", 1 )

                # Split: /path/to/name-script.md → /path/to/name-script + .md
                # Result: /path/to/name-script-v2.md
                stem, ext   = os.path.splitext( base_path )  # ext = ".md"
                output_path = f"{stem}-v{revision_num}{ext}"

            elif self._original_script_path:
                # Non-revision save (approval) - use original path
                output_path = self._original_script_path

            else:
                # First save - generate new path
                topic_slug = script.title.replace( "Podcast: ", "" )[ :40 ]
                output_path = self.config.get_output_path(
                    user_id   = self.user_id,
                    topic     = topic_slug,
                    file_type = "script",
                )
                # Store for future reference
                self._original_script_path = output_path

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

    async def _delete_draft_script( self, script_path: str ) -> None:
        """
        Delete a draft script file (used when user cancels).

        Args:
            script_path: Path to the script file to delete
        """
        try:
            def delete_file():
                if os.path.exists( script_path ):
                    os.remove( script_path )
                    return True
                return False

            deleted = await asyncio.to_thread( delete_file )

            if self.debug and deleted:
                print( f"[PodcastOrchestratorAgent] Draft script deleted: {script_path}" )

        except Exception as e:
            logger.warning( f"Failed to delete draft script: {e}" )
            # Non-fatal - continue anyway

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

    # =========================================================================
    # Private Methods - Phase 2 Implementation (Audio Generation)
    # =========================================================================

    async def _generate_audio_async(
        self,
        script: PodcastScript
    ) -> Tuple[ List[ TTSSegmentResult ], List[ int ] ]:
        """
        Phase 5: Generate TTS audio for all segments.

        Uses the TTS client to generate PCM audio for each dialogue
        segment in the script.

        Requires:
            - script has at least one segment
            - ELEVENLABS_API_KEY is set in environment

        Ensures:
            - Returns list of TTSSegmentResult for all segments
            - Returns list of indices for failed segments

        Args:
            script: Podcast script with dialogue segments

        Returns:
            Tuple[List[TTSSegmentResult], List[int]]:
                - All TTS results (including failures)
                - Indices of failed segments
        """
        # Apply max_segments limit if set (for cost control during testing)
        original_count = script.get_segment_count()
        if self.max_segments is not None and self.max_segments < original_count:
            if self.debug:
                print( f"[PodcastOrchestratorAgent] Limiting segments: {self.max_segments} of {original_count}" )
            # Create a shallow copy of script with limited segments
            from copy import copy
            limited_script = copy( script )
            limited_script.segments = script.segments[ :self.max_segments ]
            script = limited_script

        if self.debug:
            print( f"[PodcastOrchestratorAgent] Starting audio generation for {script.get_segment_count()} segments" )

        # Use the lazy-initialized TTS client
        tts_results, failed_indices = await self.tts_client.generate_all_segments( script )

        # Store TTS results in state for cost calculation in notifications
        self._podcast_state[ "tts_results" ] = tts_results

        if self.debug:
            success_count = len( tts_results ) - len( failed_indices )
            print( f"[PodcastOrchestratorAgent] Audio generation complete: {success_count}/{len( tts_results )} successful" )

        return tts_results, failed_indices

    async def _stitch_audio_async(
        self,
        tts_results: List[ TTSSegmentResult ],
        script: PodcastScript
    ) -> str:
        """
        Phase 6: Stitch audio segments into final MP3.

        Uses the audio stitcher to concatenate all successful TTS
        results into a single podcast MP3 file.

        Requires:
            - tts_results contains at least one successful result
            - Output directory is writable

        Ensures:
            - Creates MP3 file at the output path
            - Returns path to the created file

        Args:
            tts_results: List of TTS results from generation phase
            script: Original script (for output path generation)

        Returns:
            str: Path to the created MP3 file
        """
        # Generate output path
        topic_slug  = script.title.replace( "Podcast: ", "" )[ :40 ]
        output_path = self.config.get_output_path(
            user_id   = self.user_id,
            topic     = topic_slug,
            file_type = "audio",
        )

        if self.debug:
            print( f"[PodcastOrchestratorAgent] Stitching audio to: {output_path}" )

        # Run stitching in thread pool (pydub is synchronous)
        def do_stitch():
            return self.audio_stitcher.stitch_segments( tts_results, output_path )

        result = await asyncio.to_thread( do_stitch )

        if not result.success:
            raise RuntimeError( f"Audio stitching failed: {result.error_message}" )

        if self.debug:
            print( f"[PodcastOrchestratorAgent] Audio stitched: {result.total_duration_seconds:.1f}s, {result.file_size_bytes / 1024:.1f}KB" )

        return result.output_path

    async def _audio_progress_callback(
        self,
        current     : int,
        total       : int,
        speaker     : str,
        eta_seconds : float = 0.0
    ) -> None:
        """
        Progress callback for audio generation milestones.

        Called by TTS client after each segment. Sends notifications
        at every 10% progress milestone (10%, 20%, ... 100%).

        Args:
            current: Current segment number (1-based)
            total: Total number of segments
            speaker: Speaker name for current segment
            eta_seconds: Estimated time remaining in seconds
        """
        # Calculate percentage and round down to nearest 10%
        pct = int( current / total * 100 )
        milestone = ( pct // 10 ) * 10  # 15% → 10%, 27% → 20%, etc.

        # Notify only when reaching a new 10% milestone
        if milestone not in self._reported_milestones and milestone > 0:
            self._reported_milestones.add( milestone )

            if eta_seconds > 0:
                eta_str = f", ~{int( eta_seconds )}s remaining"
            else:
                eta_str = ""

            await voice_io.notify(
                f"Audio progress: {pct}% ({current}/{total} segments){eta_str}",
                priority = "low"
            )

    async def _audio_retry_callback(
        self,
        segment_index : int,
        attempt       : int,
        max_attempts  : int,
        speaker       : str
    ) -> None:
        """
        Retry callback for TTS segment failures.

        Called by TTS client when a segment fails and will be retried.
        Sends low priority notification to inform user of retry attempt.

        Args:
            segment_index: Zero-based index of the segment
            attempt: Current attempt number (1-based, e.g., 2 = second attempt)
            max_attempts: Maximum number of attempts
            speaker: Speaker name for the segment
        """
        await voice_io.notify(
            f"Segment {segment_index + 1} ({speaker}) failed, retrying ({attempt}/{max_attempts})...",
            priority = "low"
        )


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
            host_a_name     = "Nora",
            host_b_name     = "Quentin",
            segments        = [
                ScriptSegment( speaker="Nora", role="curious", text="Hello!" ),
                ScriptSegment( speaker="Quentin", role="expert", text="Hi there!" ),
            ],
            estimated_duration_minutes = 5.0,
            key_topics      = [ "topic1", "topic2" ],
        )

        preview = agent._get_script_preview( test_script )
        assert "Test Podcast" in preview
        assert "2" in preview  # 2 segments
        assert "Nora" in preview
        print( "✓ _get_script_preview generates proper markdown" )

        print( "\n✓ Podcast Orchestrator smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
