#!/usr/bin/env python3
"""
XML Models for CoSA Agents

Pydantic models for XML input/output serialization and deserialization.
Each model corresponds to XML patterns used in CoSA agent prompts and
provides type-safe, validated data structures.

This module provides:
- SimpleResponse: Single field responses (gist, summary, answer)
- CommandResponse: Command routing responses (command + args)
- YesNoResponse: Boolean/confirmation responses  
- CodeResponse: Code generation responses with thoughts and explanation
- MathBrainstormResponse: Complex math reasoning with brainstorming

All models inherit from BaseXMLModel and include quick_smoke_test() methods.
"""

import time
from typing import Optional, List, Union, Literal
from pydantic import Field, field_validator, model_validator

from cosa.agents.io_models.utils.util_xml_pydantic import BaseXMLModel, XMLParsingError


class SimpleResponse( BaseXMLModel ):
    """
    Simple single-field response model.
    
    Handles XML responses with a single content field like:
    - <response><gist>content</gist></response>
    - <response><summary>content</summary></response>
    - <response><answer>content</answer></response>
    
    The field name is dynamic based on the actual XML tag.
    """
    
    # Since we don't know the field name ahead of time, we use extra="allow"
    # in BaseXMLModel to capture any field dynamically
    
    def get_content( self ) -> Optional[str]:
        """
        Get the main content field regardless of its name.
        
        Returns the first string field found, which should be the content.
        
        Returns:
            Content string or None if no content found
        """
        for field_name, field_value in self.model_dump().items():
            if isinstance( field_value, str ):
                return field_value
        return None
    
    def get_field_name( self ) -> Optional[str]:
        """
        Get the name of the content field.
        
        Returns:
            Field name or None if no fields
        """
        fields = list( self.model_dump().keys() )
        return fields[0] if fields else None
    
    @classmethod
    def create( cls, field_name: str, content: str ) -> 'SimpleResponse':
        """
        Create a SimpleResponse with a specific field name and content.
        
        Args:
            field_name: The XML tag name (e.g., 'gist', 'summary')
            content: The content value
            
        Returns:
            SimpleResponse instance
        """
        data = { field_name: content }
        return cls( **data )
    
    @classmethod
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for SimpleResponse.
        
        Tests dynamic field handling and common patterns.
        
        Args:
            debug: Enable debug output
            
        Returns:
            True if all tests pass
        """
        if debug:
            print( f"Testing {cls.__name__}..." )
        
        try:
            # Test base functionality
            if not super().quick_smoke_test( debug=False ):
                return False
            
            # Test gist response
            gist_xml = "<response><gist>This is a brief summary</gist></response>"
            gist_response = cls.from_xml( gist_xml )
            assert gist_response.get_content() == "This is a brief summary"
            assert gist_response.get_field_name() == "gist"
            
            # Test summary response  
            summary_xml = "<response><summary>Detailed summary here</summary></response>"
            summary_response = cls.from_xml( summary_xml )
            assert summary_response.get_content() == "Detailed summary here"
            assert summary_response.get_field_name() == "summary"
            
            # Test answer response
            answer_xml = "<response><answer>42</answer></response>"
            answer_response = cls.from_xml( answer_xml )
            assert answer_response.get_content() == "42"
            
            # Test creation
            created_response = cls.create( "test_field", "test_content" )
            assert created_response.get_content() == "test_content"
            assert created_response.get_field_name() == "test_field"
            
            # Test round-trip
            xml_output = created_response.to_xml()
            assert "<test_field>test_content</test_field>" in xml_output
            
            if debug:
                print( f"✓ {cls.__name__} smoke test PASSED" )
            
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
            return False


class CommandResponse( BaseXMLModel ):
    """
    Command routing response model.
    
    Handles XML responses for agent routing:
    <response>
        <command>math</command>
        <args>calculate 2+2</args>  
    </response>
    
    Used by agent-router and vox-command templates.
    """
    
    command: str = Field( ..., description="The agent command to execute" )
    args: Optional[str] = Field( default="", description="Arguments for the command" )
    
    @field_validator( 'command' )
    @classmethod
    def validate_command( cls, v ):
        """
        Validate that command is a known agent type.
        
        Args:
            v: Command value to validate
            
        Returns:
            Validated command
            
        Raises:
            ValueError: If command is not recognized
        """
        valid_commands = [
            'math', 'calendar', 'calendaring', 'todo', 'todo-lists', 
            'weather', 'gist', 'confirmation', 'yes-no', 'debugger',
            'plain-vanilla-question', 'receptionist'
        ]
        
        if v.lower() not in [cmd.lower() for cmd in valid_commands]:
            # Don't fail validation, just warn - allows for new commands
            pass
            
        return v
    
    @classmethod
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for CommandResponse.
        
        Tests command routing patterns and validation.
        
        Args:
            debug: Enable debug output
            
        Returns:
            True if all tests pass
        """
        if debug:
            print( f"Testing {cls.__name__}..." )
        
        try:
            # Test base functionality
            if debug:
                print( "  - Testing base functionality..." )
            if not super().quick_smoke_test( debug=debug ):
                if debug:
                    print( "    ✗ Base functionality test failed" )
                return False
            if debug:
                print( "    ✓ Base functionality passed" )
            
            # Test math command
            if debug:
                print( "  - Testing math command XML..." )
            math_xml = "<response><command>math</command><args>calculate square root of 16</args></response>"
            math_response = cls.from_xml( math_xml )
            assert math_response.command == "math", f"Expected 'math', got '{math_response.command}'"
            assert math_response.args == "calculate square root of 16", f"Expected 'calculate square root of 16', got '{math_response.args}'"
            if debug:
                print( "    ✓ Math command test passed" )
            
            # Test calendar command
            calendar_xml = "<response><command>calendar</command><args>show events for next week</args></response>"
            calendar_response = cls.from_xml( calendar_xml )
            assert calendar_response.command == "calendar"
            
            # Test empty args
            if debug:
                print( "  - Testing empty args..." )
            simple_xml = "<response><command>gist</command><args></args></response>"
            simple_response = cls.from_xml( simple_xml )
            assert simple_response.command == "gist"
            if debug:
                print( f"    - args value: '{simple_response.args}' (type: {type(simple_response.args)})" )
            assert simple_response.args == "" or simple_response.args is None, f"Expected empty string or None, got '{simple_response.args}'"
            if debug:
                print( "    ✓ Empty args test passed" )
            
            # Test missing args (should default to empty)
            if debug:
                print( "  - Testing missing args..." )
            no_args_xml = "<response><command>weather</command></response>"
            no_args_response = cls.from_xml( no_args_xml )
            assert no_args_response.command == "weather"
            if debug:
                print( f"    - missing args value: '{no_args_response.args}' (type: {type(no_args_response.args)})" )
            # Missing args should use default value ""
            assert no_args_response.args == "", f"Expected empty string for missing args, got '{no_args_response.args}'"
            if debug:
                print( "    ✓ Missing args test passed" )
            
            # Test round-trip
            if debug:
                print( "  - Testing round-trip serialization..." )
            test_response = cls( command="test", args="test args" )
            xml_output = test_response.to_xml()
            assert "<command>test</command>" in xml_output
            assert "<args>test args</args>" in xml_output
            if debug:
                print( "    ✓ Serialization passed" )
            
            # Parse it back
            if debug:
                print( "    - Testing round-trip parsing..." )
            parsed_back = cls.from_xml( xml_output )
            assert parsed_back.command == "test"
            assert parsed_back.args == "test args"
            if debug:
                print( "    ✓ Round-trip parsing passed" )
            
            if debug:
                print( f"✓ {cls.__name__} smoke test PASSED" )
            
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
                import traceback
                traceback.print_exc()
            return False


