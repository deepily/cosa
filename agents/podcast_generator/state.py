#!/usr/bin/env python3
"""
State Schemas for COSA Podcast Generator Agent.

Uses Pydantic for structured outputs and TypedDict for graph state.
Designed for the podcast generation workflow with script review checkpoints.
"""

from enum import Enum
from typing import TypedDict, Literal, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class OrchestratorState( Enum ):
    """
    State machine for the Podcast Orchestrator Agent.

    Active states represent work being done.
    Waiting states are yield points where control returns to event loop.
    Terminal states indicate completion or failure.
    External control states allow user intervention.
    """
    # Active states
    LOADING_RESEARCH   = "loading_research"
    ANALYZING_CONTENT  = "analyzing_content"
    GENERATING_SCRIPT  = "generating_script"
    GENERATING_AUDIO   = "generating_audio"
    STITCHING_AUDIO    = "stitching_audio"

    # Waiting states (yield control via await)
    WAITING_SCRIPT_REVIEW = "waiting_script_review"

    # Terminal states
    COMPLETED = "completed"
    FAILED    = "failed"

    # External control states
    PAUSED  = "paused"
    STOPPED = "stopped"


class ProsodyAnnotation( Enum ):
    """
    Prosody annotations for expressive TTS rendering.

    These annotations are embedded in the script and processed
    by the TTS client to adjust voice characteristics.
    """
    # Emotional markers
    LAUGH        = "laugh"
    CHUCKLE      = "chuckle"
    WHISPER      = "whisper"
    EXCITED      = "excited"
    THOUGHTFUL   = "thoughtful"
    SURPRISED    = "surprised"

    # Pacing markers
    PAUSE        = "pause"
    LONG_PAUSE   = "long_pause"
    SPEED_UP     = "speed_up"
    SLOW_DOWN    = "slow_down"

    # Emphasis markers
    EMPHASIS     = "emphasis"
    QUESTIONING  = "questioning"
    MATTER_OF_FACT = "matter_of_fact"


# =============================================================================
# Pydantic Models for Structured Outputs
# =============================================================================

class ScriptSegment( BaseModel ):
    """
    A single dialogue segment in the podcast script.

    Each segment represents one speaker's turn with optional
    prosody annotations for TTS rendering.
    """

    speaker           : str = Field( description="Name of the speaker (Host A or B name)" )
    role              : str = Field( description="Role: 'curious' or 'expert'" )
    text              : str = Field( description="The dialogue text" )
    prosody           : list[ str ] = Field(
        default_factory = list,
        description     = "Prosody annotations embedded in text"
    )
    topic_reference   : Optional[ str ] = Field(
        default     = None,
        description = "Topic from research doc this segment discusses"
    )
    estimated_duration_seconds : float = Field(
        default     = 0.0,
        description = "Estimated TTS duration in seconds"
    )

    def to_markdown( self ) -> str:
        """
        Convert segment to minimalist markdown format.

        Format:
            **[Speaker - Role]**: Text with *[prosody]* annotations

        Returns:
            str: Markdown formatted dialogue line
        """
        return f"**[{self.speaker} - {self.role.title()}]**: {self.text}"


class PodcastScript( BaseModel ):
    """
    Complete podcast script with all dialogue segments.

    Contains the full script ready for TTS processing.
    """

    title                : str = Field( description="Podcast episode title" )
    research_source      : str = Field( description="Path or name of source research document" )
    generated_at         : str = Field(
        default_factory = lambda: datetime.now().isoformat(),
        description     = "Timestamp when script was generated"
    )
    host_a_name          : str = Field( description="Name of Host A" )
    host_b_name          : str = Field( description="Name of Host B" )
    segments             : list[ ScriptSegment ] = Field( default_factory=list )
    estimated_duration_minutes : float = Field( default=0.0 )
    key_topics           : list[ str ] = Field(
        default_factory = list,
        description     = "Main topics covered in the podcast"
    )
    revision_count       : int = Field( default=0 )

    def to_markdown( self ) -> str:
        """
        Convert entire script to minimalist markdown format.

        Returns:
            str: Full markdown script document
        """
        lines = [
            f"# Podcast: {self.title}",
            f"## Generated: {self.generated_at}",
            f"## Hosts: {self.host_a_name}, {self.host_b_name}",
            f"## Estimated Duration: {self.estimated_duration_minutes:.1f} minutes",
            "",
            "---",
            "",
        ]

        for segment in self.segments:
            lines.append( segment.to_markdown() )
            lines.append( "" )

        return "\n".join( lines )

    def get_segment_count( self ) -> int:
        """Get total number of dialogue segments."""
        return len( self.segments )

    def get_speaker_word_counts( self ) -> dict[ str, int ]:
        """Get word count per speaker."""
        counts = {}
        for segment in self.segments:
            words = len( segment.text.split() )
            counts[ segment.speaker ] = counts.get( segment.speaker, 0 ) + words
        return counts


