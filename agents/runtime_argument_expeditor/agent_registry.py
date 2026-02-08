#!/usr/bin/env python3
"""
Agent Registry for Runtime Argument Expeditor.

Maps agentic routing commands to their CLI modules, required arguments,
argument name mappings (LORA -> CLI), and fallback questions for missing args.

Also provides CLI --help capture with per-process-lifetime caching.
"""

import json
import sys
import subprocess
from typing import Optional


# ============================================================================
# Agent Registry
# ============================================================================

AGENTIC_AGENTS = {
    "agent router go to deep research" : {
        "cli_module"         : "cosa.agents.deep_research.cli",
        "job_class_path"     : "cosa.agents.deep_research.job.DeepResearchJob",
        "required_user_args" : [ "query" ],
        "system_provided"    : [ "user_email", "session_id", "user_id", "no_confirm" ],
        "arg_mapping"        : {
            "topic"            : "query",
            "query"            : "query",
            "budget"           : "budget",
            "audience"         : "audience",
            "audience_context" : "audience_context",
        },
        "fallback_questions" : {
            "query"            : "What topic would you like me to research?",
            "budget"           : "Would you like to set a budget limit in dollars? Say a dollar amount, or 'no limit'.",
            "audience"         : "Who is the target audience? Options: beginner, intermediate, expert, or academic.",
            "audience_context" : "Any additional context about the audience? Say 'none' to skip.",
        },
    },
    "agent router go to podcast generator" : {
        "cli_module"         : "cosa.agents.podcast_generator",
        "job_class_path"     : "cosa.agents.podcast_generator.job.PodcastGeneratorJob",
        "required_user_args" : [ "research" ],
        "system_provided"    : [ "user_id", "user_email", "session_id" ],
        "arg_mapping"        : {
            "research"         : "research",
            "document_path"    : "research",
            "topic"            : "research",
            "audience"         : "audience",
            "audience_context" : "audience_context",
        },
        "fallback_questions" : {
            "research"         : "Which research document should I use for the podcast? Describe it or say the filename.",
            "languages"        : "What languages for the podcast? Say 'English' or 'English and Spanish', etc.",
            "audience"         : "Who is the target audience? Options: beginner, intermediate, expert, or academic.",
            "audience_context" : "Any additional context about the audience? Say 'none' to skip.",
        },
        "special_handlers"   : {
            "research" : "fuzzy_file_match",
        },
    },
    "agent router go to research to podcast" : {
        "cli_module"         : "cosa.agents.deep_research_to_podcast",
        "job_class_path"     : "cosa.agents.deep_research_to_podcast.job.DeepResearchToPodcastJob",
        "required_user_args" : [ "query" ],
        "system_provided"    : [ "user_email", "session_id", "user_id", "no_confirm" ],
        "arg_mapping"        : {
            "topic"            : "query",
            "query"            : "query",
            "budget"           : "budget",
            "audience"         : "audience",
            "audience_context" : "audience_context",
        },
        "fallback_questions" : {
            "query"            : "What topic would you like me to research and turn into a podcast?",
            "budget"           : "Would you like to set a budget limit for the research phase?",
            "audience"         : "Who is the target audience? Options: beginner, intermediate, expert, or academic.",
            "audience_context" : "Any additional context about the audience? Say 'none' to skip.",
            "languages"        : "What languages for the podcast? Say 'English' or 'English and Spanish', etc.",
        },
    },
}


# ============================================================================
# CLI Help Capture (process-lifetime cache)
# ============================================================================

_help_cache = {}


def get_cli_help( command_key ):
    """
    Capture --help output for an agentic agent's CLI module.

    Requires:
        - command_key is a key in AGENTIC_AGENTS

    Ensures:
        - Returns help text string on success
        - Returns None if command_key not found or subprocess fails
        - Results are cached per-process-lifetime in _help_cache

    Args:
        command_key: Key from AGENTIC_AGENTS (e.g., "agent router go to deep research")

    Returns:
        str or None: CLI help text or None on failure
    """
    if command_key in _help_cache:
        return _help_cache[ command_key ]

    agent_entry = AGENTIC_AGENTS.get( command_key )
    if not agent_entry:
        return None

    cli_module = agent_entry[ "cli_module" ]

    try:
        result = subprocess.run(
            [ sys.executable, "-m", cli_module, "--help" ],
            capture_output = True,
            text           = True,
            timeout        = 10
        )
        help_text = result.stdout or result.stderr or ""
        _help_cache[ command_key ] = help_text
        return help_text

    except ( subprocess.TimeoutExpired, FileNotFoundError, OSError ) as e:
        print( f"Warning: Failed to capture --help for {cli_module}: {e}" )
        _help_cache[ command_key ] = None
        return None


