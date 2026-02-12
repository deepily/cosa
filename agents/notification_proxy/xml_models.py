#!/usr/bin/env python3
"""
XML response models for Notification Proxy Agent.

Defines Pydantic BaseXMLModel subclasses for:
    - ScriptMatcherResponse: LLM fuzzy-matching of incoming questions to Q&A script entries
    - VerificationResponse: LLM scoring of expected vs actual answers for semantic equivalence

References:
    - src/cosa/agents/runtime_argument_expeditor/xml_models.py (ExpeditorResponse pattern)
    - src/conf/notification-proxy-scripts/ (Q&A script format)
"""

import json
from pydantic import Field, field_validator

from cosa.agents.io_models.utils.util_xml_pydantic import BaseXMLModel


class ScriptMatcherResponse( BaseXMLModel ):
    """
    XML response from Phi-4 for Q&A script matching.

    Used by ALL response types (OPEN_ENDED, OPEN_ENDED_BATCH, MULTIPLE_CHOICE, YES_NO).
    The LLM fuzzy-matches an incoming notification question to a Q&A script entry
    and returns the scripted answer inside this XML structure.

    Requires:
        - LLM returns valid XML with <response> root tag

    Ensures:
        - matched_entry contains index ("0", "1", ...) or "none"
        - answer contains the scripted answer text
        - For batch: answer contains JSON dict of header->answer mappings
        - confidence is a string "0.0" to "1.0"
    """

    matched_entry : str = Field( ..., description="Index of matched script entry, or 'none'" )
    answer        : str = Field( ..., description="The answer to return (or JSON for batch)" )
    confidence    : str = Field( default="0.0", description="Match confidence 0.0-1.0" )
    reasoning     : str = Field( default="", description="Why this entry was chosen" )

    @field_validator( "*", mode="before" )
    @classmethod
    def _coerce_none_to_empty_string( cls, v, info ):
        """
        Coerce None values to empty strings for optional string fields.

        Requires:
            - v is the field value (may be None from xmltodict)
            - info.field_name identifies the field

        Ensures:
            - Returns "" for None values on optional fields (confidence, reasoning)
            - Passes through non-None values and required fields unchanged
        """
        if v is None and info.field_name not in ( "matched_entry", "answer" ):
            return ""
        return v

    @classmethod
    def get_example_for_template( cls ):
        """
        Get example instance for prompt templates.

        Requires:
            - None

        Ensures:
            - Returns ScriptMatcherResponse with placeholder values for template injection
        """
        return cls(
            matched_entry = "[index of best-matching script entry, or 'none']",
            answer        = "[the answer text from the matched script entry]",
            confidence    = "[confidence score between 0.0 and 1.0]",
            reasoning     = "[brief explanation of why this entry matches]"
        )

    def get_confidence_float( self ):
        """
        Parse confidence string to float, clamped to [0.0, 1.0].

        Requires:
            - self.confidence is a string

        Ensures:
            - Returns float in [0.0, 1.0]
            - Returns 0.0 on parse failure
        """
        try:
            return max( 0.0, min( 1.0, float( self.confidence ) ) )
        except ( ValueError, TypeError ):
            return 0.0

    def is_match( self ):
        """
        Check if the LLM found a matching script entry.

        Requires:
            - self.matched_entry and self.answer are strings

        Ensures:
            - Returns True if matched_entry is not "none" and answer is non-empty
            - Returns False otherwise
        """
        return self.matched_entry.strip().lower() != "none" and self.answer.strip() != ""

    def get_answers_dict( self ):
        """
        Parse batch answer JSON string to dict.

        Used for OPEN_ENDED_BATCH responses where the answer field
        contains a JSON object mapping headers to answer values.

        Requires:
            - self.answer is a string (possibly JSON)

        Ensures:
            - Returns dict if answer is valid JSON object
            - Returns empty dict on parse failure or non-dict JSON
        """
        if not self.answer or not self.answer.strip():
            return {}
        try:
            parsed = json.loads( self.answer )
            return parsed if isinstance( parsed, dict ) else {}
        except ( json.JSONDecodeError, TypeError ):
            return {}

    @classmethod
    def quick_smoke_test( cls, debug=False ):
        """
        Quick smoke test for ScriptMatcherResponse.

        Args:
            debug: Enable debug output

        Returns:
            True if all tests pass
        """
        if debug: print( f"Testing {cls.__name__}..." )

        try:
            # Test base functionality
            if not super().quick_smoke_test( debug=False ):
                return False

            # Test creation with all fields
            response = cls(
                matched_entry = "2",
                answer        = "quantum computing breakthroughs 2026",
                confidence    = "0.95",
                reasoning     = "Keyword 'topic' matches entry 2"
            )
            assert response.matched_entry == "2"
            assert response.answer == "quantum computing breakthroughs 2026"

            # Test is_match
            assert response.is_match()
            no_match = cls(
                matched_entry = "none",
                answer        = "",
                confidence    = "0.0",
                reasoning     = "No match found"
            )
            assert not no_match.is_match()

            # Test get_confidence_float
            assert response.get_confidence_float() == 0.95
            assert no_match.get_confidence_float() == 0.0

            # Test get_answers_dict for batch
            batch = cls(
                matched_entry = "0",
                answer        = '{"budget": "no limit", "audience": "academic"}',
                confidence    = "0.9",
                reasoning     = "Batch match"
            )
            answers = batch.get_answers_dict()
            assert answers[ "budget" ] == "no limit"
            assert answers[ "audience" ] == "academic"

            # Test get_answers_dict with non-JSON
            non_json = cls(
                matched_entry = "0",
                answer        = "plain text answer",
                confidence    = "0.8",
                reasoning     = "Single answer"
            )
            assert non_json.get_answers_dict() == {}

            # Test XML round-trip
            xml_str = response.to_xml()
            assert "<matched_entry>2</matched_entry>" in xml_str
            parsed = cls.from_xml( xml_str )
            assert parsed.matched_entry == response.matched_entry
            assert parsed.answer == response.answer

            # Test template example
            example = cls.get_example_for_template()
            assert "index" in example.matched_entry.lower()

            # Test None coercion
            none_response = cls(
                matched_entry = "0",
                answer        = "test",
                confidence    = None,
                reasoning     = None
            )
            assert none_response.confidence == ""
            assert none_response.reasoning == ""

            if debug: print( f"✓ {cls.__name__} smoke test PASSED" )
            return True

        except Exception as e:
            if debug: print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
            return False