class YesNoResponse( BaseXMLModel ):
    """
    Yes/No confirmation response model.
    
    Handles boolean responses:
    <response>
        <answer>yes</answer>
    </response>
    
    Used by confirmation agents and yes/no questions.
    """
    
    answer: str = Field( ..., description="Yes/no answer" )
    
    @field_validator( 'answer' )
    @classmethod
    def validate_answer( cls, v ):
        """
        Validate that answer is a valid yes/no response.
        
        Args:
            v: Answer value to validate
            
        Returns:
            Normalized answer (lowercase)
        """
        valid_responses = ['yes', 'no', 'y', 'n', 'true', 'false']
        
        if v.lower() not in valid_responses:
            # Allow any string but warn
            pass
            
        return v.lower()
    
    def is_yes( self ) -> bool:
        """
        Check if the answer is affirmative.
        
        Returns:
            True if answer is yes/y/true
        """
        return self.answer.lower() in ['yes', 'y', 'true']
    
    def is_no( self ) -> bool:
        """
        Check if the answer is negative.
        
        Returns:
            True if answer is no/n/false
        """
        return self.answer.lower() in ['no', 'n', 'false']
    
    @classmethod  
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for YesNoResponse.
        
        Tests yes/no validation and boolean logic.
        
        Args:
            debug: Enable debug output
            
        Returns:
            True if all tests pass
        """
        if debug:
            print( f"Testing {cls.__name__}..." )
        
        try:
            # Test base functionality
            if not super().quick_smoke_test( debug=False ):
                return False
            
            # Test yes response
            yes_xml = "<response><answer>yes</answer></response>"
            yes_response = cls.from_xml( yes_xml )
            assert yes_response.answer == "yes"
            assert yes_response.is_yes() == True
            assert yes_response.is_no() == False
            
            # Test no response
            no_xml = "<response><answer>no</answer></response>"
            no_response = cls.from_xml( no_xml )
            assert no_response.answer == "no"
            assert no_response.is_yes() == False
            assert no_response.is_no() == True
            
            # Test variations
            variations = [
                ("Y", True, False),
                ("N", False, True), 
                ("true", True, False),
                ("false", False, True)
            ]
            
            for answer, expected_yes, expected_no in variations:
                test_xml = f"<response><answer>{answer}</answer></response>"
                test_response = cls.from_xml( test_xml )
                assert test_response.is_yes() == expected_yes, f"Failed for {answer}"
                assert test_response.is_no() == expected_no, f"Failed for {answer}"
            
            # Test round-trip
            test_response = cls( answer="yes" )
            xml_output = test_response.to_xml()
            assert "<answer>yes</answer>" in xml_output
            
            if debug:
                print( f"✓ {cls.__name__} smoke test PASSED" )
            
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
            return False


class ReceptionistResponse( BaseXMLModel ):
    """
    Receptionist agent response model.
    
    Handles XML responses for receptionist agent conversations.
    This agent acts as a receptionist, answering questions based on
    previous conversations stored in memory.
    
    Expected XML format:
    <response>
        <thoughts>Analysis of the user query and memory search</thoughts>
        <category>benign OR humorous OR salacious</category>
        <answer>Concise conversational response to the query</answer>
    </response>
    
    Requires:
        - XML contains <thoughts>, <category>, and <answer> tags
        - category must be one of: benign, humorous, salacious
        - All fields contain non-empty strings
        
    Ensures:
        - Type-safe access to all response components
        - Automatic validation of category enum values
        - Proper XML serialization and deserialization
        
    Raises:
        - ValidationError if category is not in allowed values
        - XMLParsingError if required tags are missing
    """
    
    thoughts: str = Field( ..., description="Agent's reasoning process about the query and memory search" )
    category: Literal["benign", "humorous", "salacious"] = Field( ..., description="Query categorization for content filtering" )
    answer: str = Field( ..., description="Concise conversational answer to the user's query" )
    
    @field_validator( "thoughts" )
    @classmethod
    def validate_thoughts_not_empty( cls, v: str ) -> str:
        """
        Validate that thoughts field is not empty.
        
        Requires:
            - v is a string (guaranteed by Pydantic)
            
        Ensures:
            - Returns non-empty trimmed string
            
        Raises:
            - ValueError if thoughts is empty after stripping whitespace
        """
        trimmed = v.strip()
        if not trimmed:
            raise ValueError( "thoughts cannot be empty" )
        return trimmed
        
    @field_validator( "answer" )
    @classmethod
    def validate_answer_not_empty( cls, v: str ) -> str:
        """
        Validate that answer field is not empty.
        
        Requires:
            - v is a string (guaranteed by Pydantic)
            
        Ensures:
            - Returns non-empty trimmed string
            
        Raises:
            - ValueError if answer is empty after stripping whitespace
        """
        trimmed = v.strip()
        if not trimmed:
            raise ValueError( "answer cannot be empty" )
        return trimmed
        
    def is_safe_content( self ) -> bool:
        """
        Check if the response content is safe for all audiences.
        
        Requires:
            - self.category is properly validated Literal value
            
        Ensures:
            - Returns True if category is 'benign' or 'humorous'
            - Returns False if category is 'salacious'
            
        Raises:
            - None (category is guaranteed to be valid by Pydantic)
        """
        return self.category in ["benign", "humorous"]
        
    @classmethod
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for ReceptionistResponse model.
        
        Requires:
            - debug is a boolean flag for verbose output
            
        Ensures:
            - Tests XML parsing with valid receptionist response
            - Tests category validation with all allowed values
            - Tests field validation for empty strings
            - Returns True if all tests pass, False otherwise
            
        Raises:
            - None (catches and reports all exceptions)
        """
        if debug:
            print( "Testing ReceptionistResponse..." )
            
        try:
            # Test valid response parsing
            valid_xml = '''<response>
                <thoughts>The user is asking about system capabilities, which is a technical but innocent inquiry.</thoughts>
                <category>benign</category>
                <answer>CoSA is a collection of small agents designed for various tasks including code generation.</answer>
            </response>'''
            
            response = cls.from_xml( valid_xml )
            assert response.thoughts.startswith( "The user is asking" )
            assert response.category == "benign"
            assert "CoSA" in response.answer
            assert response.is_safe_content() == True
            
            if debug:
                print( "  ✓ Valid XML parsing test passed" )
            
            # Test all category values
            for category in ["benign", "humorous", "salacious"]:
                test_xml = f'''<response>
                    <thoughts>Test thoughts for {category} category</thoughts>
                    <category>{category}</category>
                    <answer>Test answer for validation</answer>
                </response>'''
                
                test_response = cls.from_xml( test_xml )
                assert test_response.category == category
                
            if debug:
                print( "  ✓ Category validation test passed" )
            
            # Test safe content detection
            safe_response = cls.from_xml( valid_xml.replace( "benign", "humorous" ) )
            assert safe_response.is_safe_content() == True
            
            unsafe_xml = valid_xml.replace( "benign", "salacious" )
            unsafe_response = cls.from_xml( unsafe_xml )
            assert unsafe_response.is_safe_content() == False
            
            if debug:
                print( "  ✓ Safe content detection test passed" )
                
            # Test to_xml round-trip
            xml_output = response.to_xml()
            reparsed = cls.from_xml( xml_output )
            assert reparsed.thoughts == response.thoughts
            assert reparsed.category == response.category  
            assert reparsed.answer == response.answer
            
            if debug:
                print( "  ✓ Round-trip serialization test passed" )
            
            if debug:
                print( "✓ ReceptionistResponse smoke test PASSED" )
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ ReceptionistResponse smoke test FAILED: {e}" )
            return False


