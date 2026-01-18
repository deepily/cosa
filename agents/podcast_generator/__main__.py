#!/usr/bin/env python3
"""
Entry point for COSA Podcast Generator Agent.

Run with: python -m cosa.agents.podcast_generator

Usage:
    # Generate podcast script from research document
    python -m cosa.agents.podcast_generator --research path/to/research.md

    # With custom output
    python -m cosa.agents.podcast_generator --research research.md --output my-podcast.md

    # Run all module smoke tests
    python -m cosa.agents.podcast_generator --smoke-test

    # Dry run (show what would happen)
    python -m cosa.agents.podcast_generator --research research.md --dry-run
"""

import argparse
import asyncio
import sys


def run_all_smoke_tests():
    """Run smoke tests for all podcast generator modules."""
    import cosa.utils.util as cu

    cu.print_banner( "Podcast Generator - Full Smoke Test Suite", prepend_nl=True )

    modules = [
        ( "config", "cosa.agents.podcast_generator.config" ),
        ( "state", "cosa.agents.podcast_generator.state" ),
        ( "prompts.script_generation", "cosa.agents.podcast_generator.prompts.script_generation" ),
        ( "prompts.personality", "cosa.agents.podcast_generator.prompts.personality" ),
        ( "cosa_interface", "cosa.agents.podcast_generator.cosa_interface" ),
        ( "api_client", "cosa.agents.podcast_generator.api_client" ),
        ( "orchestrator", "cosa.agents.podcast_generator.orchestrator" ),
    ]

    results = []

    for name, module_path in modules:
        try:
            print( f"\n{'='*60}" )
            print( f"Running: {name}" )
            print( '='*60 )

            module = __import__( module_path, fromlist=[ "quick_smoke_test" ] )
            module.quick_smoke_test()
            results.append( ( name, "PASSED", None ) )

        except Exception as e:
            results.append( ( name, "FAILED", str( e ) ) )

    # Summary table
    print( f"\n{'='*60}" )
    print( "SMOKE TEST SUMMARY" )
    print( '='*60 )

    passed = sum( 1 for _, status, _ in results if status == "PASSED" )
    failed = sum( 1 for _, status, _ in results if status == "FAILED" )

    for name, status, error in results:
        status_icon = "✓" if status == "PASSED" else "✗"
        print( f"  {status_icon} {name}: {status}" )
        if error:
            print( f"      Error: {error[:60]}" )

    print( f"\nTotal: {passed} passed, {failed} failed out of {len( results )} modules" )

    return failed == 0


async def run_podcast_generation( args ):
    """Run the podcast generation workflow."""
    from .orchestrator import PodcastOrchestratorAgent
    from .config import PodcastConfig
    import cosa.utils.util as cu

    cu.print_banner( "COSA Podcast Generator", prepend_nl=True )

    # Validate research document exists
    import os
    research_path = args.research

    if not research_path.startswith( "/" ):
        research_path = cu.get_project_root() + "/" + research_path

    if not os.path.exists( research_path ):
        print( f"Error: Research document not found: {research_path}" )
        return 1

    print( f"Research document: {research_path}" )
    print( f"User ID: {args.user_id}" )

    if args.dry_run:
        print( "\n[DRY RUN MODE - No API calls will be made]" )
        print( "\nWould execute:" )
        print( "  1. Load research document" )
        print( "  2. Analyze content for key topics" )
        print( "  3. Generate podcast script" )
        print( "  4. Wait for script review" )
        print( "  5. Save script to file" )
        return 0

    # Create config
    config = PodcastConfig()

    # Create orchestrator
    agent = PodcastOrchestratorAgent(
        research_doc_path = research_path,
        user_id           = args.user_id,
        config            = config,
        debug             = args.debug,
        verbose           = args.verbose,
    )

    print( f"Podcast ID: {agent.podcast_id}" )
    print( "" )

    # Run the workflow
    try:
        script = await agent.do_all_async()

        if script:
            print( f"\n✓ Podcast script generated successfully!" )
            print( f"  Title: {script.title}" )
            print( f"  Segments: {script.get_segment_count()}" )
            print( f"  Duration: ~{script.estimated_duration_minutes:.1f} minutes" )

            state = agent.get_state()
            print( f"  Cost: ${agent.api_client.cost_estimate.estimated_cost_usd:.4f}" )
            return 0
        else:
            print( "\n⚠ Podcast generation was cancelled." )
            return 1

    except KeyboardInterrupt:
        print( "\n\n⚠ Interrupted by user." )
        return 1

    except Exception as e:
        print( f"\n✗ Podcast generation failed: {e}" )
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description = "COSA Podcast Generator Agent - Transform research into podcasts",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """
Examples:
  # Generate podcast from research document
  python -m cosa.agents.podcast_generator --research io/deep-research/output.md

  # Run all smoke tests
  python -m cosa.agents.podcast_generator --smoke-test

  # Dry run to see what would happen
  python -m cosa.agents.podcast_generator --research research.md --dry-run
"""
    )

    parser.add_argument(
        "--research", "-r",
        help = "Path to Deep Research markdown document"
    )

    parser.add_argument(
        "--user-id", "-u",
        default = "user@example.com",
        help = "User ID for output directory (default: user@example.com)"
    )

    parser.add_argument(
        "--dry-run",
        action = "store_true",
        help = "Show what would happen without making API calls"
    )

    parser.add_argument(
        "--smoke-test",
        action = "store_true",
        help = "Run all module smoke tests"
    )

    parser.add_argument(
        "--debug", "-d",
        action = "store_true",
        help = "Enable debug output"
    )

    parser.add_argument(
        "--verbose", "-v",
        action = "store_true",
        help = "Enable verbose output"
    )

    args = parser.parse_args()

    # Run smoke tests if requested
    if args.smoke_test:
        success = run_all_smoke_tests()
        sys.exit( 0 if success else 1 )

    # Require research document for generation
    if not args.research:
        parser.print_help()
        print( "\nError: --research argument is required for podcast generation" )
        print( "       Use --smoke-test to run tests instead" )
        sys.exit( 1 )

    # Run podcast generation
    exit_code = asyncio.run( run_podcast_generation( args ) )
    sys.exit( exit_code )


if __name__ == "__main__":
    main()
