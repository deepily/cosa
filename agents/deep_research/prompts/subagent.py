#!/usr/bin/env python3
"""
Research Subagent Prompt Template for COSA Deep Research Agent.

This prompt guides research subagents that execute focused web searches
and gather information for specific subqueries. Subagents:
- Execute targeted web searches
- Evaluate source quality
- Compress findings before returning
- Identify information gaps

Based on patterns from:
- Anthropic Cookbook: Research subagent execution
- GPT Researcher: Wide-to-narrow search strategy
- Context compression techniques from open research
"""

from typing import Optional, List


SUBAGENT_SYSTEM_PROMPT = """You are a research subagent specializing in focused information gathering. Your task is to thoroughly research a specific topic and return compressed, high-quality findings.

## Your Research Process

1. **Search Strategically**:
   - Start with broad searches to understand the landscape
   - Follow up with specific searches for detailed information
   - Use multiple search queries to triangulate information
   - Prioritize recent, authoritative sources

2. **Evaluate Sources**:
   - **Primary sources**: Official documentation, academic papers, original research
   - **Secondary sources**: Reputable news, industry publications, expert blogs
   - **Aggregators**: Wikipedia, Stack Overflow (good for overview, verify elsewhere)
   - Note source quality in your findings

3. **Gather Comprehensively**:
   - Aim for {min_sources} to {max_sources} quality sources
   - Look for consensus across sources
   - Note disagreements or contradictions
   - Capture specific data points, not just opinions

4. **Compress Findings**:
   - Extract only relevant information
   - Remove redundancy
   - Preserve key facts and data points
   - Keep source attribution

## Output Format

You must respond with a JSON object:

```json
{{
    "findings": "Compressed, relevant information gathered from research",
    "sources": [
        {{
            "url": "https://...",
            "title": "Source title",
            "snippet": "Relevant excerpt or summary",
            "relevance_score": 0.0-1.0,
            "source_quality": "primary" | "secondary" | "aggregator" | "unknown",
            "access_date": "2025-01-14"
        }}
    ],
    "confidence": 0.0-1.0,
    "gaps": ["Information that could not be found or verified"],
    "quality_notes": "Notes on source quality issues or limitations"
}}
```

## Research Guidelines

- **Be thorough but focused**: Stay on topic, but explore thoroughly within scope
- **Prefer recency**: For technology topics, prioritize sources from the last 1-2 years
- **Cross-reference**: Don't rely on a single source for important claims
- **Acknowledge uncertainty**: If information is conflicting or uncertain, note it
- **Compress intelligently**: The lead agent doesn't need every detail, just key findings

## Example

**Subquery**: Research React's virtual DOM implementation and performance characteristics

**Response**:
```json
{{
    "findings": "React uses a Virtual DOM (VDOM) - a lightweight JavaScript representation of the actual DOM. When state changes, React creates a new VDOM tree, diffs it against the previous one (reconciliation), and batch-updates only changed elements in the real DOM. This approach minimizes expensive DOM operations. React 18+ introduced concurrent rendering and automatic batching for better performance. Fiber architecture enables interruptible rendering. Benchmarks show React performs well for most applications, though can be slower than Svelte or SolidJS for fine-grained updates. Key optimizations: memo(), useMemo(), useCallback(), React.lazy() for code splitting.",
    "sources": [
        {{
            "url": "https://react.dev/learn/preserving-and-resetting-state",
            "title": "React Documentation - Preserving and Resetting State",
            "snippet": "Official documentation on React's reconciliation algorithm",
            "relevance_score": 0.95,
            "source_quality": "primary",
            "access_date": "2025-01-14"
        }},
        {{
            "url": "https://blog.isquaredsoftware.com/2020/05/blogged-answers-a-mostly-complete-guide-to-react-rendering-behavior/",
            "title": "A Mostly Complete Guide to React Rendering Behavior",
            "snippet": "Comprehensive analysis of React's rendering and optimization techniques",
            "relevance_score": 0.90,
            "source_quality": "secondary",
            "access_date": "2025-01-14"
        }}
    ],
    "confidence": 0.9,
    "gaps": ["Specific benchmark numbers vary by test methodology", "React 19 changes not fully documented yet"],
    "quality_notes": "Good coverage from official docs and respected technical blogs. Benchmark comparisons are contentious - included general consensus rather than specific numbers."
}}
```"""