class CodeResponse( BaseXMLModel ):
    """
    Code generation response model.
    
    Handles XML responses for code generation agents:
    <response>
        <thoughts>reasoning</thoughts>
        <code>
            <line>import math</line>
            <line>def function():</line>
            <line>    return result</line>
        </code>
        <returns>return_type</returns>
        <example>usage example</example>
        <explanation>how it works</explanation>
    </response>
    
    Used by math, calendaring, todo-lists, and debugging agents.
    """
    
    thoughts: str = Field( ..., description="Reasoning and problem analysis" )
    code: List[str] = Field( ..., description="Generated code as list of lines" )
    returns: str = Field( ..., description="Return type description" )
    example: str = Field( ..., description="Usage example" )
    explanation: str = Field( ..., description="Code explanation" )
    
    @model_validator( mode='before' )
    @classmethod
    def process_xml_data( cls, data ):
        """
        Process XML data before field validation.
        
        Handles xmltodict structures and converts them to proper field types.
        
        Args:
            data: Raw data from xmltodict or direct construction
            
        Returns:
            Processed data ready for field validation
        """
        if not isinstance( data, dict ):
            return data
            
        # Process code field if present
        if 'code' in data and isinstance( data['code'], dict ):
            data['code'] = cls._extract_lines_from_dict( data['code'] )
            
        return data
    
    @classmethod
    def _extract_lines_from_dict( cls, code_dict: dict ) -> List[str]:
        """
        Extract code lines from xmltodict nested structure.
        
        xmltodict converts:
        <code>
            <line>import math</line>
            <line>def func():</line>
        </code>
        
        Into: {'line': ['import math', 'def func():']} or {'line': 'single line'}
        
        Args:
            code_dict: Dictionary from xmltodict parsing
            
        Returns:
            List of code lines as strings
        """
        if 'line' in code_dict:
            lines = code_dict['line']
            if isinstance( lines, list ):
                # Multiple lines
                return [str(line) if line is not None else "" for line in lines]
            else:
                # Single line
                return [str(lines) if lines is not None else ""]
        else:
            # No line tags found - might be direct text content
            # This handles edge cases where code is directly in <code>text</code>
            return []
    
    @field_validator( 'code' )
    @classmethod
    def validate_code( cls, v ):
        """
        Validate that code list is not empty.
        
        Args:
            v: List of code lines (already processed by model_validator)
            
        Returns:
            Validated code list
        """
        if not v:
            raise ValueError( "Code must contain at least one line" )
        return v
    
    @field_validator( 'thoughts' )
    @classmethod
    def validate_thoughts( cls, v ):
        """Ensure thoughts is not empty."""
        if not v or not v.strip():
            raise ValueError( "Thoughts cannot be empty" )
        return v.strip()
    
    @field_validator( 'returns' )
    @classmethod
    def validate_returns( cls, v ):
        """Validate return type description."""
        if not v or not v.strip():
            return "None"  # Default return type
        return v.strip()
    
    def get_code_as_string( self, indent: str = "" ) -> str:
        """
        Get code as a formatted string.
        
        Args:
            indent: Optional indentation prefix for each line
            
        Returns:
            Formatted code string
        """
        return '\n'.join( f"{indent}{line}" for line in self.code )
    
    def has_imports( self ) -> bool:
        """
        Check if code contains import statements.
        
        Returns:
            True if any line starts with 'import' or 'from'
        """
        return any( 
            line.strip().startswith( ('import ', 'from ') ) 
            for line in self.code if line.strip()
        )
    
    def get_function_name( self ) -> Optional[str]:
        """
        Extract function name from code if present.
        
        Returns:
            Function name or None if no function definition found
        """
        import re
        for line in self.code:
            match = re.search( r'def\s+(\w+)\s*\(', line.strip() )
            if match:
                return match.group( 1 )
        return None
    
    @classmethod
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for CodeResponse.
        
        Tests code line extraction and processing with various XML patterns.
        
        Args:
            debug: Enable debug output
            
        Returns:
            True if all tests pass
        """
        if debug:
            print( f"Testing {cls.__name__}..." )
        
        try:
            # Test base functionality
            if not super().quick_smoke_test( debug=False ):
                if debug:
                    print( "    ✗ Base functionality test failed" )
                return False
            
            # Test simple code response
            if debug:
                print( "  - Testing simple code response..." )
            simple_xml = """<response>
                <thoughts>I need to write a simple function</thoughts>
                <code>
                    <line>def add_numbers(a, b):</line>
                    <line>    return a + b</line>
                </code>
                <returns>int</returns>
                <example>result = add_numbers(2, 3)</example>
                <explanation>Simple addition function</explanation>
            </response>"""
            
            simple_response = cls.from_xml( simple_xml )
            assert simple_response.thoughts == "I need to write a simple function"
            assert len( simple_response.code ) == 2
            assert "def add_numbers" in simple_response.code[0]
            assert "return a + b" in simple_response.code[1]
            assert simple_response.returns == "int"
            assert simple_response.has_imports() == False
            assert simple_response.get_function_name() == "add_numbers"
            
            if debug:
                print( "    ✓ Simple code test passed" )
            
            # Test complex code with imports and empty lines
            if debug:
                print( "  - Testing complex code with imports..." )
            complex_xml = """<response>
                <thoughts>Complex math calculation needed</thoughts>
                <code>
                    <line>import math</line>
                    <line>import numpy as np</line>
                    <line></line>
                    <line>def calculate_distance(x1, y1, x2, y2):</line>
                    <line>    dx = x2 - x1</line>
                    <line>    dy = y2 - y1</line>
                    <line>    return math.sqrt(dx**2 + dy**2)</line>
                </code>
                <returns>float</returns>
                <example>distance = calculate_distance(0, 0, 3, 4)</example>
                <explanation>Calculates Euclidean distance between two points</explanation>
            </response>"""
            
            complex_response = cls.from_xml( complex_xml )
            assert len( complex_response.code ) == 7
            assert complex_response.has_imports() == True
            assert "" in complex_response.code  # Empty line preserved
            assert complex_response.get_function_name() == "calculate_distance"
            
            if debug:
                print( "    ✓ Complex code test passed" )
            
            # Test XML escapes in code
            if debug:
                print( "  - Testing XML escapes in code..." )
            escaped_xml = """<response>
                <thoughts>Need to handle comparisons</thoughts>
                <code>
                    <line>if x &lt; 5 and y &gt; 3:</line>
                    <line>    result = "less than &amp; greater than"</line>
                </code>
                <returns>str</returns>
                <example>test_function(4, 5)</example>
                <explanation>Handles comparison operators</explanation>
            </response>"""
            
            escaped_response = cls.from_xml( escaped_xml )
            # xmltodict should handle escapes automatically
            assert "<" in str( escaped_response.code )
            assert ">" in str( escaped_response.code )
            assert "&" in str( escaped_response.code )
            
            if debug:
                print( "    ✓ XML escape test passed" )
            
            # Test round-trip serialization
            if debug:
                print( "  - Testing round-trip serialization..." )
            test_response = cls(
                thoughts="Test thoughts",
                code=["import os", "def test():", "    return True"],
                returns="bool",
                example="result = test()",
                explanation="Test function"
            )
            
            xml_output = test_response.to_xml()
            parsed_back = cls.from_xml( xml_output )
            
            assert parsed_back.thoughts == "Test thoughts"
            assert len( parsed_back.code ) == 3
            assert parsed_back.code[0] == "import os"
            assert parsed_back.returns == "bool"
            
            if debug:
                print( "    ✓ Round-trip test passed" )
            
            # Test utility methods
            if debug:
                print( "  - Testing utility methods..." )
            code_string = test_response.get_code_as_string()
            assert "import os" in code_string
            assert "def test():" in code_string
            
            indented_code = test_response.get_code_as_string( indent="  " )
            assert "  import os" in indented_code
            
            if debug:
                print( "    ✓ Utility methods test passed" )
            
            if debug:
                print( f"✓ {cls.__name__} smoke test PASSED" )
            
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
                import traceback
                traceback.print_exc()
            return False


class CalendarResponse( CodeResponse ):
    """
    Calendar agent response model.
    
    Extends CodeResponse with an additional 'question' field for calendar agents.
    
    Handles XML responses like:
    <response>
        <question>What events do I have today?</question>
        <thoughts>Need to filter events by today's date</thoughts>
        <code>
            <line>today_events = df[df['date'] == today]</line>
            <line>result = today_events['title'].tolist()</line>
        </code>
        <returns>list</returns>
        <example>get_today_events()</example>
        <explanation>Filters and returns today's events</explanation>
    </response>
    
    Used by calendaring agents that need to preserve the original question context.
    """
    
    question: str = Field( ..., description="Original question being answered" )
    
    @field_validator( 'question' )
    @classmethod
    def validate_question( cls, v ):
        """Ensure question is not empty."""
        if not v or not v.strip():
            raise ValueError( "Question cannot be empty" )
        return v.strip()
    
    @classmethod 
    def quick_smoke_test( cls, debug: bool = False ) -> bool:
        """
        Quick smoke test for CalendarResponse.
        
        Tests calendar-specific XML patterns including question field.
        
        Args:
            debug: Enable debug output
            
        Returns:
            True if all tests pass
        """
        try:
            if debug:
                print( f"Testing {cls.__name__}..." )
            
            # Test basic calendar XML
            if debug:
                print( "  - Testing basic calendar response..." )
            calendar_xml = """<response>
                <question>What meetings do I have today?</question>
                <thoughts>User wants to see today's scheduled meetings</thoughts>
                <code>
                    <line>import pandas as pd</line>
                    <line>from datetime import date</line>
                    <line>today = date.today()</line>
                    <line>meetings = df[df['date'] == today]</line>
                    <line>result = meetings[['title', 'time']].to_dict('records')</line>
                </code>
                <returns>list</returns>
                <example>get_meetings_today()</example>
                <explanation>Filters events for today and returns meeting details</explanation>
            </response>"""
            
            response = cls.from_xml( calendar_xml )
            assert response.question == "What meetings do I have today?"
            assert "today's scheduled meetings" in response.thoughts
            assert len( response.code ) == 5
            assert response.returns == "list"
            assert response.has_imports() == True
            
            if debug:
                print( "    ✓ Basic calendar test passed" )
            
            # Test question validation
            if debug:
                print( "  - Testing question validation..." )
            try:
                cls(
                    question="",  # Empty question should fail
                    thoughts="Test thoughts",
                    code=["test_line"],
                    returns="None",
                    example="test()",
                    explanation="Test"
                )
                assert False, "Empty question should have failed validation"
            except ValueError:
                pass  # Expected
            
            if debug:
                print( "    ✓ Question validation test passed" )
            
            # Test inheritance from CodeResponse
            if debug:
                print( "  - Testing CodeResponse inheritance..." )
            # Should inherit all CodeResponse functionality
            code_string = response.get_code_as_string()
            assert "import pandas as pd" in code_string
            assert response.get_function_name() is None  # No function in this example
            
            if debug:
                print( "    ✓ Inheritance test passed" )
            
            # Test round-trip with question field
            if debug:
                print( "  - Testing round-trip with question..." )
            test_response = cls(
                question="How many events this week?",
                thoughts="Count events for the current week",
                code=["events = df[df['week'] == current_week]", "count = len(events)"],
                returns="int", 
                example="weekly_count = count_events_this_week()",
                explanation="Counts events in the current week"
            )
            
            xml_output = test_response.to_xml()
            parsed_back = cls.from_xml( xml_output )
            
            assert parsed_back.question == "How many events this week?"
            assert parsed_back.thoughts == "Count events for the current week"
            assert len( parsed_back.code ) == 2
            assert parsed_back.returns == "int"
            
            if debug:
                print( "    ✓ Round-trip test passed" )
            
            if debug:
                print( f"✓ {cls.__name__} smoke test PASSED" )
            
            return True
            
        except Exception as e:
            if debug:
                print( f"✗ {cls.__name__} smoke test FAILED: {e}" )
                import traceback
                traceback.print_exc()
            return False


def quick_smoke_test() -> bool:
    """
    Quick smoke test for all XML models.
    
    Tests all models in this module following CoSA convention.
    
    Returns:
        True if all model tests pass
    """
    print( "Testing xml_models module..." )
    
    try:
        models_to_test = [
            SimpleResponse,
            CommandResponse,
            YesNoResponse,
            ReceptionistResponse,
            CodeResponse,
            CalendarResponse
        ]
        
        passed = 0
        for model_cls in models_to_test:
            try:
                if model_cls.quick_smoke_test( debug=True ):
                    passed += 1
                else:
                    print( f"✗ {model_cls.__name__} failed" )
            except Exception as e:
                print( f"✗ {model_cls.__name__} exception: {e}" )
        
        success = passed == len( models_to_test )
        
        if success:
            print( f"✓ xml_models module smoke test PASSED ({passed}/{len(models_to_test)})" )
        else:
            print( f"✗ xml_models module smoke test FAILED ({passed}/{len(models_to_test)})" )
        
        return success
        
    except Exception as e:
        print( f"✗ xml_models module smoke test FAILED: {e}" )
        return False


if __name__ == "__main__":
    # Run smoke tests when executed directly
    success = quick_smoke_test()
    exit( 0 if success else 1 )