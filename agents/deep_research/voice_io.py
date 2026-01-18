#!/usr/bin/env python3
"""
Voice-First I/O Layer for COSA Deep Research Agent.

This module provides a unified interface for user interaction that:
1. PRIMARILY uses voice I/O via cosa_interface (TTS + voice input)
2. Automatically falls back to CLI text when voice is unavailable
3. Allows explicit --cli-mode override to force text interaction

The voice service availability is cached for the session duration
to avoid repeated connection attempts.

Priority Order:
    1. Voice I/O (cosa_interface functions) - PRIMARY
    2. CLI fallback (print/input) - when voice unavailable
    3. --cli-mode flag - forces CLI regardless of voice availability
"""

import asyncio
import logging
from typing import Optional, List

from . import cosa_interface

logger = logging.getLogger( __name__ )


# =============================================================================
# Module State
# =============================================================================

_force_cli_mode: bool = False
_voice_available: Optional[ bool ] = None  # None = not checked, True/False = cached


# =============================================================================
# Configuration Functions
# =============================================================================

def set_cli_mode( enabled: bool ) -> None:
    """
    Enable or disable forced CLI mode.

    When enabled, all interactions use CLI text (print/input)
    even if voice service is available.

    Requires:
        - enabled is a boolean

    Ensures:
        - Module state updated
        - Subsequent calls use appropriate mode

    Args:
        enabled: True to force CLI mode, False for voice-first
    """
    global _force_cli_mode
    _force_cli_mode = enabled
    if enabled:
        logger.info( "CLI mode enabled - voice I/O disabled" )


def reset_voice_check() -> None:
    """
    Reset the cached voice availability check.

    Call this if the voice service status may have changed
    and you want to re-check availability.

    Ensures:
        - Next call to is_voice_available() will re-check
    """
    global _voice_available
    _voice_available = None


async def is_voice_available() -> bool:
    """
    Check if voice service is available (result cached).

    Attempts a minimal notification to test the voice service.
    The result is cached for the session to avoid repeated checks.

    Ensures:
        - Returns True if voice service responds
        - Returns False if voice service unavailable/fails
        - Result is cached for subsequent calls

    Returns:
        bool: True if voice service is available
    """
    global _voice_available

    # Return cached result if available
    if _voice_available is not None:
        return _voice_available

    # Try to ping the voice service
    try:
        # Send a silent/minimal notification to test connectivity
        # Using a very short message that won't be intrusive
        await cosa_interface.notify_progress( "Initializing...", priority="low" )
        _voice_available = True
        logger.info( "Voice service available - using voice-first mode" )

    except Exception as e:
        _voice_available = False
        logger.warning( f"Voice service unavailable ({e}) - falling back to CLI mode" )

    return _voice_available


def get_mode_description() -> str:
    """
    Get a human-readable description of the current I/O mode.

    Returns:
        str: Description of current mode
    """
    if _force_cli_mode:
        return "CLI mode (forced)"
    elif _voice_available is True:
        return "Voice mode (primary)"
    elif _voice_available is False:
        return "CLI mode (voice unavailable)"
    else:
        return "Mode not yet determined"


# =============================================================================
# Voice-First I/O Functions
# =============================================================================

async def notify(
    message: str,
    priority: str = "medium",
    abstract: Optional[str] = None,
    session_name: Optional[str] = None
) -> None:
    """
    Send a progress notification (voice-first).

    In voice mode: Plays TTS announcement
    In CLI mode: Prints to console

    Requires:
        - message is a non-empty string
        - priority is "low", "medium", "high", or "urgent"

    Ensures:
        - Message is communicated to user via appropriate channel
        - Never raises (logs warnings on failure)

    Args:
        message: The message to announce
        priority: Notification priority level
        abstract: Optional supplementary context (markdown, URLs, details)
        session_name: Optional human-readable session name for UI display
    """
    # Check for forced CLI mode or unavailable voice
    if _force_cli_mode or not await is_voice_available():
        print( f"  {message}" )
        if abstract:
            print( f"\n  Context:\n{abstract}\n" )
        return

    try:
        await cosa_interface.notify_progress( message, priority, abstract, session_name )
    except Exception as e:
        logger.warning( f"Voice notification failed: {e}" )
        print( f"  {message}" )  # Fallback to print


