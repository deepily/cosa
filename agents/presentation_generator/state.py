#!/usr/bin/env python3
"""
State models for Presentation Generator Agent.

Defines the orchestrator state machine, Pydantic models for slides
and presentations, and narrative section classification.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Orchestrator State Machine
# =============================================================================

class OrchestratorState( str, Enum ):
    """
    State machine for the presentation generation pipeline.

    Active states progress sequentially through the pipeline.
    Terminal states indicate completion or failure.
    """
    # Active states
    INITIALIZED       = "initialized"
    INGESTING         = "ingesting"
    ANALYZING         = "analyzing"
    OUTLINING         = "outlining"
    ELABORATING       = "elaborating"
    SERIALIZING       = "serializing"
    RENDERING_TEXT    = "rendering_text"
    RENDERING_VISUALS = "rendering_visuals"
    DELIVERING        = "delivering"

    # Terminal states
    COMPLETED         = "completed"
    FAILED            = "failed"
    CANCELLED         = "cancelled"


# =============================================================================
# Narrative Arc Classification
# =============================================================================

class ArcPosition( str, Enum ):
    """
    Position within the narrative arc of a presentation.

    Used during Phase 2 (Analyze) to classify document sections
    and map them to the presentation structure.
    """
    SETUP       = "setup"
    ARGUMENT    = "argument"
    EVIDENCE    = "evidence"
    TRANSITION  = "transition"
    CONCLUSION  = "conclusion"
    CTA         = "cta"


class NarrativeSection( BaseModel ):
    """
    A classified section of the source document.

    Produced during Phase 2 (Analyze) when the LLM classifies
    each document section into a narrative arc position.

    Requires:
        - heading is a non-empty string
        - content is a non-empty string
        - arc_position is a valid ArcPosition
        - proposed_slides is a positive integer

    Ensures:
        - Section maps to exactly one arc position
        - proposed_slides suggests how many slides this section needs
    """
    heading         : str
    content         : str
    arc_position    : ArcPosition
    proposed_slides : int = 1


# =============================================================================
# Slide Models
# =============================================================================

class PresenterNotes( BaseModel ):
    """
    Presenter notes for a single slide — the speaking script.

    Requires:
        - talking_points is a list of strings
        - timing_seconds is a positive integer

    Ensures:
        - Contains all information needed to present the slide
    """
    transition     : Optional[ str ] = None
    talking_points : List[ str ]     = Field( default_factory=list )
    timing_seconds : int             = 60
    emphasis       : Optional[ str ] = None


class SlideModel( BaseModel ):
    """
    A single slide in the presentation.

    Requires:
        - number is a positive integer
        - arc_position is "opening", "body", or "closing"
        - type is a valid slide type
        - title is a non-empty string

    Ensures:
        - visual_type determines which renderer is used in Phase 7
        - visual_description provides natural-language spec for renderer
        - presenter_notes contains the speaking script
    """
    number             : int
    arc_position       : str
    type               : str
    title              : str
    subtitle           : Optional[ str ]          = None
    visual_type        : str                      = "text_only"
    visual_description : Optional[ str ]          = None
    content_bullets    : List[ str ]              = Field( default_factory=list )
    presenter_notes    : PresenterNotes           = Field( default_factory=PresenterNotes )


class PresentationModel( BaseModel ):
    """
    The complete presentation — the YAML intermediate contract.

    This model is serialized to YAML after Phase 5 and consumed
    by the rendering phases (6-8).

    Requires:
        - title is a non-empty string
        - slides is a list of SlideModel

    Ensures:
        - total_slides matches len(slides)
        - Can be serialized to/from YAML
    """
    title            : str
    speaker          : str                        = ""
    date             : str                        = ""
    duration_minutes : int                        = 15
    source_document  : str                        = ""
    total_slides     : int                        = 0
    slides           : List[ SlideModel ]         = Field( default_factory=list )
    theme            : str                        = "default"
    theme_overrides  : dict                       = Field( default_factory=dict )


# =============================================================================
# Orchestrator Internal State Factory
# =============================================================================

def create_initial_state( source_path: str, user_id: str ) -> dict:
    """
    Initialize internal orchestrator state tracking dict.

    Requires:
        - source_path is a non-empty string
        - user_id is a non-empty string

    Ensures:
        - Returns dict with all phase-tracking keys initialized

    Returns:
        dict: Initial orchestrator state
    """
    return {
        "source_path"       : source_path,
        "source_content"    : None,
        "narrative_sections": None,
        "slide_outline"     : None,
        "elaborated_slides" : None,
        "presentation_model": None,
        "yaml_path"         : None,
        "marp_path"         : None,
        "revision_count"    : 0,
        "human_feedback"    : None,
        "user_id"           : user_id,
    }


# =============================================================================
# Smoke Test
# =============================================================================

def quick_smoke_test():
    """Quick smoke test for presentation state models."""
    import cosa.utils.util as cu

    cu.print_banner( "Presentation Generator State Models Smoke Test", prepend_nl=True )

    try:
        # Test 1: OrchestratorState enum
        print( "Testing OrchestratorState enum..." )
        assert OrchestratorState.INITIALIZED == "initialized"
        assert OrchestratorState.COMPLETED == "completed"
        assert len( OrchestratorState ) == 12
        print( "  PASS" )

        # Test 2: ArcPosition enum
        print( "Testing ArcPosition enum..." )
        assert ArcPosition.SETUP == "setup"
        assert ArcPosition.CTA == "cta"
        assert len( ArcPosition ) == 6
        print( "  PASS" )

        # Test 3: NarrativeSection
        print( "Testing NarrativeSection model..." )
        section = NarrativeSection(
            heading      = "Background",
            content      = "Current tools miss 40% of edge cases.",
            arc_position = ArcPosition.SETUP,
            proposed_slides = 2
        )
        assert section.heading == "Background"
        assert section.arc_position == ArcPosition.SETUP
        assert section.proposed_slides == 2
        print( "  PASS" )

        # Test 4: PresenterNotes
        print( "Testing PresenterNotes model..." )
        notes = PresenterNotes(
            transition     = "So we've seen the problem...",
            talking_points = [ "Point 1", "Point 2" ],
            timing_seconds = 75,
            emphasis       = "Pause here"
        )
        assert notes.timing_seconds == 75
        assert len( notes.talking_points ) == 2
        print( "  PASS" )

        # Test 5: PresenterNotes defaults
        print( "Testing PresenterNotes defaults..." )
        defaults = PresenterNotes()
        assert defaults.transition is None
        assert defaults.talking_points == []
        assert defaults.timing_seconds == 60
        print( "  PASS" )

        # Test 6: SlideModel
        print( "Testing SlideModel..." )
        slide = SlideModel(
            number             = 5,
            arc_position       = "body",
            type               = "key_point",
            title              = "Three-Layer Cache Eliminates Cold Starts",
            visual_type        = "diagram",
            visual_description = "Flowchart: L1->L2->L3",
            content_bullets    = [ "L1: 80% hit rate", "L2: Redis", "L3: S3" ],
            presenter_notes    = notes
        )
        assert slide.number == 5
        assert slide.visual_type == "diagram"
        assert len( slide.content_bullets ) == 3
        assert slide.presenter_notes.timing_seconds == 75
        print( "  PASS" )

        # Test 7: SlideModel defaults
        print( "Testing SlideModel defaults..." )
        minimal = SlideModel(
            number       = 1,
            arc_position = "opening",
            type         = "title",
            title        = "My Talk"
        )
        assert minimal.visual_type == "text_only"
        assert minimal.visual_description is None
        assert minimal.content_bullets == []
        print( "  PASS" )

        # Test 8: PresentationModel
        print( "Testing PresentationModel..." )
        pres = PresentationModel(
            title            = "Test Presentation",
            duration_minutes = 15,
            total_slides     = 2,
            slides           = [ minimal, slide ]
        )
        assert pres.title == "Test Presentation"
        assert len( pres.slides ) == 2
        assert pres.theme == "default"
        print( "  PASS" )

        # Test 9: create_initial_state
        print( "Testing create_initial_state..." )
        state = create_initial_state( "/path/to/doc.md", "user123" )
        assert state[ "source_path" ] == "/path/to/doc.md"
        assert state[ "user_id" ] == "user123"
        assert state[ "revision_count" ] == 0
        assert state[ "yaml_path" ] is None
        print( "  PASS" )

        print( "\nAll Presentation Generator state model smoke tests passed" )

    except Exception as e:
        print( f"\nSmoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
