#!/usr/bin/env python3
"""
Presentation Generator Agent — CLI entry point.

Runs smoke tests across all modules when invoked with --smoke-test.

Usage:
    python -m cosa.agents.presentation_generator --smoke-test
"""

import sys


def run_smoke_tests():
    """Run smoke tests for all Presentation Generator modules."""

    modules = [
        ( "config",         "cosa.agents.presentation_generator.config" ),
        ( "state",          "cosa.agents.presentation_generator.state" ),
        ( "cosa_interface", "cosa.agents.presentation_generator.cosa_interface" ),
        ( "voice_io",       "cosa.agents.presentation_generator.voice_io" ),
        ( "orchestrator",   "cosa.agents.presentation_generator.orchestrator" ),
        ( "job",            "cosa.agents.presentation_generator.job" ),
    ]

    failed = []
    for name, module_path in modules:
        try:
            mod = __import__( module_path, fromlist=[ "quick_smoke_test" ] )
            mod.quick_smoke_test()
        except Exception as e:
            print( f"\nFAILED: {name} — {e}" )
            failed.append( name )

    print( "\n" + "=" * 60 )
    if failed:
        print( f"SMOKE TESTS: {len( failed )} FAILED — {', '.join( failed )}" )
        sys.exit( 1 )
    else:
        print( f"SMOKE TESTS: All {len( modules )} modules passed" )


if __name__ == "__main__":

    if "--smoke-test" in sys.argv:
        run_smoke_tests()
    else:
        print( "Usage: python -m cosa.agents.presentation_generator --smoke-test" )
        print( "\nPresentation Generator Agent v0.1.0" )
        print( "Phase 1: Foundation (dry-run only)" )
