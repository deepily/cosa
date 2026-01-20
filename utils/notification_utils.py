#!/usr/bin/env python3
"""
Notification Utility Functions.

Shared formatting utilities for notification messages across COSA agents
and the MCP server. Handles TTS message formatting and API format conversion.
"""


def format_questions_for_tts( questions: list ) -> str:
    """
    Format questions for TTS playback.

    Returns ONLY the question text. Options are displayed in the UI
    and should NOT be included in the spoken TTS message.

    Requires:
        - questions is a list of question dicts
        - Each dict should have 'question' key
        - Optional 'multiSelect' key (camelCase, from Claude Code format)

    Ensures:
        - Returns TTS-friendly string with question text only
        - Multi-question: "Question N of X: ..."
        - Single question: Just the question text
        - Adds multi-select hint when multiSelect is True

    Args:
        questions: List of question objects (Claude Code format)

    Returns:
        str: TTS-friendly message (question text only, no options)
    """
    total = len( questions )
    parts = []

    for i, q in enumerate( questions, 1 ):
        question_text = q.get( "question", "Please select an option" )
        multi_select = q.get( "multiSelect", False )

        # Build question intro (question text ONLY)
        if total > 1:
            part = f"Question {i} of {total}: {question_text}"
        else:
            part = question_text

        # Add multi-select hint if needed
        if multi_select:
            part += " You can select multiple options."

        # NOTE: Options are displayed in UI, not spoken in TTS
        parts.append( part )

    return " ".join( parts )


def convert_questions_for_api( questions: list ) -> dict:
    """
    Convert Claude Code's camelCase format to API's snake_case format.

    Claude Code uses: multiSelect (camelCase)
    API/Database expects: multi_select (snake_case)

    Frontend rendering depends on multi_select:
        - multi_select: true -> renders as checkboxes
        - multi_select: false -> renders as radio buttons

    Requires:
        - questions is a list of question dicts

    Ensures:
        - Returns dict with 'questions' array
        - multiSelect converted to multi_select
        - Other fields preserved (question, header, options)

    Args:
        questions: List of question dicts in Claude Code format

    Returns:
        dict: API-compatible response_options structure
    """
    converted = []
    for q in questions:
        converted_q = {
            "question"     : q.get( 'question', '' ),
            "header"       : q.get( 'header', 'Selection' ),
            "multi_select" : q.get( 'multiSelect', False ),
            "options"      : q.get( 'options', [] )
        }
        converted.append( converted_q )
    return { "questions": converted }


def quick_smoke_test():
    """Quick smoke test for notification_utils module."""
    import cosa.utils.util as cu

    cu.print_banner( "Notification Utils Smoke Test", prepend_nl=True )

    try:
        # Test 1: Single question, single select
        print( "Testing format_questions_for_tts (single question, single select)..." )
        questions = [ {
            "question"    : "Which database?",
            "multiSelect" : False,
            "options"     : [ { "label": "PostgreSQL" }, { "label": "MySQL" } ]
        } ]
        tts = format_questions_for_tts( questions )
        assert tts == "Which database?"
        assert "Option" not in tts  # Options NOT in TTS
        print( f"✓ Result: '{tts}'" )

        # Test 2: Single question, multi-select
        print( "Testing format_questions_for_tts (single question, multi-select)..." )
        questions = [ {
            "question"    : "Which features?",
            "multiSelect" : True,
            "options"     : [ { "label": "Auth" }, { "label": "Cache" } ]
        } ]
        tts = format_questions_for_tts( questions )
        assert "Which features?" in tts
        assert "You can select multiple options" in tts
        print( f"✓ Result: '{tts}'" )

        # Test 3: Multiple questions
        print( "Testing format_questions_for_tts (multiple questions)..." )
        questions = [
            { "question": "First?", "multiSelect": False },
            { "question": "Second?", "multiSelect": True }
        ]
        tts = format_questions_for_tts( questions )
        assert "Question 1 of 2" in tts
        assert "Question 2 of 2" in tts
        assert "You can select multiple options" in tts
        print( f"✓ Result: '{tts}'" )

        # Test 4: convert_questions_for_api
        print( "Testing convert_questions_for_api..." )
        questions = [ {
            "question"    : "Which auth?",
            "header"      : "Auth",
            "multiSelect" : True,
            "options"     : [ { "label": "OAuth" }, { "label": "JWT" } ]
        } ]
        converted = convert_questions_for_api( questions )
        assert "questions" in converted
        assert converted[ "questions" ][ 0 ][ "multi_select" ] is True
        assert "multiSelect" not in converted[ "questions" ][ 0 ]
        print( "✓ multiSelect -> multi_select conversion correct" )

        print( "\n✓ Notification utils smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