# ============================================================================
# User-Visible Args Capture (process-lifetime cache)
# ============================================================================

_user_visible_cache = {}


def get_user_visible_args( command_key ):
    """
    Get list of user-visible args for an agent by calling its CLI with --user-visible-args.

    Requires:
        - command_key exists in AGENTIC_AGENTS

    Ensures:
        - Returns list of arg name strings, or None on failure
        - Results are cached for process lifetime

    Args:
        command_key: Key from AGENTIC_AGENTS (e.g., "agent router go to deep research")

    Returns:
        list or None: List of user-visible arg names, or None on failure
    """
    if command_key in _user_visible_cache:
        return _user_visible_cache[ command_key ]

    entry = AGENTIC_AGENTS.get( command_key )
    if not entry:
        return None

    cli_module = entry[ "cli_module" ]

    try:
        result = subprocess.run(
            [ sys.executable, "-m", cli_module, "--user-visible-args" ],
            capture_output = True,
            text           = True,
            timeout        = 10
        )
        if result.returncode == 0 and result.stdout.strip():
            args_list = json.loads( result.stdout.strip() )
            _user_visible_cache[ command_key ] = args_list
            return args_list

    except ( subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError ):
        pass

    return None


# ============================================================================
# Smoke Test
# ============================================================================

def quick_smoke_test():
    """
    Quick smoke test for agent_registry module.

    Tests registry structure, key lookups, and help capture.
    """
    import cosa.utils.util as cu
    cu.print_banner( "Agent Registry Smoke Test", prepend_nl=True )

    tests_passed = 0
    tests_failed = 0

    # Test 1: Registry structure
    print( "\n1. Testing registry structure..." )
    try:
        assert len( AGENTIC_AGENTS ) == 3, f"Expected 3 agents, got {len( AGENTIC_AGENTS )}"
        for key, entry in AGENTIC_AGENTS.items():
            assert "cli_module" in entry, f"Missing cli_module in {key}"
            assert "required_user_args" in entry, f"Missing required_user_args in {key}"
            assert "system_provided" in entry, f"Missing system_provided in {key}"
            assert "arg_mapping" in entry, f"Missing arg_mapping in {key}"
            assert "fallback_questions" in entry, f"Missing fallback_questions in {key}"
            print( f"   ✓ {key}: structure valid" )
        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 2: Key lookups
    print( "\n2. Testing key lookups..." )
    try:
        dr = AGENTIC_AGENTS.get( "agent router go to deep research" )
        assert dr is not None
        assert dr[ "required_user_args" ] == [ "query" ]
        print( "   ✓ Deep research lookup works" )

        pg = AGENTIC_AGENTS.get( "agent router go to podcast generator" )
        assert pg is not None
        assert pg[ "required_user_args" ] == [ "research" ]
        assert "special_handlers" in pg
        print( "   ✓ Podcast generator lookup works (has special_handlers)" )

        rp = AGENTIC_AGENTS.get( "agent router go to research to podcast" )
        assert rp is not None
        assert rp[ "required_user_args" ] == [ "query" ]
        print( "   ✓ Research to podcast lookup works" )

        missing = AGENTIC_AGENTS.get( "nonexistent command" )
        assert missing is None
        print( "   ✓ Missing key returns None" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 3: Help capture
    print( "\n3. Testing CLI help capture..." )
    try:
        help_text = get_cli_help( "agent router go to deep research" )
        if help_text:
            print( f"   ✓ Help captured ({len( help_text )} chars)" )
        else:
            print( "   ⚠ Help returned None (CLI module may not be available)" )

        # Test cache hit
        help_text_2 = get_cli_help( "agent router go to deep research" )
        assert help_text_2 == help_text, "Cache miss on second call"
        print( "   ✓ Cache hit works" )

        # Test missing key
        help_none = get_cli_help( "nonexistent" )
        assert help_none is None
        print( "   ✓ Missing key returns None" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Summary
    print( f"\n{'=' * 60}" )
    print( f"Agent Registry Smoke Test: {tests_passed} passed, {tests_failed} failed" )
    print( "=" * 60 )

    return tests_failed == 0


if __name__ == "__main__":
    success = quick_smoke_test()
    exit( 0 if success else 1 )
