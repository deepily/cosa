#!/usr/bin/env python3
"""
Presentation Orchestrator Agent — Top-level coordinator for presentation generation.

This agent manages the entire presentation generation workflow internally as a single
queue entry, yielding control at I/O boundaries via async/await.

Design Pattern: Top-Level Orchestrator (same as Podcast Generator)
- Single job in queue, multi-phase internal state machine
- Async execution for non-blocking queue behavior
- Queryable state for external monitoring
- Controllable via pause/stop

Phase progression:
    INGESTING → ANALYZING → OUTLINING → ELABORATING → SERIALIZING
    → RENDERING_TEXT → RENDERING_VISUALS → DELIVERING → COMPLETED

Current status: Skeleton with stub phase methods (Phase 2 foundation).
Real implementations will be added in Phases 3-8.
"""

import asyncio
import logging
import uuid
from typing import Optional, List
from datetime import datetime

from .config import PresentationConfig
from .state import (
    OrchestratorState,
    PresentationModel,
    NarrativeSection,
    SlideModel,
    create_initial_state,
)
from . import cosa_interface
from . import voice_io

logger = logging.getLogger( __name__ )


class PresentationOrchestratorAgent:
    """
    Top-level orchestrator for presentation generation — single job, multi-phase, async.

    Standalone class (not inheriting from AgentBase) because:
    - AgentBase is synchronous, this is async
    - Different execution model (yields on await vs blocking)
    - Composition over inheritance for COSA integration

    Requires:
        - source_path points to a valid file
        - user_id is a valid system identifier

    Ensures:
        - Manages entire presentation workflow internally
        - Yields control at I/O boundaries (await points)
        - State is queryable via get_state()
        - Can be stopped externally via request_stop()
    """

    def __init__(
        self,
        source_path : str,
        user_id     : str,
        config      : Optional[ PresentationConfig ] = None,
        debug       : bool = False,
        verbose     : bool = False
    ):
        """
        Initialize the presentation orchestrator.

        Args:
            source_path: Path to the source document (markdown/text)
            user_id: System user ID for event routing
            config: Presentation configuration (uses defaults if None)
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.source_path = source_path
        self.user_id     = user_id
        self.config      = config or PresentationConfig()
        self.debug       = debug
        self.verbose     = verbose

        # State management
        self.state            = OrchestratorState.INITIALIZED
        self._stop_requested  = False

        # Initialize internal state tracking dict
        self._presentation_state = create_initial_state( source_path, user_id )

        # Generate presentation ID
        self.presentation_id = f"pres-{uuid.uuid4().hex[ :8 ]}"

        # Metrics
        self.metrics = {
            "start_time"  : None,
            "end_time"    : None,
            "api_calls"   : 0,
            "tokens_used" : 0,
        }

        if self.debug:
            print( f"[PresentationOrchestratorAgent] Initialized for: {source_path}" )
            print( f"[PresentationOrchestratorAgent] Presentation ID: {self.presentation_id}" )

    # =========================================================================
    # External Control
    # =========================================================================

    def request_stop( self ):
        """Request graceful stop at next phase boundary."""
        self._stop_requested = True
        if self.debug: print( "[PresentationOrchestratorAgent] Stop requested" )

    def _check_stop( self ) -> bool:
        """
        Check if stop has been requested.

        Returns:
            bool: True if stop was requested
        """
        return self._stop_requested

    async def _handle_stop( self ) -> None:
        """Handle graceful stop — update state and notify."""
        self.state = OrchestratorState.CANCELLED
        await voice_io.notify( "Presentation generation cancelled.", priority="medium" )
        if self.debug: print( "[PresentationOrchestratorAgent] Stopped gracefully" )

    # =========================================================================
    # State Query
    # =========================================================================

    def get_state( self ) -> dict:
        """
        Return current orchestrator state for external monitoring.

        Ensures:
            - Returns dict with state, presentation_id, metrics, internal state

        Returns:
            dict: Current state snapshot
        """
        return {
            "state"           : self.state.value,
            "presentation_id" : self.presentation_id,
            "source_path"     : self.source_path,
            "metrics"         : self.metrics,
            "internal_state"  : {
                k: v is not None for k, v in self._presentation_state.items()
                if k not in ( "user_id", "source_path" )
            },
        }

    # =========================================================================
    # Main Execution
    # =========================================================================

    async def do_all_async( self ) -> Optional[ PresentationModel ]:
        """
        Main execution — run all phases sequentially.

        Yields on I/O, doesn't block other jobs.

        Ensures:
            - Progresses through all phases in order
            - Checks for stop request between phases
            - Returns PresentationModel on success, None if cancelled

        Returns:
            PresentationModel or None if cancelled/failed
        """
        self.metrics[ "start_time" ] = datetime.now().isoformat()

        try:
            # Phase 1: Ingest
            self.state = OrchestratorState.INGESTING
            await voice_io.notify( "Phase 1: Ingesting source document...", priority="low" )
            source_content = await self._ingest_async()
            self._presentation_state[ "source_content" ] = source_content
            if self._check_stop(): await self._handle_stop(); return None

            # Phase 2: Analyze
            self.state = OrchestratorState.ANALYZING
            await voice_io.notify( "Phase 2: Analyzing narrative structure...", priority="low" )
            narrative_sections = await self._analyze_async( source_content )
            self._presentation_state[ "narrative_sections" ] = narrative_sections
            if self._check_stop(): await self._handle_stop(); return None

            # Gate 1: Narrative arc review (stub — auto-approve)
            gate1_approved = await self._gate_1_narrative_review( narrative_sections )
            if not gate1_approved: await self._handle_stop(); return None

            # Phase 3: Outline
            self.state = OrchestratorState.OUTLINING
            await voice_io.notify( "Phase 3: Generating slide outline...", priority="low" )
            slide_outline = await self._outline_async( narrative_sections )
            self._presentation_state[ "slide_outline" ] = slide_outline
            if self._check_stop(): await self._handle_stop(); return None

            # Gate 2: Slide titles + visual types review (stub — auto-approve)
            gate2_approved = await self._gate_2_outline_review( slide_outline )
            if not gate2_approved: await self._handle_stop(); return None

            # Phase 4: Elaborate
            self.state = OrchestratorState.ELABORATING
            await voice_io.notify( "Phase 4: Elaborating slide content...", priority="low" )
            elaborated_slides = await self._elaborate_async( slide_outline )
            self._presentation_state[ "elaborated_slides" ] = elaborated_slides
            if self._check_stop(): await self._handle_stop(); return None

            # Gate 3: Full content review (stub — auto-approve)
            gate3_approved = await self._gate_3_content_review( elaborated_slides )
            if not gate3_approved: await self._handle_stop(); return None

            # Phase 5: Serialize
            self.state = OrchestratorState.SERIALIZING
            await voice_io.notify( "Phase 5: Serializing to YAML...", priority="low" )
            presentation_model = await self._serialize_async( elaborated_slides )
            self._presentation_state[ "presentation_model" ] = presentation_model
            if self._check_stop(): await self._handle_stop(); return None

            # Phase 6: Render Text
            self.state = OrchestratorState.RENDERING_TEXT
            await voice_io.notify( "Phase 6: Rendering Marp Markdown...", priority="low" )
            await self._render_text_async( presentation_model )
            if self._check_stop(): await self._handle_stop(); return None

            # Phase 7: Render Visuals
            self.state = OrchestratorState.RENDERING_VISUALS
            await voice_io.notify( "Phase 7: Rendering visual elements...", priority="low" )
            await self._render_visuals_async( presentation_model )
            if self._check_stop(): await self._handle_stop(); return None

            # Gate 4: Final rendered output review (stub — auto-approve)
            gate4_approved = await self._gate_4_render_review( presentation_model )
            if not gate4_approved: await self._handle_stop(); return None

            # Phase 8: Deliver
            self.state = OrchestratorState.DELIVERING
            await voice_io.notify( "Phase 8: Delivering final artifacts...", priority="low" )
            await self._deliver_async( presentation_model )

            # Complete
            self.state = OrchestratorState.COMPLETED
            self.metrics[ "end_time" ] = datetime.now().isoformat()
            await voice_io.notify( "Presentation generation complete!", priority="medium" )

            return presentation_model

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = datetime.now().isoformat()
            logger.error( f"Presentation generation failed: {e}" )
            await voice_io.notify( f"Presentation generation failed: {str( e )[ :100 ]}", priority="urgent" )
            raise

    # =========================================================================
    # Phase Stubs (to be implemented in Phases 3-8)
    # =========================================================================

    async def _ingest_async( self ) -> str:
        """
        Phase 1: Ingest source document.

        TODO (Phase 3): Read file, detect format, extract raw sections.

        Returns:
            str: Source document content
        """
        if self.debug: print( "[Orchestrator] Phase 1: Ingest (stub)" )
        await asyncio.sleep( 0.1 )  # Simulate work
        return f"[stub] Content from: {self.source_path}"

    async def _analyze_async( self, source_content: str ) -> List[ NarrativeSection ]:
        """
        Phase 2: Analyze narrative structure.

        TODO (Phase 3): Call Claude with source content + narrative prompt.

        Returns:
            List[NarrativeSection]: Classified document sections
        """
        if self.debug: print( "[Orchestrator] Phase 2: Analyze (stub)" )
        await asyncio.sleep( 0.1 )
        return []

    async def _outline_async( self, narrative_sections: List[ NarrativeSection ] ) -> list:
        """
        Phase 3: Generate slide outline with titles + visual types.

        TODO (Phase 4): Call Claude with narrative sections.

        Returns:
            list: Slide outline (title, visual_type) tuples
        """
        if self.debug: print( "[Orchestrator] Phase 3: Outline (stub)" )
        await asyncio.sleep( 0.1 )
        return []

    async def _elaborate_async( self, slide_outline: list ) -> List[ SlideModel ]:
        """
        Phase 4: Elaborate full slide content with presenter notes.

        TODO (Phase 4): Call Claude with outline + source.

        Returns:
            List[SlideModel]: Fully elaborated slides
        """
        if self.debug: print( "[Orchestrator] Phase 4: Elaborate (stub)" )
        await asyncio.sleep( 0.1 )
        return []

    async def _serialize_async( self, elaborated_slides: List[ SlideModel ] ) -> Optional[ PresentationModel ]:
        """
        Phase 5: Serialize to YAML intermediate file.

        TODO (Phase 5): Build PresentationModel, write YAML.

        Returns:
            PresentationModel or None
        """
        if self.debug: print( "[Orchestrator] Phase 5: Serialize (stub)" )
        await asyncio.sleep( 0.1 )
        return PresentationModel(
            title            = "Stub Presentation",
            duration_minutes = self.config.target_duration_minutes,
            source_document  = self.source_path,
            total_slides     = 0,
            slides           = [],
        )

    async def _render_text_async( self, presentation: Optional[ PresentationModel ] ) -> None:
        """
        Phase 6: Render YAML to Marp Markdown.

        TODO (Phase 6): Load theme, generate Marp markdown.
        """
        if self.debug: print( "[Orchestrator] Phase 6: Render Text (stub)" )
        await asyncio.sleep( 0.1 )

    async def _render_visuals_async( self, presentation: Optional[ PresentationModel ] ) -> None:
        """
        Phase 7: Render visual elements (Mermaid diagrams, etc.).

        TODO (Phase 7): For each slide with visual_type != text_only, call renderer.
        """
        if self.debug: print( "[Orchestrator] Phase 7: Render Visuals (stub)" )
        await asyncio.sleep( 0.1 )

    async def _deliver_async( self, presentation: Optional[ PresentationModel ] ) -> None:
        """
        Phase 8: Save final artifacts and send completion notification.

        TODO (Phase 8): Save YAML, Marp MD, generated visuals.
        """
        if self.debug: print( "[Orchestrator] Phase 8: Deliver (stub)" )
        await asyncio.sleep( 0.1 )

    # =========================================================================
    # Gate Stubs (to be implemented in Phases 3-4)
    # =========================================================================

    async def _gate_1_narrative_review( self, sections: list ) -> bool:
        """Gate 1: User reviews narrative arc mapping. Stub — auto-approve."""
        if self.debug: print( "[Orchestrator] Gate 1: Narrative review (auto-approve)" )
        return True

    async def _gate_2_outline_review( self, outline: list ) -> bool:
        """Gate 2: User reviews slide titles + visual types. Stub — auto-approve."""
        if self.debug: print( "[Orchestrator] Gate 2: Outline review (auto-approve)" )
        return True

    async def _gate_3_content_review( self, slides: list ) -> bool:
        """Gate 3: User reviews full structured content. Stub — auto-approve."""
        if self.debug: print( "[Orchestrator] Gate 3: Content review (auto-approve)" )
        return True

    async def _gate_4_render_review( self, presentation: Optional[ PresentationModel ] ) -> bool:
        """Gate 4: User reviews final rendered output. Stub — auto-approve."""
        if self.debug: print( "[Orchestrator] Gate 4: Render review (auto-approve)" )
        return True


# =============================================================================
# Smoke Test
# =============================================================================

def quick_smoke_test():
    """Quick smoke test for PresentationOrchestratorAgent."""
    import cosa.utils.util as cu

    cu.print_banner( "PresentationOrchestratorAgent Smoke Test", prepend_nl=True )

    try:
        # Test 1: Construction
        print( "Testing orchestrator construction..." )
        agent = PresentationOrchestratorAgent(
            source_path = "/test/doc.md",
            user_id     = "test-user",
            debug       = True
        )
        assert agent.state == OrchestratorState.INITIALIZED
        assert agent.source_path == "/test/doc.md"
        assert agent.presentation_id.startswith( "pres-" )
        print( f"  Presentation ID: {agent.presentation_id}" )
        print( "  PASS" )

        # Test 2: get_state
        print( "Testing get_state..." )
        state = agent.get_state()
        assert state[ "state" ] == "initialized"
        assert state[ "presentation_id" ].startswith( "pres-" )
        assert "metrics" in state
        assert "internal_state" in state
        print( "  PASS" )

        # Test 3: Stop request
        print( "Testing stop request..." )
        assert agent._check_stop() is False
        agent.request_stop()
        assert agent._check_stop() is True
        print( "  PASS" )

        # Test 4: Default config
        print( "Testing default config..." )
        assert agent.config.target_duration_minutes == 15
        assert agent.config.slides_per_minute == 1.0
        print( "  PASS" )

        # Test 5: Async state progression (run stubs)
        print( "Testing async state progression..." )

        async def run_stub_phases():
            # Reset stop flag
            agent._stop_requested = False

            # Run phase 1 stub
            agent.state = OrchestratorState.INGESTING
            content = await agent._ingest_async()
            assert "[stub]" in content

            # Run phase 2 stub
            agent.state = OrchestratorState.ANALYZING
            sections = await agent._analyze_async( content )
            assert sections == []

            # Verify gates auto-approve
            assert await agent._gate_1_narrative_review( [] ) is True
            assert await agent._gate_2_outline_review( [] ) is True
            assert await agent._gate_3_content_review( [] ) is True
            assert await agent._gate_4_render_review( None ) is True

            return True

        result = asyncio.run( run_stub_phases() )
        assert result is True
        print( "  PASS" )

        print( "\nAll PresentationOrchestratorAgent smoke tests passed" )

    except Exception as e:
        print( f"\nSmoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