async def ask_yes_no(
    question: str,
    default: str = "no",
    timeout: int = 60,
    abstract: Optional[str] = None
) -> bool:
    """
    Ask a yes/no question (voice-first).

    In voice mode: Speaks question via TTS, waits for voice response
    In CLI mode: Prints question, waits for keyboard input

    Requires:
        - question is a non-empty string
        - default is "yes" or "no"
        - timeout is positive integer (1-600)

    Ensures:
        - Returns True if user said yes
        - Returns False if user said no
        - Returns default value on timeout or error

    Args:
        question: The yes/no question to ask
        default: Default answer if timeout ("yes" or "no")
        timeout: Seconds to wait for response
        abstract: Optional supplementary context (plan details, URLs, markdown)

    Returns:
        bool: True if user approved, False otherwise
    """
    if _force_cli_mode or not await is_voice_available():
        # CLI fallback - show abstract if provided
        if abstract:
            print( f"\n  Context:\n{abstract}\n" )
        default_hint = "Y/n" if default == "yes" else "y/N"
        response = input( f"  {question} [{default_hint}]: " ).strip().lower()
        if not response:
            return default == "yes"
        return response in [ "y", "yes", "yeah", "yep", "sure", "ok", "okay" ]

    try:
        return await cosa_interface.ask_confirmation( question, default, timeout, abstract )
    except Exception as e:
        logger.warning( f"Voice ask_yes_no failed: {e}" )
        # Fallback to CLI
        if abstract:
            print( f"\n  Context:\n{abstract}\n" )
        response = input( f"  {question} [y/N]: " ).strip().lower()
        return response in [ "y", "yes" ]


async def get_input(
    prompt: str,
    allow_empty: bool = True,
    timeout: int = 300
) -> Optional[ str ]:
    """
    Get open-ended input from user (voice-first).

    In voice mode: Speaks prompt via TTS, captures voice response
    In CLI mode: Prints prompt, waits for keyboard input

    Requires:
        - prompt is a non-empty string
        - timeout is positive integer (1-600)

    Ensures:
        - Returns user's text response on success
        - Returns None on timeout, error, or empty (if not allowed)

    Args:
        prompt: The prompt to present to user
        allow_empty: If True, empty response returns empty string
        timeout: Seconds to wait for response

    Returns:
        str or None: User's response, or None on timeout/error
    """
    if _force_cli_mode or not await is_voice_available():
        # CLI fallback
        response = input( f"  {prompt}: " ).strip()
        if not response and not allow_empty:
            return None
        return response

    try:
        response = await cosa_interface.get_feedback( prompt, timeout )
        if not response and not allow_empty:
            return None
        return response
    except Exception as e:
        logger.warning( f"Voice get_input failed: {e}" )
        # Fallback to CLI
        response = input( f"  {prompt}: " ).strip()
        return response if response or allow_empty else None