def get_subagent_prompt(
    topic: str,
    objective: str,
    output_format: str,
    min_sources: int = 3,
    max_sources: int = 10,
    priority: int = 1,
    context: Optional[ str ] = None
) -> str:
    """
    Generate the user message for subagent research.

    Args:
        topic: The specific topic to research
        objective: What information to gather
        output_format: Expected output structure
        min_sources: Minimum sources to find
        max_sources: Maximum sources to include
        priority: Priority level (1=highest)
        context: Optional context from lead agent

    Returns:
        str: Formatted user message for the API call
    """
    message = f"""Research the following topic:

**Topic**: {topic}

**Objective**: {objective}

**Expected Output Format**: {output_format}

**Source Requirements**:
- Minimum sources: {min_sources}
- Maximum sources: {max_sources}
- Prioritize quality over quantity"""

    if context:
        message += f"\n\n**Additional Context**: {context}"

    message += """

Use web search to gather information. Be thorough but focused on the specific objective.

Respond with a JSON object following the format specified in your instructions."""

    return message


def get_system_prompt_with_params(
    min_sources: int = 3,
    max_sources: int = 10
) -> str:
    """
    Get the system prompt with source parameters filled in.

    Args:
        min_sources: Minimum sources to find
        max_sources: Maximum sources to include

    Returns:
        str: System prompt with parameters
    """
    return SUBAGENT_SYSTEM_PROMPT.format(
        min_sources=min_sources,
        max_sources=max_sources
    )


def parse_subagent_response( response_text: str ) -> dict:
    """
    Parse the subagent response JSON.

    Args:
        response_text: Raw response from the API

    Returns:
        dict: Parsed subagent findings

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
        raise ValueError( f"Could not parse subagent response as JSON: {e}" )


def quick_smoke_test():
    """Quick smoke test for subagent prompt."""
    import cosa.utils.util as cu

    cu.print_banner( "Subagent Prompt Smoke Test", prepend_nl=True )

    try:
        # Test 1: System prompt exists
        print( "Testing system prompt..." )
        assert len( SUBAGENT_SYSTEM_PROMPT ) > 1000
        assert "findings" in SUBAGENT_SYSTEM_PROMPT
        assert "sources" in SUBAGENT_SYSTEM_PROMPT
        assert "confidence" in SUBAGENT_SYSTEM_PROMPT
        print( f"✓ System prompt exists ({len( SUBAGENT_SYSTEM_PROMPT )} chars)" )

        # Test 2: Parameterized system prompt
        print( "Testing get_system_prompt_with_params..." )
        prompt = get_system_prompt_with_params( min_sources=5, max_sources=15 )
        assert "5" in prompt
        assert "15" in prompt
        print( "✓ Parameterized prompt generated" )

        # Test 3: User prompt generation
        print( "Testing get_subagent_prompt..." )
        prompt = get_subagent_prompt(
            topic="React performance optimization",
            objective="Find best practices for optimizing React apps",
            output_format="bullet list with explanations"
        )
        assert "React performance" in prompt
        assert "best practices" in prompt
        print( f"✓ User prompt generated ({len( prompt )} chars)" )

        # Test 4: With context
        print( "Testing prompt with context..." )
        prompt = get_subagent_prompt(
            topic="Vue 3 Composition API",
            objective="Document key features",
            output_format="feature comparison",
            context="User is comparing with React Hooks"
        )
        assert "React Hooks" in prompt
        print( "✓ Context included in prompt" )

        # Test 5: Parse valid response
        print( "Testing parse_subagent_response..." )
        valid_json = '''{
            "findings": "Test findings with important data",
            "sources": [{"url": "https://test.com", "title": "Test", "relevance_score": 0.9}],
            "confidence": 0.85,
            "gaps": ["Missing some info"],
            "quality_notes": "Good sources overall"
        }'''
        result = parse_subagent_response( valid_json )
        assert result[ "confidence" ] == 0.85
        assert len( result[ "sources" ] ) == 1
        print( "✓ Parsed valid subagent response" )

        print( "\n✓ Subagent prompt smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
