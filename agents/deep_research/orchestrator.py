#!/usr/bin/env python3
"""
Research Orchestrator Agent - Top-level coordinator for deep research.

This agent manages the entire research workflow internally as a single
queue entry, yielding control at I/O boundaries via async/await.

Design Pattern: Top-Level Orchestrator
- Single job in queue, multi-phase internal state machine
- Async execution for non-blocking queue behavior
- Queryable state for external monitoring
- Controllable via pause/resume/stop
"""

import asyncio
import time
import logging
from typing import Optional, Any

from .config import ResearchConfig
from .state import (
    OrchestratorState,
    ResearchState,
    ResearchPlan,
    SubagentFinding,
    create_initial_state
)
from . import cosa_interface

logger = logging.getLogger( __name__ )


class ResearchOrchestratorAgent:
    """
    Top-level orchestrator - single job, multi-phase, async execution.

    This is a standalone class (not inheriting from AgentBase) because:
    - AgentBase is synchronous, this is async
    - Different execution model (yields on await vs blocking)
    - Composition over inheritance for COSA integration

    Requires:
        - query is a non-empty string
        - user_id is a valid system identifier

    Ensures:
        - Manages entire research workflow internally
        - Yields control at I/O boundaries (await points)
        - State is queryable via get_state()
        - Can be paused, resumed, or stopped externally
    """

    def __init__(
        self,
        query: str,
        user_id: str,
        config: Optional[ ResearchConfig ] = None,
        debug: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the research orchestrator.

        Args:
            query: The user's research query
            user_id: System user ID for event routing
            config: Research configuration (uses defaults if None)
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.query   = query
        self.user_id = user_id
        self.config  = config or ResearchConfig()
        self.debug   = debug
        self.verbose = verbose

        # State management
        self.state      = OrchestratorState.CLARIFYING
        self.sub_tasks  : list[ asyncio.Task ] = []
        self.findings   : list[ Any ] = []
        self._pause_requested = False
        self._stop_requested  = False

        # Initialize research state (TypedDict for graph)
        self._research_state = create_initial_state( query )

        # Metrics
        self.metrics = {
            "start_time"  : None,
            "end_time"    : None,
            "tokens_used" : 0,
            "api_calls"   : 0,
        }

        if self.debug: print( f"[ResearchOrchestratorAgent] Initialized for query: {query[:50]}..." )

    async def do_all_async( self ) -> Optional[str]:
        """
        Main execution - yields on I/O, doesn't block other jobs.

        Each `await` is a potential yield point where other jobs can execute.
        This method implements the full research workflow:
        1. Clarification - Understand the query
        2. Planning - Create research strategy
        3. Research - Execute parallel subagents
        4. Synthesis - Combine findings
        5. Review - Get user feedback
        6. Citation - Add sources

        Requires:
            - COSA interface is configured (for human feedback)

        Ensures:
            - Executes complete research workflow
            - Returns final report on success, None on cancellation
            - Updates state throughout execution

        Returns:
            str or None: Final research report, or None if cancelled
        """
        self.metrics[ "start_time" ] = time.time()

        try:
            # =================================================================
            # Phase 1: Clarification
            # =================================================================
            self.state = OrchestratorState.CLARIFYING
            await cosa_interface.notify_progress( "Starting research - analyzing your question..." )

            clarification = await self._clarify_query_async()

            if clarification.get( "needs_feedback" ):
                self.state = OrchestratorState.WAITING_CLARIFICATION
                response = await cosa_interface.get_feedback(
                    clarification.get( "question", "Could you clarify your question?" ),
                    timeout=self.config.feedback_timeout_seconds
                )
                self._research_state[ "clarification_response" ] = response
                self._research_state[ "clarification_rounds" ] += 1
                # TODO: Process clarification response in Phase 2

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 2: Planning
            # =================================================================
            self.state = OrchestratorState.PLANNING
            await cosa_interface.notify_progress( "Creating research plan..." )

            plan = await self._create_plan_async()
            self._research_state[ "plan" ] = plan

            # Get user approval for plan
            self.state = OrchestratorState.WAITING_PLAN_APPROVAL

            num_subqueries = len( plan.subqueries ) if plan else 0
            choice = await cosa_interface.present_choices( questions=[ {
                "question"    : "Research plan ready. How should we proceed?",
                "header"      : "Plan",
                "multiSelect" : False,
                "options"     : [
                    { "label": "Execute plan", "description": f"{num_subqueries} research threads" },
                    { "label": "Modify scope", "description": "Adjust focus or depth" },
                    { "label": "Cancel", "description": "Abort research" }
                ]
            } ] )

            plan_choice = choice.get( "answers", {} ).get( "Plan", "" )

            if plan_choice == "Cancel":
                self.state = OrchestratorState.STOPPED
                return None

            if plan_choice == "Modify scope":
                # TODO: Handle plan modification in Phase 2
                pass

            self._research_state[ "plan_approved" ] = True

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 3: Parallel Research
            # =================================================================
            self.state = OrchestratorState.RESEARCHING
            await cosa_interface.notify_progress( "Starting parallel research..." )

            # TODO: Implement parallel research execution in Phase 2
            # Placeholder: Would spawn subagent tasks here
            # self.sub_tasks = [
            #     asyncio.create_task( self._research_subquery_async( sq, i ) )
            #     for i, sq in enumerate( plan.subqueries if plan else [] )
            # ]
            # self.findings = await asyncio.gather( *self.sub_tasks, return_exceptions=True )

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 4: Gathering & Synthesis
            # =================================================================
            self.state = OrchestratorState.GATHERING
            await cosa_interface.notify_progress( "Gathering and analyzing findings..." )

            self.state = OrchestratorState.SYNTHESIZING
            await cosa_interface.notify_progress( "Synthesizing report..." )

            report = await self._synthesize_async()
            self._research_state[ "draft_report" ] = report

            # =================================================================
            # Phase 5: Review
            # =================================================================
            self.state = OrchestratorState.WAITING_DRAFT_REVIEW
            feedback = await cosa_interface.get_feedback(
                "Draft ready. Any feedback or changes needed?",
                timeout=self.config.feedback_timeout_seconds
            )

            if feedback and not cosa_interface.is_approval( feedback ):
                self._research_state[ "human_feedback_on_draft" ] = feedback
                self._research_state[ "draft_revision_count" ] += 1
                report = await self._revise_report_async( report, feedback )

            if self._check_stop(): return await self._handle_stop()

            # =================================================================
            # Phase 6: Citations
            # =================================================================
            self.state = OrchestratorState.CITING
            await cosa_interface.notify_progress( "Adding citations..." )

            final_report = await self._add_citations_async( report )
            self._research_state[ "final_report" ] = final_report

            # =================================================================
            # Completion
            # =================================================================
            self.state = OrchestratorState.COMPLETED
            self.metrics[ "end_time" ] = time.time()
            await cosa_interface.notify_progress( "Research complete!" )

            return final_report

        except Exception as e:
            self.state = OrchestratorState.FAILED
            self.metrics[ "end_time" ] = time.time()
            logger.error( f"Research failed: {e}" )
            await cosa_interface.notify_progress(
                f"Research failed: {str( e )[:100]}",
                priority="urgent"
            )
            raise

    def get_state( self ) -> dict:
        """
        Query current orchestrator state for external monitoring.

        Ensures:
            - Returns dict with phase, progress, sub-task status, metrics

        Returns:
            dict: Current state summary
        """
        return {
            "state"          : self.state.value,
            "progress_pct"   : self._calculate_progress(),
            "sub_tasks"      : [
                {
                    "index"     : i,
                    "done"      : t.done(),
                    "cancelled" : t.cancelled()
                }
                for i, t in enumerate( self.sub_tasks )
            ],
            "findings_count" : len( [ f for f in self.findings if f ] ),
            "metrics"        : self.metrics,
            "query"          : self.query[ :100 ],  # Truncated for safety
        }

    async def pause( self ) -> bool:
        """
        Request graceful pause at next yield point.

        Ensures:
            - Sets pause flag
            - Returns True (pause always accepted)

        Returns:
            bool: True indicating pause requested
        """
        self._pause_requested = True
        return True

    async def resume( self ) -> bool:
        """
        Resume from paused state.

        Ensures:
            - Clears pause flag if in PAUSED state
            - Returns True if resumed, False if not paused

        Returns:
            bool: True if successfully resumed
        """
        if self.state == OrchestratorState.PAUSED:
            self._pause_requested = False
            return True
        return False

    async def stop( self ) -> dict:
        """
        Cancel all sub-tasks and return partial results.

        Ensures:
            - Cancels all running sub-tasks
            - Sets state to STOPPED
            - Returns partial findings

        Returns:
            dict: Partial results including findings and stop point
        """
        self._stop_requested = True
        for task in self.sub_tasks:
            if not task.done():
                task.cancel()
        self.state = OrchestratorState.STOPPED
        return {
            "partial_findings" : self.findings,
            "stopped_at"       : self.state.value,
            "partial_report"   : self._research_state.get( "draft_report" )
        }

    # =========================================================================
    # Private Methods (Placeholders for Phase 2)
    # =========================================================================

    def _check_stop( self ) -> bool:
        """Check if stop was requested."""
        return self._stop_requested

    async def _handle_stop( self ) -> None:
        """Handle stop request gracefully."""
        await cosa_interface.notify_progress( "Research stopped by user request." )
        self.state = OrchestratorState.STOPPED
        return None

    def _calculate_progress( self ) -> int:
        """
        Calculate completion percentage based on current state.

        Returns:
            int: Progress percentage (0-100)
        """
        state_progress = {
            OrchestratorState.CLARIFYING            : 10,
            OrchestratorState.WAITING_CLARIFICATION : 15,
            OrchestratorState.PLANNING              : 20,
            OrchestratorState.WAITING_PLAN_APPROVAL : 25,
            OrchestratorState.RESEARCHING           : 50,
            OrchestratorState.GATHERING             : 70,
            OrchestratorState.SYNTHESIZING          : 80,
            OrchestratorState.WAITING_DRAFT_REVIEW  : 85,
            OrchestratorState.CITING                : 95,
            OrchestratorState.COMPLETED             : 100,
            OrchestratorState.FAILED                : 0,
            OrchestratorState.PAUSED                : 0,
            OrchestratorState.STOPPED               : 0,
        }
        return state_progress.get( self.state, 0 )

    async def _clarify_query_async( self ) -> dict:
        """
        Placeholder: Analyze query for clarification needs.

        Phase 2 will implement with Claude API call.

        Returns:
            dict: {"needs_feedback": bool, "question": str, "understood_query": str}
        """
        # TODO: Implement with Claude API call
        return {
            "needs_feedback"   : False,
            "understood_query" : self.query
        }

    async def _create_plan_async( self ) -> Optional[ ResearchPlan ]:
        """
        Placeholder: Create research plan with Claude.

        Phase 2 will implement with Claude API call.

        Returns:
            ResearchPlan or None
        """
        # TODO: Implement with Claude API call
        # Return a placeholder plan for testing
        from .state import SubQuery

        return ResearchPlan(
            complexity="moderate",
            subqueries=[
                SubQuery(
                    topic=self.query,
                    objective="Research the topic",
                    output_format="summary"
                )
            ],
            estimated_subagents=1,
            rationale="Placeholder plan for Phase 1 testing"
        )

    async def _synthesize_async( self ) -> str:
        """
        Placeholder: Synthesize findings into report.

        Phase 2 will implement synthesis logic.

        Returns:
            str: Draft report
        """
        # TODO: Implement synthesis
        return f"Research report placeholder for: {self.query}"

    async def _revise_report_async( self, report: str, feedback: str ) -> str:
        """
        Placeholder: Revise report based on feedback.

        Phase 2 will implement revision logic.

        Args:
            report: Current report draft
            feedback: User feedback

        Returns:
            str: Revised report
        """
        # TODO: Implement revision
        return report

    async def _add_citations_async( self, report: str ) -> str:
        """
        Placeholder: Add citations to report.

        Phase 2 will implement citation addition.

        Args:
            report: Report without citations

        Returns:
            str: Report with citations
        """
        # TODO: Implement citation addition
        return report


def quick_smoke_test():
    """Quick smoke test for ResearchOrchestratorAgent."""
    import cosa.utils.util as cu
    import asyncio

    cu.print_banner( "Research Orchestrator Smoke Test", prepend_nl=True )

    try:
        # Test 1: Instantiation
        print( "Testing instantiation..." )
        agent = ResearchOrchestratorAgent(
            query="What is quantum computing?",
            user_id="test-user-123",
            debug=True
        )
        assert agent.query == "What is quantum computing?"
        assert agent.state == OrchestratorState.CLARIFYING
        print( "✓ Agent instantiated correctly" )

        # Test 2: get_state
        print( "Testing get_state..." )
        state = agent.get_state()
        assert "state" in state
        assert "progress_pct" in state
        assert "metrics" in state
        assert state[ "state" ] == "clarifying"
        print( f"✓ get_state works (state={state[ 'state' ]}, progress={state[ 'progress_pct' ]}%)" )

        # Test 3: _calculate_progress
        print( "Testing _calculate_progress..." )
        assert agent._calculate_progress() == 10  # CLARIFYING = 10%
        agent.state = OrchestratorState.RESEARCHING
        assert agent._calculate_progress() == 50  # RESEARCHING = 50%
        agent.state = OrchestratorState.COMPLETED
        assert agent._calculate_progress() == 100  # COMPLETED = 100%
        print( "✓ _calculate_progress returns correct values" )

        # Test 4: Async placeholder methods (run in event loop)
        print( "Testing async placeholder methods..." )

        async def test_placeholders():
            agent2 = ResearchOrchestratorAgent(
                query="Test query",
                user_id="test-user"
            )

            # Test _clarify_query_async
            clarification = await agent2._clarify_query_async()
            assert "needs_feedback" in clarification
            assert clarification[ "needs_feedback" ] is False

            # Test _create_plan_async
            plan = await agent2._create_plan_async()
            assert plan is not None
            assert plan.complexity == "moderate"

            # Test _synthesize_async
            report = await agent2._synthesize_async()
            assert "Test query" in report

            return True

        result = asyncio.run( test_placeholders() )
        assert result is True
        print( "✓ Async placeholder methods work correctly" )

        # Test 5: pause/resume/stop
        print( "Testing control methods..." )

        async def test_control():
            agent3 = ResearchOrchestratorAgent(
                query="Control test",
                user_id="test-user"
            )

            # Test pause
            paused = await agent3.pause()
            assert paused is True
            assert agent3._pause_requested is True

            # Test resume (not paused state, so returns False)
            resumed = await agent3.resume()
            assert resumed is False  # Not in PAUSED state

            # Test stop
            result = await agent3.stop()
            assert agent3.state == OrchestratorState.STOPPED
            assert "partial_findings" in result

            return True

        result = asyncio.run( test_control() )
        assert result is True
        print( "✓ Control methods (pause/resume/stop) work correctly" )

        print( "\n✓ Research Orchestrator smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