class VerificationResponse( BaseXMLModel ):
    """
    XML response from Phi-4 for answer verification scoring.

    Used by smoke tests and integration tests to compare expected vs actual
    answers using semantic equivalence instead of exact string matching.

    Requires:
        - LLM compares expected vs actual answers

    Ensures:
        - match is "true" or "false"
        - confidence is a string "0.0" to "1.0"
    """

    match      : str = Field( ..., description="'true' if answers are semantically equivalent, 'false' otherwise" )
    confidence : str = Field( default="0.0", description="Confidence 0.0-1.0" )
    reasoning  : str = Field( default="", description="Why match or no match" )

    @field_validator( "*", mode="before" )
    @classmethod
    def _coerce_none_to_empty_string( cls, v, info ):
        """
        Coerce None values to empty strings for optional string fields.

        Requires:
            - v is the field value (may be None from xmltodict)
            - info.field_name identifies the field

        Ensures:
            - Returns "" for None values on optional fields (confidence, reasoning)
            - Passes through non-None values and required fields unchanged
        """
        if v is None and info.field_name != "match":
            return ""
        return v

    @classmethod
    def get_example_for_template( cls ):
        """
        Get example instance for prompt templates.

        Requires:
            - None

        Ensures:
            - Returns VerificationResponse with placeholder values for template injection
        """
        return cls(
            match      = "[true if answers are semantically equivalent, false otherwise]",
            confidence = "[confidence score between 0.0 and 1.0]",
            reasoning  = "[brief explanation of comparison result]"
        )

    def is_match( self ):
        """
        Check if the answers were judged semantically equivalent.

        Requires:
            - self.match is a string

        Ensures:
            - Returns True if match is "true" (case-insensitive, stripped)
            - Returns False otherwise
        """
        return self.match.strip().lower() == "true"

    def get_confidence_float( self ):
        """
        Parse confidence string to float, clamped to [0.0, 1.0].

        Requires:
            - self.confidence is a string

        Ensures:
            - Returns float in [0.0, 1.0]
            - Returns 0.0 on parse failure
        """
        try:
            return max( 0.0, min( 1.0, float( self.confidence ) ) )
        except ( ValueError, TypeError ):
            return 0.0

    @classmethod
    def quick_smoke_test( cls, debug=False ):
        """
        Quick smoke test for VerificationResponse.

        Args:
            debug: Enable debug output

        Returns:
            True if all tests pass
        """
        if debug: print( f"Testing {cls.__name__}..." )

        try:
            # Test base functionality
            if not super().quick_smoke_test( debug=False ):
                return False

            # Test creation with all fields
            response = cls(
                match      = "true",
                confidence = "0.95",
                reasoning  = "Both answers mean the same thing"
            )
            assert response.match == "true"

            # Test is_match
            assert response.is_match()
            no_match = cls(
                match      = "false",
                confidence = "0.85",
                reasoning  = "Answers differ in meaning"
            )
            assert not no_match.is_match()

            # Test get_confidence_float
            assert response.get_confidence_float() == 0.95
            bad_conf = cls( match="true", confidence="invalid" )
            assert bad_conf.get_confidence_float() == 0.0

            # Test XML round-trip
            xml_str = response.to_xml()
            assert "<match>true</match>" in xml_str
            parsed = cls.from_xml( xml_str )
            assert parsed.match == response.match
            assert parsed.confidence == response.confidence

            # Test template example
            example = cls.get_example_for_template()
            assert "true" in example.match.lower()

            # Test None coercion
            none_response = cls(
                match      = "true",
                confidence = None,
                reasoning  = None
            )
            assert none_response.confidence == ""
            assert none_response.reasoning == ""

            if debug: print( f"✓ {cls.__name__} smoke test PASSED" )
            return True

        except Exception as e:
            if debug: print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
            return False


def quick_smoke_test():
    """Module-level smoke test following CoSA convention."""
    result1 = ScriptMatcherResponse.quick_smoke_test( debug=True )
    result2 = VerificationResponse.quick_smoke_test( debug=True )
    return result1 and result2


if __name__ == "__main__":
    success = quick_smoke_test()
    exit( 0 if success else 1 )
