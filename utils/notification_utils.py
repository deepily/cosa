#!/usr/bin/env python3
"""
Notification Utility Functions.

Shared formatting utilities for notification messages across COSA agents
and the MCP server. Handles TTS message formatting and API format conversion.
"""


def normalize_abstract( abstract ) -> str:
    """
    Convert literal \\n to actual newlines in abstract text.

    Requires:
        - abstract is None or a string

    Ensures:
        - Returns None if input is None
        - Returns string with literal \\\\n converted to newlines

    Args:
        abstract: Abstract text from MCP tool call (may contain escaped newlines)

    Returns:
        str or None: Normalized abstract text
    """
    if abstract is None:
        return None
    return abstract.replace( '\\n', '\n' )


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


def format_open_ended_batch_for_tts( questions: list ) -> str:
    """
    Format open-ended batch questions for TTS playback.

    For a single question, speaks the question text directly.
    For multiple questions, speaks only the count preamble — individual
    questions are already displayed in the UI batch form and should NOT
    be read aloud (too verbose for voice UX).

    Requires:
        - questions is a non-empty list of question dicts
        - Each dict should have 'question' key

    Ensures:
        - Single question: just the question text (no preamble)
        - Multiple questions: count-only preamble ("I have N questions for you.")

    Args:
        questions: List of question objects with 'question' and 'header' keys

    Returns:
        str: TTS-friendly message
    """
    total = len( questions )
    if total == 0:
        return ""
    if total == 1:
        return questions[ 0 ].get( "question", "Please provide a value" )
    return f"I have {total} questions for you."


def convert_open_ended_batch_for_api( questions: list ) -> dict:
    """
    Convert open-ended batch questions to API response_options format.

    Marks each question with input_type: "text" so the frontend knows
    to render text inputs instead of radio/checkbox options.

    Requires:
        - questions is a list of question dicts

    Ensures:
        - Returns dict with 'questions' array
        - Each question has input_type: "text"
        - Preserves question and header fields

    Args:
        questions: List of question dicts with 'question' and 'header' keys

    Returns:
        dict: API-compatible response_options structure
    """
    converted = []
    for q in questions:
        converted_q = {
            "question"   : q.get( "question", "" ),
            "header"     : q.get( "header", f"Question {len( converted ) + 1}" ),
            "input_type" : "text"
        }
        if "default_value" in q:
            converted_q[ "default_value" ] = q[ "default_value" ]
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

        # Test 5: format_open_ended_batch_for_tts (single question)
        print( "Testing format_open_ended_batch_for_tts (single question)..." )
        questions = [ { "question": "What topic?", "header": "Topic" } ]
        tts = format_open_ended_batch_for_tts( questions )
        assert tts == "What topic?"
        assert "I have" not in tts
        print( f"✓ Result: '{tts}'" )

        # Test 6: format_open_ended_batch_for_tts (multiple questions — count-only preamble)
        print( "Testing format_open_ended_batch_for_tts (multiple questions)..." )
        questions = [
            { "question": "What topic?", "header": "Topic" },
            { "question": "What budget?", "header": "Budget" },
            { "question": "Who is the audience?", "header": "Audience" }
        ]
        tts = format_open_ended_batch_for_tts( questions )
        assert tts == "I have 3 questions for you."
        assert "Question 1 of 3" not in tts  # Individual questions NOT spoken
        print( f"✓ Result: '{tts}'" )

        # Test 7: convert_open_ended_batch_for_api
        print( "Testing convert_open_ended_batch_for_api..." )
        questions = [
            { "question": "What topic?", "header": "Topic" },
            { "question": "What budget?", "header": "Budget" }
        ]
        converted = convert_open_ended_batch_for_api( questions )
        assert "questions" in converted
        assert len( converted[ "questions" ] ) == 2
        assert converted[ "questions" ][ 0 ][ "input_type" ] == "text"
        assert converted[ "questions" ][ 0 ][ "header" ] == "Topic"
        assert converted[ "questions" ][ 1 ][ "header" ] == "Budget"
        print( "✓ Batch questions converted with input_type='text'" )

        # Test 8: convert_open_ended_batch_for_api with default_value
        print( "Testing convert_open_ended_batch_for_api (with default_value)..." )
        questions = [
            { "question": "What budget?", "header": "Budget", "default_value": "no limit" },
            { "question": "What audience?", "header": "Audience" }
        ]
        converted = convert_open_ended_batch_for_api( questions )
        assert converted[ "questions" ][ 0 ][ "default_value" ] == "no limit"
        assert "default_value" not in converted[ "questions" ][ 1 ]
        print( "✓ default_value passed through when present, omitted when absent" )

        print( "\n✓ Notification utils smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
