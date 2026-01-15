#!/usr/bin/env python3
"""
Research Planning Prompt Template for COSA Deep Research Agent.

This prompt helps the lead agent create a research plan by:
- Assessing query complexity (simple/moderate/complex)
- Decomposing into focused subqueries
- Determining appropriate subagent count
- Establishing research strategy

Based on patterns from:
- Anthropic Cookbook: Multi-agent coordination
- GPT Researcher: Planner/executor decomposition
- Anthropic Blog: Scaling heuristics
"""

from typing import Optional


PLANNING_SYSTEM_PROMPT = """You are a research planning specialist. Your task is to create an optimal research plan by decomposing a query into focused, parallelizable subqueries.

## Your Planning Process

1. **Assess Complexity**:
   - **Simple**: Straightforward fact-finding, single perspective (1 subquery)
   - **Moderate**: Comparisons, multi-faceted topics, some analysis (2-4 subqueries)
   - **Complex**: Deep analysis, multiple perspectives, synthesis required (5-10 subqueries)

2. **Decompose into Subqueries**:
   - Each subquery should be independently researchable
   - Subqueries should be focused and specific
   - Avoid overlap between subqueries
   - Order by priority (1 = highest)

3. **Design for Parallelism**:
   - Most subqueries can run in parallel
   - Use `depends_on` only when information from one subquery is needed for another
   - Minimize sequential dependencies

## Subquery Design Principles

- **Focused**: Each subquery addresses ONE aspect of the topic
- **Actionable**: Clear objective that can be achieved with web search
- **Measurable**: Specific output format (list, summary, comparison, etc.)
- **Independent**: Can be researched without context from other subqueries (unless dependency specified)

## Output Format

You must respond with a JSON object:

```json
{
    "complexity": "simple" | "moderate" | "complex",
    "subqueries": [
        {
            "topic": "Specific topic to research",
            "objective": "What information to gather - be specific",
            "output_format": "Expected structure (e.g., 'list of 5 companies', 'comparison table', 'factual summary')",
            "tools_to_use": ["web_search", "web_fetch"],
            "priority": 1-5,
            "depends_on": null or [indices of dependencies]
        }
    ],
    "estimated_subagents": 1-10,
    "rationale": "Brief explanation of the research approach",
    "estimated_duration_minutes": 5-30
}
```

## Examples

**Query**: "What are the main differences between React and Vue?"
**Response**:
```json
{
    "complexity": "moderate",
    "subqueries": [
        {
            "topic": "React core concepts and architecture",
            "objective": "Summarize React's key features, virtual DOM, component model, and design philosophy",
            "output_format": "structured summary with bullet points",
            "tools_to_use": ["web_search"],
            "priority": 1,
            "depends_on": null
        },
        {
            "topic": "Vue core concepts and architecture",
            "objective": "Summarize Vue's key features, reactivity system, component model, and design philosophy",
            "output_format": "structured summary with bullet points",
            "tools_to_use": ["web_search"],
            "priority": 1,
            "depends_on": null
        },
        {
            "topic": "React vs Vue performance benchmarks",
            "objective": "Find recent performance comparisons and benchmark data",
            "output_format": "comparison table with metrics",
            "tools_to_use": ["web_search"],
            "priority": 2,
            "depends_on": null
        },
        {
            "topic": "React vs Vue ecosystem and community",
            "objective": "Compare ecosystem size, community activity, job market, and tooling",
            "output_format": "comparison summary",
            "tools_to_use": ["web_search"],
            "priority": 2,
            "depends_on": null
        }
    ],
    "estimated_subagents": 4,
    "rationale": "Parallel comparison approach: gather information about each framework independently, then compare specific aspects. All subqueries can run in parallel.",
    "estimated_duration_minutes": 10
}
```

**Query**: "Summarize the latest news about Tesla"
**Response**:
```json
{
    "complexity": "simple",
    "subqueries": [
        {
            "topic": "Recent Tesla news and developments",
            "objective": "Find the most recent and significant news about Tesla from the past week",
            "output_format": "chronological list of 5-7 key news items with brief summaries",
            "tools_to_use": ["web_search"],
            "priority": 1,
            "depends_on": null
        }
    ],
    "estimated_subagents": 1,
    "rationale": "Simple fact-finding query that can be handled by a single focused search for recent news.",
    "estimated_duration_minutes": 5
}
```"""