class ContentAnalysis( BaseModel ):
    """
    Analysis of the research document for script generation.

    Extracts key topics, interesting facts, and discussion points
    from the source document.
    """

    main_topic           : str = Field( description="Primary topic of the research" )
    key_subtopics        : list[ str ] = Field(
        default_factory = list,
        description     = "Important subtopics to cover"
    )
    interesting_facts    : list[ str ] = Field(
        default_factory = list,
        description     = "Surprising or engaging facts to highlight"
    )
    discussion_questions : list[ str ] = Field(
        default_factory = list,
        description     = "Questions the hosts should explore"
    )
    analogies_suggested  : list[ str ] = Field(
        default_factory = list,
        description     = "Analogies to make concepts accessible"
    )
    target_audience      : str = Field(
        default     = "general audience",
        description = "Intended audience level"
    )
    complexity_level     : Literal[ "beginner", "intermediate", "advanced" ] = Field(
        default = "intermediate"
    )
    estimated_coverage_minutes : float = Field( default=10.0 )


class PodcastMetadata( BaseModel ):
    """
    Metadata about the generated podcast.

    Tracks generation details, costs, and output locations.
    """

    podcast_id           : str = Field( description="Unique identifier for this podcast" )
    user_id              : str = Field( description="User who requested the podcast" )
    research_doc_path    : str = Field( description="Path to source research document" )
    script_path          : Optional[ str ] = Field( default=None )
    audio_path           : Optional[ str ] = Field( default=None )
    generated_at         : str = Field( default_factory=lambda: datetime.now().isoformat() )
    generation_duration_seconds : float = Field( default=0.0 )
    api_calls_count      : int = Field( default=0 )
    total_tokens_used    : int = Field( default=0 )
    estimated_cost_usd   : float = Field( default=0.0 )
    script_revision_count: int = Field( default=0 )


# =============================================================================
# TypedDict for Graph State
# =============================================================================

class PodcastState( TypedDict ):
    """
    Main graph state for the podcast generator agent.

    This TypedDict defines the complete state that flows through
    the generation workflow, tracking all phases and intermediate results.
    """

    # Input
    research_doc_path    : str
    research_content     : Optional[ str ]
    user_id              : str

    # Analysis Phase
    content_analysis     : Optional[ ContentAnalysis ]
    topics_extracted     : bool
    analysis_confidence  : float

    # Script Generation Phase
    draft_script         : Optional[ PodcastScript ]
    script_approved      : bool
    human_feedback       : Optional[ str ]
    revision_count       : int

    # Audio Generation Phase (Phase 2)
    audio_segments       : list[ str ]  # Paths to individual audio files
    audio_generation_progress : float

    # Final Output
    final_script_path    : Optional[ str ]
    final_audio_path     : Optional[ str ]
    metadata             : Optional[ PodcastMetadata ]

    # Control
    current_state        : str
    error_message        : Optional[ str ]


def create_initial_state(
    research_doc_path: str,
    user_id: str
) -> PodcastState:
    """
    Create the initial state for a podcast generation task.

    Requires:
        - research_doc_path is a non-empty string
        - user_id is a valid identifier

    Ensures:
        - Returns fully initialized PodcastState with defaults
        - All counters start at 0
        - All optional fields are None or empty

    Args:
        research_doc_path: Path to the research document
        user_id: User identifier for output directory

    Returns:
        PodcastState: Initialized state dictionary
    """
    return PodcastState(
        research_doc_path   = research_doc_path,
        research_content    = None,
        user_id             = user_id,
        content_analysis    = None,
        topics_extracted    = False,
        analysis_confidence = 0.0,
        draft_script        = None,
        script_approved     = False,
        human_feedback      = None,
        revision_count      = 0,
        audio_segments      = [],
        audio_generation_progress = 0.0,
        final_script_path   = None,
        final_audio_path    = None,
        metadata            = None,
        current_state       = OrchestratorState.LOADING_RESEARCH.value,
        error_message       = None,
    )


