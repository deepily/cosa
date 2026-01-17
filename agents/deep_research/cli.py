#!/usr/bin/env python3
"""
Command-Line Interface for COSA Deep Research Agent.

Provides a voice-first CLI for running research queries. Voice I/O is the
PRIMARY interaction mode, with CLI text as automatic fallback.

Usage:
    python -m cosa.agents.deep_research.cli --query "Your research question"
    python -m cosa.agents.deep_research.cli --query "..." --budget 5.00
    python -m cosa.agents.deep_research.cli --query "..." --cli-mode  # Force text mode

Features:
- Voice-first interaction (TTS announcements, voice input)
- Automatic CLI fallback when voice unavailable
- Budget limits for cost control
- Debug output for development
- Cost reporting after completion
"""

import argparse
import asyncio
import os
import sys
import uuid
from typing import Optional

from .config import ResearchConfig
from .cost_tracker import CostTracker, BudgetExceededError
from .api_client import ResearchAPIClient, ANTHROPIC_AVAILABLE, ENV_VAR_NAME, KEY_FILE_NAME
from .orchestrator import ResearchOrchestratorAgent, OrchestratorState
from . import cosa_interface
from . import voice_io

# Import anthropic for RateLimitError handling
if ANTHROPIC_AVAILABLE:
    import anthropic


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="COSA Deep Research Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic research query
  python -m cosa.agents.deep_research.cli --query "Compare React and Vue"

  # With budget limit
  python -m cosa.agents.deep_research.cli --query "..." --budget 5.00

  # Debug mode
  python -m cosa.agents.deep_research.cli --query "..." --debug

  # Non-interactive (skip confirmations)
  python -m cosa.agents.deep_research.cli --query "..." --no-confirm
        """
    )

    parser.add_argument(
        "--query", "-q",
        type=str,
        required=True,
        help="The research query to investigate"
    )

    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Maximum budget in USD (default: unlimited)"
    )

    parser.add_argument(
        "--lead-model",
        type=str,
        default=None,
        help="Model for lead agent (default: claude-opus-4-20250514)"
    )

    parser.add_argument(
        "--subagent-model",
        type=str,
        default=None,
        help="Model for subagents (default: claude-sonnet-4-20250514)"
    )

    parser.add_argument(
        "--max-subagents",
        type=int,
        default=10,
        help="Maximum number of parallel subagents (default: 10)"
    )

    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompts (auto-approve)"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file for the research report"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making API calls"
    )

    parser.add_argument(
        "--cli-mode",
        action="store_true",
        help="Force CLI text mode (disable voice I/O)"
    )

    return parser.parse_args()


def check_prerequisites() -> bool:
    """
    Check that all prerequisites are met.

    Returns:
        bool: True if all prerequisites are met
    """
    # Check anthropic SDK
    if not ANTHROPIC_AVAILABLE:
        print( "ERROR: anthropic SDK not installed" )
        print( "  Install with: pip install anthropic" )
        return False

    # Check API key using firewalled pattern
    # Priority: Environment variable (prod/test) → Local file (dev)
    api_key = os.environ.get( ENV_VAR_NAME )
    key_source = "environment"

    if not api_key:
        # Try local file for development
        try:
            import cosa.utils.util as cu
            api_key = cu.get_api_key( KEY_FILE_NAME )
            key_source = "local file"
        except Exception:
            pass

    if not api_key:
        print( "ERROR: Anthropic API key not found" )
        print( f"  For testing/production: export {ENV_VAR_NAME}=your-key" )
        print( f"  For development: create src/conf/keys/{KEY_FILE_NAME}" )
        print( "" )
        print( "  NOTE: Do NOT use ANTHROPIC_API_KEY (reserved for Claude Code)" )
        return False

    print( f"✓ API key found ({key_source})" )
    return True


def print_header( query: str, config: ResearchConfig, budget: Optional[ float ] ):
    """Print CLI header with configuration."""
    print( "\n" + "=" * 70 )
    print( "  COSA Deep Research Agent" )
    print( "=" * 70 )
    print( f"\nQuery: {query}" )
    print( f"\nConfiguration:" )
    print( f"  Lead Model:     {config.lead_model}" )
    print( f"  Subagent Model: {config.subagent_model}" )
    print( f"  Max Subagents:  {config.max_subagents_complex}" )
    if budget:
        print( f"  Budget Limit:   ${budget:.2f}" )
    else:
        print( f"  Budget Limit:   None (unlimited)" )
    print( "" )


async def run_research(
    query: str,
    config: ResearchConfig,
    cost_tracker: CostTracker,
    no_confirm: bool = False,
    debug: bool = False,
    verbose: bool = False
) -> Optional[ str ]:
    """
    Run the research workflow with voice-first interaction.

    Args:
        query: The research query
        config: Research configuration
        cost_tracker: Cost tracker for usage
        no_confirm: Skip confirmation prompts
        debug: Enable debug output
        verbose: Enable verbose output

    Returns:
        str or None: The final research report, or None if cancelled
    """
    # Create API client
    api_client = ResearchAPIClient(
        config       = config,
        cost_tracker = cost_tracker,
        debug        = debug,
        verbose      = verbose,
    )

    # Announce I/O mode
    mode = voice_io.get_mode_description()
    if debug:
        print( f"  [I/O Mode: {mode}]" )

    # For now, we'll use a simplified flow that doesn't use the full orchestrator
    # This is a Phase 2 implementation that demonstrates the API client
    await voice_io.notify( "Step 1 of 4: Analyzing your query", priority="low" )

    # Import prompts
    from .prompts import (
        CLARIFICATION_SYSTEM_PROMPT,
        get_clarification_prompt,
        parse_clarification_response,
        PLANNING_SYSTEM_PROMPT,
        get_planning_prompt,
        parse_planning_response,
    )

    try:
        # Step 1: Clarification
        clarification_response = await api_client.call_with_json_output(
            system_prompt = CLARIFICATION_SYSTEM_PROMPT,
            user_message  = get_clarification_prompt( query ),
            call_type     = "clarification",
        )

        if clarification_response.get( "needs_clarification" ):
            question = clarification_response.get( "question", "Could you clarify?" )
            await voice_io.notify( f"Clarification needed: {question}", priority="medium" )

            if not no_confirm:
                clarification = await voice_io.get_input(
                    f"{question} Say your clarification, or say 'skip' to continue without clarifying"
                )
                if clarification and clarification.lower().strip() not in [ "skip", "none", "no", "" ]:
                    query = f"{query} - Clarification: {clarification}"

        understood = clarification_response.get( "understood_query", query )
        await voice_io.notify( f"Understood: {understood[:80]}{'...' if len( understood ) > 80 else ''}", priority="low" )

        # Step 2: Planning
        await voice_io.notify( "Step 2 of 4: Creating research plan", priority="low" )

        plan_response = await api_client.call_with_json_output(
            system_prompt = PLANNING_SYSTEM_PROMPT,
            user_message  = get_planning_prompt( query ),
            call_type     = "planning",
        )

        complexity = plan_response.get( "complexity", "moderate" )
        subqueries = plan_response.get( "subqueries", [] )
        rationale = plan_response.get( "rationale", "" )

        # Announce plan summary
        topics = [ sq.get( "topic", "Unknown" ) for sq in subqueries ]
        plan_summary = f"Found {len( subqueries )} research topics: {', '.join( topics[ :3 ] )}"
        if len( topics ) > 3:
            plan_summary += f" and {len( topics ) - 3} more"
        await voice_io.notify( plan_summary, priority="medium" )

        if not no_confirm:
            # Build plan summary for abstract - helps user understand what they're approving
            plan_abstract = "Research Plan:\n"
            for i, sq in enumerate( subqueries, 1 ):
                topic = sq.get( 'topic', 'Unknown' )
                objective = sq.get( 'objective', '' )
                plan_abstract += f"  {i}. {topic}"
                if objective:
                    plan_abstract += f"\n     → {objective[:80]}{'...' if len( objective ) > 80 else ''}"
                plan_abstract += "\n"
            plan_abstract += f"\nComplexity: {complexity}\n"
            plan_abstract += f"Estimated searches: {len( subqueries )}"

            proceed = await voice_io.ask_yes_no(
                "Would you like to proceed with this research plan?",
                default="yes",
                abstract=plan_abstract
            )
            if not proceed:
                await voice_io.notify( "Research cancelled.", priority="medium" )
                return None

        # Step 3: Research (simplified - single call for MVP)
        await voice_io.notify( "Step 3 of 4: Executing research", priority="low" )

        from .prompts import SUBAGENT_SYSTEM_PROMPT, get_subagent_prompt

        # Get rate limiter for progress reporting
        rate_limiter = api_client.get_rate_limiter()

        # Explain rate limiting to user before starting multi-topic research
        if len( subqueries ) > 1:
            await voice_io.notify(
                f"Researching {len( subqueries )} topics. "
                f"Note: Anthropic's web search API is limited to 30,000 tokens per minute, "
                f"but each search typically returns around 80,000 tokens. "
                f"This means we'll need brief pauses between searches to stay within limits.",
                priority="medium"
            )

            # Give time estimate
            estimated_time = rate_limiter.estimate_total_time( len( subqueries ) )
            if estimated_time > 60:
                await voice_io.notify(
                    f"Estimated total research time: {estimated_time / 60:.1f} minutes.",
                    priority="low"
                )

        # Research loop with partial result recovery on rate limit
        findings = []
        rate_limit_hit = False

        try:
            for i, sq in enumerate( subqueries ):
                topic = sq.get( "topic", "Unknown" )
                await voice_io.notify( f"Researching topic {i + 1} of {len( subqueries )}: {topic}", priority="low" )

                subagent_response = await api_client.call_subagent(
                    system_prompt  = SUBAGENT_SYSTEM_PROMPT.format( min_sources=3, max_sources=10 ),
                    user_message   = get_subagent_prompt(
                        topic         = sq.get( "topic", "" ),
                        objective     = sq.get( "objective", "" ),
                        output_format = sq.get( "output_format", "summary" ),
                    ),
                    subquery_index = i,
                    call_type      = "research",
                )

                # Parse findings
                content = subagent_response.content
                try:
                    import json
                    # Try to parse as JSON
                    if "```json" in content:
                        json_start = content.index( "```json" ) + 7
                        json_end = content.index( "```", json_start )
                        finding = json.loads( content[ json_start:json_end ].strip() )
                    else:
                        finding = json.loads( content )
                except ( json.JSONDecodeError, ValueError ):
                    # Use raw content if not JSON
                    finding = {
                        "findings"       : content,
                        "subquery_topic" : sq.get( "topic", "" ),
                        "confidence"     : 0.7,
                    }

                finding[ "subquery_topic" ] = sq.get( "topic", "" )
                findings.append( finding )

                # After each call, report progress with token count and next wait estimate
                if i < len( subqueries ) - 1:
                    tokens_used = subagent_response.input_tokens
                    next_wait = rate_limiter.get_estimated_wait_for_next_call()
                    remaining = len( subqueries ) - i - 1
                    await voice_io.notify(
                        f"Topic {i + 1}/{len( subqueries )} complete ({tokens_used:,} tokens). "
                        f"{remaining} remaining. Next search in ~{next_wait:.0f} seconds.",
                        priority="low"
                    )

        except anthropic.RateLimitError:
            # Rate limit hit - offer partial synthesis
            rate_limit_hit = True
            completed = len( findings )
            total = len( subqueries )

            await voice_io.notify(
                f"Rate limit hit after completing {completed} of {total} topics. "
                f"The API limits web searches to 30,000 tokens per minute, but each search returns ~80,000+ tokens.",
                priority="urgent"
            )

            if findings:
                proceed_partial = await voice_io.ask_yes_no(
                    f"Generate partial report from {completed} completed topics?",
                    default="yes"
                )

                if not proceed_partial:
                    await voice_io.notify(
                        "Research paused. You can retry later with fewer topics or wait 1-2 minutes.",
                        priority="medium"
                    )
                    return None
                # If proceed_partial is True, continue to synthesis below
            else:
                await voice_io.notify(
                    "No topics completed before rate limit. Try again in 1-2 minutes.",
                    priority="urgent"
                )
                return None

        if rate_limit_hit:
            await voice_io.notify( f"Proceeding with {len( findings )} partial research findings", priority="medium" )
        else:
            await voice_io.notify( f"Gathered {len( findings )} research findings", priority="low" )

        # Step 4: Synthesis
        await voice_io.notify( "Step 4 of 4: Synthesizing your report", priority="low" )

        from .prompts import SYNTHESIS_SYSTEM_PROMPT, get_synthesis_prompt

        synthesis_response = await api_client.call_lead_agent(
            system_prompt = SYNTHESIS_SYSTEM_PROMPT,
            user_message  = get_synthesis_prompt(
                query        = query,
                findings     = findings,
                plan_summary = rationale,
            ),
            call_type     = "synthesis",
            max_tokens    = 8192,
        )

        report = synthesis_response.content
        await voice_io.notify( "Research complete! Your report is ready.", priority="high" )

        return report

    except BudgetExceededError as e:
        await voice_io.notify( f"Budget exceeded: {e}", priority="urgent" )
        return None

    finally:
        await api_client.close()


def main():
    """Main entry point."""
    args = parse_args()

    # Configure voice I/O mode
    if args.cli_mode:
        voice_io.set_cli_mode( True )
        print( "  [CLI mode enabled - voice I/O disabled]" )

    # Generate semantic topic from query using existing Gister with custom prompt
    from cosa.memory.gister import Gister
    gister = Gister( debug=args.debug )
    semantic_topic = gister.get_gist( args.query, prompt_key="prompt template for deep research session id generation" )

    # Post-process: ensure lowercase and hyphenated (defensive - expects 3 words)
    semantic_topic = semantic_topic.lower().strip()
    if " " in semantic_topic:
        semantic_topic = semantic_topic.replace( " ", "-" )
    # Validate 3-word format (should have exactly 2 hyphens)
    if not semantic_topic or semantic_topic.count( "-" ) != 2:
        semantic_topic = "general-research-query"

    if args.debug:
        print( f"  [Semantic topic: {semantic_topic}]" )

    # Update cosa_interface sender_id BEFORE any notifications
    cosa_interface.SENDER_ID = cosa_interface._get_sender_id() + f"#{semantic_topic}"

    # Check prerequisites
    if not args.dry_run and not check_prerequisites():
        sys.exit( 1 )

    # Build configuration
    config = ResearchConfig()
    if args.lead_model:
        config.lead_model = args.lead_model
    if args.subagent_model:
        config.subagent_model = args.subagent_model
    if args.max_subagents:
        config.max_subagents_complex = args.max_subagents

    # Create cost tracker
    session_id = f"cli-{semantic_topic}-{uuid.uuid4().hex[:4]}"
    cost_tracker = CostTracker(
        session_id       = session_id,
        budget_limit_usd = args.budget,
        debug            = args.debug,
    )

    # Print header
    print_header( args.query, config, args.budget )

    # Dry run mode
    if args.dry_run:
        print( "DRY RUN MODE - No API calls will be made" )
        print( f"\nSemantic topic extracted: {semantic_topic}" )
        print( f"Session ID would be: {session_id}" )
        print( f"Notification sender: {cosa_interface.SENDER_ID}" )
        print( "\nWould execute:" )
        print( "  1. Query clarification analysis" )
        print( "  2. Research plan generation" )
        print( "  3. Parallel subagent research" )
        print( "  4. Report synthesis" )
        sys.exit( 0 )

    # Run research
    try:
        report = asyncio.run( run_research(
            query        = args.query,
            config       = config,
            cost_tracker = cost_tracker,
            no_confirm   = args.no_confirm,
            debug        = args.debug,
            verbose      = args.verbose,
        ) )

        if report:
            # Print report
            print( "\n" + "=" * 70 )
            print( "  RESEARCH REPORT" )
            print( "=" * 70 )
            print( report )

            # Save to file if requested
            if args.output:
                with open( args.output, "w" ) as f:
                    f.write( report )
                print( f"\n  Report saved to: {args.output}" )

        # Print cost summary
        print( "\n" + "=" * 70 )
        print( "  COST SUMMARY" )
        print( "=" * 70 )
        print( cost_tracker.get_cost_report() )

    except KeyboardInterrupt:
        print( "\n\nResearch interrupted by user." )
        print( "\nPartial cost summary:" )
        print( cost_tracker.get_cost_report() )
        sys.exit( 1 )

    except anthropic.RateLimitError:
        # User-friendly rate limit error message
        print( "\n" + "=" * 70 )
        print( "  RATE LIMIT REACHED" )
        print( "=" * 70 )
        print( "\nThe Anthropic API rate limit (30,000 tokens/minute) was exceeded." )
        print( "\nThis can happen when:" )
        print( "  - Web searches return large amounts of content (80,000+ tokens each)" )
        print( "  - Multiple searches run in quick succession" )
        print( "\nSuggested next steps:" )
        print( "  1. Wait 1-2 minutes and try again" )
        print( "  2. Use --max-subagents 2 to limit parallel research" )
        print( "  3. Use a simpler/narrower query" )
        print( "\nPartial cost summary:" )
        print( cost_tracker.get_cost_report() )
        sys.exit( 2 )  # Exit code 2 for rate limit (different from general error)

    except Exception as e:
        print( f"\nError: {e}" )
        if args.debug:
            import traceback
            traceback.print_exc()
        print( "\nPartial cost summary:" )
        print( cost_tracker.get_cost_report() )
        sys.exit( 1 )


if __name__ == "__main__":
    main()