async def choose(
    question: str,
    options: List[ str ],
    timeout: int = 120
) -> str:
    """
    Present multiple-choice options (voice-first).

    In voice mode: Speaks options via TTS, captures voice selection
    In CLI mode: Prints numbered options, waits for number input

    Requires:
        - question is a non-empty string
        - options is a non-empty list of strings
        - timeout is positive integer (1-600)

    Ensures:
        - Returns one of the provided options
        - Returns first option as default on timeout/error

    Args:
        question: The question introducing the choices
        options: List of option strings to present
        timeout: Seconds to wait for response

    Returns:
        str: The selected option
    """
    if not options:
        raise ValueError( "Options list cannot be empty" )

    if _force_cli_mode or not await is_voice_available():
        # CLI fallback - numbered menu
        print( f"\n  {question}" )
        for i, opt in enumerate( options, 1 ):
            print( f"    {i}. {opt}" )

        response = input( "  Enter number: " ).strip()
        try:
            idx = int( response ) - 1
            if 0 <= idx < len( options ):
                return options[ idx ]
        except ValueError:
            pass

        print( f"  Invalid selection, using default: {options[ 0 ]}" )
        return options[ 0 ]

    try:
        # Build question format for cosa_interface
        questions = [ {
            "question"    : question,
            "header"      : "Choice",
            "multiSelect" : False,
            "options"     : [ { "label": opt, "description": "" } for opt in options ]
        } ]

        result = await cosa_interface.present_choices( questions, timeout )
        selection = result.get( "answers", {} ).get( "Choice" )

        if selection and selection in options:
            return selection

        return options[ 0 ]  # Default

    except Exception as e:
        logger.warning( f"Voice choose failed: {e}" )
        # Fallback to CLI
        return options[ 0 ]


# =============================================================================
# Progressive Narrowing Functions (Theme/Topic Selection)
# =============================================================================

async def select_themes(
    themes: list,
    timeout: int = 180
) -> list:
    """
    Present themes for multi-select and return selected theme indices.

    Requires:
        - themes is a list of {"name": str, "description": str, "subquery_indices": list}
        - At least 2 themes provided

    Ensures:
        - Returns list of selected theme indices (0-based)
        - Returns empty list if user cancels

    Args:
        themes: List of theme dicts from clustering response
        timeout: Seconds to wait for response

    Returns:
        list[int]: Selected theme indices (0-based)
    """
    if _force_cli_mode or not await is_voice_available():
        # CLI fallback
        print( "\n  Select research themes (comma-separated numbers, or 'all'):" )
        for i, theme in enumerate( themes, 1 ):
            topic_count = len( theme.get( "subquery_indices", [] ) )
            print( f"    {i}. {theme[ 'name' ]} ({topic_count} topics)" )
            print( f"       {theme.get( 'description', '' )}" )

        response = input( "  Your selection: " ).strip().lower()
        if response == "all":
            return list( range( len( themes ) ) )

        try:
            indices = [ int( x.strip() ) - 1 for x in response.split( "," ) ]
            return [ i for i in indices if 0 <= i < len( themes ) ]
        except ValueError:
            return []

    # Voice mode - use present_choices with multiSelect
    questions = [ {
        "question"    : "Which research themes interest you? Select all that apply.",
        "header"      : "Themes",
        "multiSelect" : True,
        "options"     : [
            {
                "label"       : theme[ "name" ],
                "description" : f"{len( theme.get( 'subquery_indices', [] ) )} topics: {theme.get( 'description', '' )}"
            }
            for theme in themes
        ]
    } ]

    try:
        result = await cosa_interface.present_choices( questions, timeout )
        selected_names = result.get( "answers", {} ).get( "Themes", [] )

        # Handle single selection (string) vs multi (list)
        if isinstance( selected_names, str ):
            selected_names = [ selected_names ]

        # Map names back to indices
        return [
            i for i, theme in enumerate( themes )
            if theme[ "name" ] in selected_names
        ]

    except Exception as e:
        logger.warning( f"Voice select_themes failed: {e}" )
        return []