def quick_smoke_test():
    """Quick smoke test for state schemas."""
    import cosa.utils.util as cu

    cu.print_banner( "Podcast Generator State Smoke Test", prepend_nl=True )

    try:
        # Test 1: OrchestratorState enum
        print( "Testing OrchestratorState enum..." )
        assert OrchestratorState.LOADING_RESEARCH.value == "loading_research"
        assert OrchestratorState.COMPLETED.value == "completed"
        assert len( OrchestratorState ) == 10
        print( f"✓ OrchestratorState enum valid ({len( OrchestratorState )} states)" )

        # Test 2: ProsodyAnnotation enum
        print( "Testing ProsodyAnnotation enum..." )
        assert ProsodyAnnotation.LAUGH.value == "laugh"
        assert ProsodyAnnotation.PAUSE.value == "pause"
        assert len( ProsodyAnnotation ) == 13
        print( f"✓ ProsodyAnnotation enum valid ({len( ProsodyAnnotation )} annotations)" )

        # Test 3: ScriptSegment model
        print( "Testing ScriptSegment model..." )
        segment = ScriptSegment(
            speaker         = "Alex",
            role            = "curious",
            text            = "So what you're saying is... *[pause]* this changes everything?",
            prosody         = [ "pause" ],
            topic_reference = "quantum computing",
        )
        assert segment.speaker == "Alex"
        assert "pause" in segment.prosody
        markdown = segment.to_markdown()
        assert "**[Alex - Curious]**" in markdown
        print( "✓ ScriptSegment model validates and converts to markdown" )

        # Test 4: PodcastScript model
        print( "Testing PodcastScript model..." )
        script = PodcastScript(
            title           = "Understanding Quantum Computing",
            research_source = "/path/to/research.md",
            host_a_name     = "Alex",
            host_b_name     = "Jordan",
            segments        = [ segment ],
            estimated_duration_minutes = 12.5,
            key_topics      = [ "quantum", "computing", "future" ],
        )
        assert script.get_segment_count() == 1
        word_counts = script.get_speaker_word_counts()
        assert "Alex" in word_counts
        markdown_full = script.to_markdown()
        assert "# Podcast: Understanding Quantum Computing" in markdown_full
        print( "✓ PodcastScript model validates" )

        # Test 5: ContentAnalysis model
        print( "Testing ContentAnalysis model..." )
        analysis = ContentAnalysis(
            main_topic        = "Quantum Computing",
            key_subtopics     = [ "qubits", "entanglement", "applications" ],
            interesting_facts = [ "Quantum computers can be 100M times faster" ],
            discussion_questions = [ "Will quantum computers replace classical?" ],
        )
        assert analysis.complexity_level == "intermediate"  # Default
        assert len( analysis.key_subtopics ) == 3
        print( "✓ ContentAnalysis model validates" )

        # Test 6: PodcastMetadata model
        print( "Testing PodcastMetadata model..." )
        metadata = PodcastMetadata(
            podcast_id        = "podcast-123",
            user_id           = "user@example.com",
            research_doc_path = "/path/to/research.md",
            api_calls_count   = 5,
            total_tokens_used = 10000,
        )
        assert metadata.script_revision_count == 0  # Default
        print( "✓ PodcastMetadata model validates" )

        # Test 7: create_initial_state
        print( "Testing create_initial_state..." )
        state = create_initial_state(
            research_doc_path = "/path/to/research.md",
            user_id           = "user@example.com",
        )
        assert state[ "research_doc_path" ] == "/path/to/research.md"
        assert state[ "user_id" ] == "user@example.com"
        assert state[ "revision_count" ] == 0
        assert state[ "script_approved" ] is False
        assert state[ "current_state" ] == "loading_research"
        print( f"✓ create_initial_state works ({len( state )} keys)" )

        print( "\n✓ Podcast Generator State smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