def get_planning_prompt(
    query: str,
    clarified_query: Optional[ str ] = None,
    max_subagents: int = 10
) -> str:
    """
    Generate the user message for research planning.

    Args:
        query: The original research query
        clarified_query: The clarified version (if clarification was done)
        max_subagents: Maximum number of subagents to suggest

    Returns:
        str: Formatted user message for the API call
    """
    effective_query = clarified_query if clarified_query else query

    message = f"Create a research plan for this query:\n\n\"{effective_query}\""

    if clarified_query and clarified_query != query:
        message += f"\n\n(Original query: \"{query}\")"

    message += f"\n\nConstraints:"
    message += f"\n- Maximum subagents: {max_subagents}"
    message += f"\n- Prefer fewer, more focused subqueries over many shallow ones"
    message += f"\n- Prioritize parallelism when possible"

    message += "\n\nRespond with a JSON object following the format specified in your instructions."

    return message


def parse_planning_response( response_text: str ) -> dict:
    """
    Parse the planning response JSON.

    Args:
        response_text: Raw response from the API

    Returns:
        dict: Parsed research plan

    Raises:
        ValueError: If response cannot be parsed as JSON
    """
    import json

    text = response_text.strip()

    # Handle markdown code blocks
    if text.startswith( "```json" ):
        text = text[ 7: ]
    if text.startswith( "```" ):
        text = text[ 3: ]
    if text.endswith( "```" ):
        text = text[ :-3 ]

    try:
        return json.loads( text.strip() )
    except json.JSONDecodeError as e:
        raise ValueError( f"Could not parse planning response as JSON: {e}" )


def quick_smoke_test():
    """Quick smoke test for planning prompt."""
    import cosa.utils.util as cu

    cu.print_banner( "Planning Prompt Smoke Test", prepend_nl=True )

    try:
        # Test 1: System prompt exists
        print( "Testing system prompt..." )
        assert len( PLANNING_SYSTEM_PROMPT ) > 1000
        assert "complexity" in PLANNING_SYSTEM_PROMPT
        assert "subqueries" in PLANNING_SYSTEM_PROMPT
        print( f"✓ System prompt exists ({len( PLANNING_SYSTEM_PROMPT )} chars)" )

        # Test 2: User prompt generation
        print( "Testing get_planning_prompt..." )
        prompt = get_planning_prompt( "Compare Python and JavaScript" )
        assert "Compare Python and JavaScript" in prompt
        assert "Maximum subagents" in prompt
        print( f"✓ User prompt generated ({len( prompt )} chars)" )

        # Test 3: With clarified query
        print( "Testing prompt with clarification..." )
        prompt = get_planning_prompt(
            query="Tell me about AI",
            clarified_query="Explain the current state of generative AI in 2025"
        )
        assert "generative AI" in prompt
        assert "Original query" in prompt
        print( "✓ Clarified query included" )

        # Test 4: Parse valid response
        print( "Testing parse_planning_response..." )
        valid_json = '''{
            "complexity": "moderate",
            "subqueries": [
                {"topic": "Topic 1", "objective": "Obj 1", "output_format": "summary", "priority": 1}
            ],
            "estimated_subagents": 2,
            "rationale": "Test rationale"
        }'''
        result = parse_planning_response( valid_json )
        assert result[ "complexity" ] == "moderate"
        assert len( result[ "subqueries" ] ) == 1
        print( "✓ Parsed valid planning response" )

        print( "\n✓ Planning prompt smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