async def select_topics(
    topics: list,
    preselected: bool = True,
    timeout: int = 180
) -> list:
    """
    Present specific topics for refinement.

    Requires:
        - topics is a list of {"topic": str, "objective": str}

    Ensures:
        - Returns list of selected topic indices
        - Returns empty list if user cancels

    Args:
        topics: List of topic dicts (subqueries)
        preselected: Whether topics should be pre-selected (for deselection flow)
        timeout: Seconds to wait for response

    Returns:
        list[int]: Selected topic indices (0-based)
    """
    if _force_cli_mode or not await is_voice_available():
        # CLI fallback
        print( "\n  Refine topic selection (comma-separated numbers, 'all', or 'none'):" )
        for i, topic in enumerate( topics, 1 ):
            print( f"    {i}. {topic.get( 'topic', 'Unknown' )}" )

        response = input( "  Your selection: " ).strip().lower()
        if response == "all":
            return list( range( len( topics ) ) )
        if response == "none":
            return []

        try:
            indices = [ int( x.strip() ) - 1 for x in response.split( "," ) ]
            return [ i for i in indices if 0 <= i < len( topics ) ]
        except ValueError:
            return list( range( len( topics ) ) )  # Default to all on error

    # Voice mode
    questions = [ {
        "question"    : "Which specific topics should I research? Deselect any you want to skip.",
        "header"      : "Topics",
        "multiSelect" : True,
        "options"     : [
            {
                "label"       : topic.get( "topic", "Unknown" )[ :50 ],
                "description" : topic.get( "objective", "" )[ :80 ]
            }
            for topic in topics
        ]
    } ]

    try:
        result = await cosa_interface.present_choices( questions, timeout )
        selected = result.get( "answers", {} ).get( "Topics", [] )

        if isinstance( selected, str ):
            selected = [ selected ]

        # Map back to indices
        topic_names = [ t.get( "topic", "" )[ :50 ] for t in topics ]
        return [ i for i, name in enumerate( topic_names ) if name in selected ]

    except Exception as e:
        logger.warning( f"Voice select_topics failed: {e}" )
        return list( range( len( topics ) ) )  # Default to all on error


# =============================================================================
# Smoke Test
# =============================================================================

def quick_smoke_test():
    """Quick smoke test for voice_io module."""
    import cosa.utils.util as cu

    cu.print_banner( "Voice I/O Smoke Test", prepend_nl=True )

    try:
        # Test 1: Module state functions
        print( "Testing module state functions..." )
        assert _force_cli_mode is False
        set_cli_mode( True )
        assert _force_cli_mode is True
        set_cli_mode( False )
        assert _force_cli_mode is False
        print( "✓ set_cli_mode works correctly" )

        # Test 2: reset_voice_check
        print( "Testing reset_voice_check..." )
        global _voice_available
        _voice_available = True
        reset_voice_check()
        assert _voice_available is None
        print( "✓ reset_voice_check works correctly" )

        # Test 3: get_mode_description
        print( "Testing get_mode_description..." )
        _voice_available = None
        desc = get_mode_description()
        assert "not yet determined" in desc.lower()

        set_cli_mode( True )
        desc = get_mode_description()
        assert "forced" in desc.lower()
        set_cli_mode( False )
        print( "✓ get_mode_description works correctly" )

        # Test 4: Async function signatures
        print( "Testing async function signatures..." )
        import inspect
        assert inspect.iscoroutinefunction( is_voice_available )
        assert inspect.iscoroutinefunction( notify )
        assert inspect.iscoroutinefunction( ask_yes_no )
        assert inspect.iscoroutinefunction( get_input )
        assert inspect.iscoroutinefunction( choose )
        assert inspect.iscoroutinefunction( select_themes )
        assert inspect.iscoroutinefunction( select_topics )
        print( "✓ All async functions have correct signatures" )

        # Test 5: CLI mode fallback (force CLI mode for safe testing)
        print( "Testing CLI mode fallback..." )
        set_cli_mode( True )

        async def test_cli_fallback():
            # This should use CLI fallback (print), not voice
            # We can't fully test without mocking input()
            mode = get_mode_description()
            assert "forced" in mode.lower()

        asyncio.run( test_cli_fallback() )
        set_cli_mode( False )
        print( "✓ CLI mode fallback configured correctly" )

        # Reset state
        _voice_available = None

        print( "\n✓ Voice I/O smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
