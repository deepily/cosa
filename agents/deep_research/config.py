#!/usr/bin/env python3
"""
Configuration for COSA Deep Research Agent.

Design decisions:
- Opus 4.5 for lead agent (planning, synthesis) - higher reasoning capability
- Sonnet 4 for subagents (research execution) - cost optimization
- Scaling heuristics from Anthropic blog post (June 2025)
- Configurable limits to prevent runaway execution
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ResearchConfig:
    """
    Configuration for the deep research agent.

    Requires:
        - All numeric values must be positive

    Ensures:
        - Provides sensible defaults for all parameters
        - get_max_subagents() returns appropriate limit for complexity
    """

    # === Model Selection ===
    lead_model     : str = "claude-opus-4-20250514"
    subagent_model : str = "claude-sonnet-4-20250514"

    # === Scaling Heuristics ===
    max_subagents_simple   : int = 1
    max_subagents_moderate : int = 4
    max_subagents_complex  : int = 10

    # === Execution Limits ===
    max_concurrent_subagents    : int = 5
    max_research_iterations     : int = 3
    max_tool_calls_per_subagent : int = 15
    max_clarification_rounds    : int = 2

    # === Token Budgets ===
    extended_thinking_budget : int = 10000
    subagent_context_limit   : int = 100000
    max_findings_tokens      : int = 50000

    # === COSA Integration ===
    feedback_timeout_seconds  : int  = 300
    stream_thoughts_to_voice  : bool = True
    narrate_progress          : bool = True

    # === Search Configuration ===
    search_tool              : str  = "web_search_20250305"
    prefer_primary_sources   : bool = True
    min_sources_per_subquery : int  = 3
    max_sources_per_subquery : int  = 10

    # === Output Configuration ===
    include_confidence_scores     : bool = True
    include_source_quality_notes  : bool = True
    citation_style                : Literal[ "inline", "footnote", "endnote" ] = "inline"

    def get_max_subagents( self, complexity: str ) -> int:
        """
        Get max subagents for given complexity level.

        Requires:
            - complexity is "simple", "moderate", or "complex"

        Ensures:
            - Returns appropriate limit for complexity
            - Falls back to moderate if unknown complexity

        Args:
            complexity: The assessed complexity level

        Returns:
            int: Maximum number of subagents to spawn
        """
        mapping = {
            "simple"   : self.max_subagents_simple,
            "moderate" : self.max_subagents_moderate,
            "complex"  : self.max_subagents_complex,
        }
        return mapping.get( complexity, self.max_subagents_moderate )


def quick_smoke_test():
    """Quick smoke test for ResearchConfig."""
    import cosa.utils.util as cu

    cu.print_banner( "ResearchConfig Smoke Test", prepend_nl=True )

    try:
        # Test 1: Default instantiation
        print( "Testing default config..." )
        config = ResearchConfig()
        assert config.lead_model == "claude-opus-4-20250514"
        assert config.subagent_model == "claude-sonnet-4-20250514"
        print( "✓ Default config created" )

        # Test 2: get_max_subagents
        print( "Testing get_max_subagents..." )
        assert config.get_max_subagents( "simple" ) == 1
        assert config.get_max_subagents( "moderate" ) == 4
        assert config.get_max_subagents( "complex" ) == 10
        assert config.get_max_subagents( "unknown" ) == 4  # Falls back to moderate
        print( "✓ get_max_subagents works correctly" )

        # Test 3: Custom values
        print( "Testing custom config values..." )
        custom = ResearchConfig(
            lead_model="custom-model",
            max_subagents_complex=20,
            feedback_timeout_seconds=600
        )
        assert custom.lead_model == "custom-model"
        assert custom.max_subagents_complex == 20
        assert custom.feedback_timeout_seconds == 600
        print( "✓ Custom config values work" )

        print( "\n✓ ResearchConfig smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
