#!/usr/bin/env python3
"""
Runtime Argument Expeditor - Core Logic.

Sits between LORA intent classification and agentic job creation.
When a user says "make me a podcast", the LORA model identifies the routing
command but may not capture all required arguments. The expeditor detects
missing args via LLM gap analysis against --help output, then asks the user
for missing information via synchronous voice notifications.

Scope: Deep Research, Podcast Generator, Research-to-Podcast (3 agents).
"""

import os
import re
from typing import Optional

import cosa.utils.util as cu

from cosa.agents.runtime_argument_expeditor.agent_registry import (
    AGENTIC_AGENTS,
    get_cli_help
)
from cosa.agents.runtime_argument_expeditor.xml_models import ExpeditorResponse
from cosa.agents.llm_client_factory import LlmClientFactory
from cosa.agents.io_models.utils.prompt_template_processor import PromptTemplateProcessor
from cosa.cli.notify_user_sync import notify_user_sync
from cosa.cli.notification_models import (
    NotificationRequest,
    NotificationPriority,
    ResponseType
)


class RuntimeArgumentExpeditor:
    """
    Determines which required arguments a user's voice command provides and
    asks for any missing ones before creating an agentic job.

    Requires:
        - config_mgr is a valid ConfigurationManager instance
        - The config has keys: runtime argument expeditor enabled,
          llm spec key for runtime argument expeditor,
          prompt template for runtime argument expeditor

    Ensures:
        - expedite() returns a complete args dict or None (cancel/timeout)
        - Uses LLM only for gap analysis; questions come from static registry
        - System-provided args are never asked for
    """

    SENDER_ID = "arg.expeditor@lupin.deepily.ai"

    def __init__( self, config_mgr, debug=False, verbose=False ):
        """
        Initialize the runtime argument expeditor.

        Requires:
            - config_mgr is a valid ConfigurationManager instance

        Ensures:
            - Reads 3 config keys
            - Creates LlmClientFactory singleton reference

        Args:
            config_mgr: ConfigurationManager instance
            debug: Enable debug output
            verbose: Enable verbose output
        """
        self.config_mgr         = config_mgr
        self.debug              = debug
        self.verbose            = verbose
        self.llm_spec_key       = config_mgr.get( "llm spec key for runtime argument expeditor" )
        self.prompt_template_path = config_mgr.get( "prompt template for runtime argument expeditor" )
        self.llm_factory        = LlmClientFactory( debug=debug, verbose=verbose )

    def expedite( self, command, raw_args, user_email, session_id, user_id, original_question ):
        """
        Run argument gap analysis and collect missing arguments from user.

        Requires:
            - command is a key in AGENTIC_AGENTS
            - raw_args is a string (may be empty)
            - user_email, session_id, user_id are non-empty strings
            - original_question is the full voice command string

        Ensures:
            - Returns dict of complete args if all required args are satisfied
            - Returns None if user cancels, times out, or command not found
            - System-provided args are injected, never asked for

        Args:
            command: Routing command key (e.g., "agent router go to deep research")
            raw_args: LORA-extracted arguments string
            user_email: Authenticated user's email
            session_id: WebSocket session ID
            user_id: System user ID
            original_question: Full voice command transcription

        Returns:
            dict or None: Complete argument dictionary or None on cancel
        """
        agent_entry = AGENTIC_AGENTS.get( command )
        if not agent_entry:
            print( f"[Expeditor] Unknown command: {command}" )
            return None

        # Step 1: Capture --help output
        help_text = get_cli_help( command )
        if not help_text:
            help_text = "(CLI help not available)"

        # Step 2: Parse LORA args and map to CLI names
        lora_args    = self._parse_lora_args( raw_args )
        mapped_args  = {}
        arg_mapping  = agent_entry[ "arg_mapping" ]

        for lora_name, value in lora_args.items():
            cli_name = arg_mapping.get( lora_name, lora_name )
            mapped_args[ cli_name ] = value

        if self.debug:
            print( f"[Expeditor] LORA args: {lora_args}" )
            print( f"[Expeditor] Mapped args: {mapped_args}" )

        # Step 3: Build and run LLM gap analysis prompt
        template_raw = cu.get_file_as_string(
            cu.get_project_root() + self.prompt_template_path
        )

        # Process {{PYDANTIC_XML_EXAMPLE}} first
        processor = PromptTemplateProcessor( debug=self.debug )
        template_processed = processor.process_template(
            template_raw, "runtime argument expeditor"
        )

        # Fill runtime placeholders
        system_args   = ", ".join( agent_entry[ "system_provided" ] )
        required_args = ", ".join( agent_entry[ "required_user_args" ] )
        extracted_str = ", ".join( f"{k}={v}" for k, v in mapped_args.items() ) if mapped_args else "(none)"

        prompt = template_processed.format(
            system_args    = system_args,
            help_text      = help_text,
            voice_command  = original_question,
            extracted_args = extracted_str,
            required_args  = required_args
        )

        if self.debug and self.verbose:
            print( f"[Expeditor] Prompt ({len( prompt )} chars):\n{prompt[ :500 ]}..." )

        # Step 4: Call LLM
        llm_client = self.llm_factory.get_client(
            self.llm_spec_key, debug=self.debug, verbose=self.verbose
        )
        response = llm_client.run( prompt )

        if self.debug: print( f"[Expeditor] LLM response: {response[ :300 ]}" )

        # Step 5: Parse response
        try:
            parsed = ExpeditorResponse.from_xml( response )
        except Exception as e:
            print( f"[Expeditor] Failed to parse LLM response: {e}" )
            # Fallback: assume all required args are missing
            parsed = ExpeditorResponse(
                all_required_met = "false",
                args_present     = "",
                args_missing     = ", ".join( agent_entry[ "required_user_args" ] )
            )

        # Step 6: If all args present, merge and return
        present_dict = parsed.get_present_dict()

        # Merge LLM-detected present args with LORA-mapped args
        final_args = dict( mapped_args )
        for k, v in present_dict.items():
            if k not in final_args:
                final_args[ k ] = v

        if parsed.is_complete():
            if self.debug: print( f"[Expeditor] All required args present: {final_args}" )
            return self._inject_system_args(
                final_args, agent_entry, user_email, session_id, user_id
            )

        # Step 7: Ask for missing args
        missing = parsed.get_missing_list()
        if self.debug: print( f"[Expeditor] Missing args: {missing}" )

        special_handlers = agent_entry.get( "special_handlers", {} )
        fallback_questions = agent_entry[ "fallback_questions" ]

        for arg_name in missing:
            # Skip if already collected
            if arg_name in final_args:
                continue

            handler = special_handlers.get( arg_name )

            if handler == "fuzzy_file_match":
                value = self._handle_fuzzy_file_match( user_email )
            elif arg_name in fallback_questions:
                value = self._ask_for_arg(
                    arg_name, fallback_questions[ arg_name ], user_email
                )
            else:
                # Generic fallback
                value = self._ask_for_arg(
                    arg_name,
                    f"Please provide the '{arg_name}' argument.",
                    user_email
                )

            if value is None:
                print( f"[Expeditor] User cancelled at arg '{arg_name}'" )
                return None

            # Handle special "no limit" / "none" answers for optional args
            if arg_name in ( "budget", "languages" ) and value.lower().strip() in ( "no limit", "none", "skip", "no" ):
                continue

            final_args[ arg_name ] = value

        if self.debug: print( f"[Expeditor] Final args: {final_args}" )

        return self._inject_system_args(
            final_args, agent_entry, user_email, session_id, user_id
        )

    def _inject_system_args( self, args_dict, agent_entry, user_email, session_id, user_id ):
        """
        Inject system-provided arguments into the args dictionary.

        Requires:
            - args_dict is a dict of user-provided arguments
            - agent_entry has "system_provided" list

        Ensures:
            - Returns args_dict with system args injected
            - Does not overwrite existing user-provided values

        Returns:
            dict: Args dict with system args added
        """
        system_map = {
            "user_email"  : user_email,
            "session_id"  : session_id,
            "user_id"     : user_id,
            "no_confirm"  : True,
        }

        for sys_arg in agent_entry[ "system_provided" ]:
            if sys_arg in system_map and sys_arg not in args_dict:
                args_dict[ sys_arg ] = system_map[ sys_arg ]

        return args_dict

    def _parse_lora_args( self, raw_args_str ):
        """
        Parse LORA raw argument string into a dictionary.

        Handles formats:
            - key="value"
            - key='value'
            - key=value (no quotes, stops at whitespace or comma)

        Requires:
            - raw_args_str is a string (may be empty or None)

        Ensures:
            - Returns dict mapping arg names to values
            - Handles multiple formats gracefully

        Args:
            raw_args_str: Raw argument string from LORA router

        Returns:
            dict: Parsed argument name-value pairs
        """
        if not raw_args_str or not raw_args_str.strip():
            return {}

        result = {}

        # Match key="value", key='value', or key=value patterns
        pattern = r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|(\S+))'
        matches = re.findall( pattern, raw_args_str )

        for match in matches:
            key = match[ 0 ]
            # Value is in whichever capture group matched
            value = match[ 1 ] or match[ 2 ] or match[ 3 ]
            result[ key ] = value

        return result

    def _ask_for_arg( self, arg_name, question, user_email ):
        """
        Ask the user for a missing argument via synchronous notification.

        Requires:
            - arg_name is a non-empty string
            - question is the question text to ask
            - user_email is the target user's email

        Ensures:
            - Returns user's response string on success
            - Returns None on timeout, error, or cancellation

        Args:
            arg_name: Name of the missing argument
            question: Fallback question from registry
            user_email: Target user for notification

        Returns:
            str or None: User's response or None
        """
        request = NotificationRequest(
            message         = question,
            response_type   = ResponseType.OPEN_ENDED,
            priority        = NotificationPriority.HIGH,
            target_user     = user_email,
            timeout_seconds = 60,
            sender_id       = self.SENDER_ID,
            title           = f"Missing: {arg_name}",
            suppress_ding   = False
        )

        response = notify_user_sync( request=request, debug=self.debug )

        if response.success and response.response_value:
            value = response.response_value.strip()
            # Check for cancellation keywords
            if value.lower() in ( "cancel", "nevermind", "never mind", "stop", "quit" ):
                return None
            return value

        return None

    def _handle_fuzzy_file_match( self, user_email ):
        """
        Use fuzzy file matching to find a research document by user description.

        Reuses the FuzzyFileMatchResponse + fuzzy-file-matching.txt prompt.
        Lists files from the user's deep research output directory.

        Requires:
            - user_email is a valid email

        Ensures:
            - Returns full file path if user selects a match
            - Returns None if no matches found or user cancels

        Args:
            user_email: User's email (determines research directory)

        Returns:
            str or None: Full path to selected research document
        """
        from cosa.agents.io_models.xml_models import FuzzyFileMatchResponse

        research_dir = cu.get_project_root() + f"/io/deep-research/{user_email}"

        if not os.path.exists( research_dir ):
            if self.debug: print( f"[Expeditor] No research directory: {research_dir}" )
            # Ask for a description instead of a file
            return self._ask_for_arg(
                "research",
                "I don't see any research documents. Please provide the path to a research document.",
                user_email
            )

        docs = [ f for f in os.listdir( research_dir ) if f.endswith( ".md" ) ]

        if not docs:
            if self.debug: print( f"[Expeditor] No markdown files in {research_dir}" )
            return self._ask_for_arg(
                "research",
                "No research documents found. Please provide the path to a research document.",
                user_email
            )

        # Ask user to describe which document
        description = self._ask_for_arg(
            "research",
            "Which research document should I use for the podcast? Describe it or say the filename.",
            user_email
        )
        if not description:
            return None

        # Check if they gave an exact filename
        if description in docs:
            return f"{research_dir}/{description}"

        # Try fuzzy matching via LLM
        try:
            from cosa.config.configuration_manager import ConfigurationManager

            config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            template_path = config_mgr.get( "prompt template for fuzzy file matching" )
            template = cu.get_file_as_string( cu.get_project_root() + template_path )

            processor = PromptTemplateProcessor( debug=self.debug )
            template = processor.process_template( template, "fuzzy file matching" )

            file_list = "\n".join( f"- {doc}" for doc in docs )
            prompt = template.format( description=description, file_list=file_list )

            llm_client = self.llm_factory.get_client(
                config_mgr.get( "llm spec key for fuzzy file matching" ),
                debug=self.debug, verbose=self.verbose
            )
            response = llm_client.run( prompt )

            parsed = FuzzyFileMatchResponse.from_xml( response )
            matches = [ m for m in parsed.get_matches_list() if m in docs ]

            if not matches:
                if self.debug: print( "[Expeditor] No fuzzy matches found" )
                return self._ask_for_arg(
                    "research",
                    "I couldn't find a matching document. Please say the exact filename.",
                    user_email
                )

            if len( matches ) == 1:
                return f"{research_dir}/{matches[ 0 ]}"

            # Multiple matches - ask user to pick
            options_str = ", ".join( f"{i + 1}. {m}" for i, m in enumerate( matches ) )
            pick = self._ask_for_arg(
                "research",
                f"I found multiple matches: {options_str}. Say the number or name of the one you want.",
                user_email
            )
            if not pick:
                return None

            # Try to match by number
            try:
                idx = int( pick.strip() ) - 1
                if 0 <= idx < len( matches ):
                    return f"{research_dir}/{matches[ idx ]}"
            except ValueError:
                pass

            # Try to match by name
            for m in matches:
                if pick.lower().strip() in m.lower():
                    return f"{research_dir}/{m}"

            # Fallback: use first match
            return f"{research_dir}/{matches[ 0 ]}"

        except Exception as e:
            print( f"[Expeditor] Fuzzy match error: {e}" )
            return self._ask_for_arg(
                "research",
                "Matching failed. Please provide the exact filename or path.",
                user_email
            )


# ============================================================================
# Smoke Test
# ============================================================================

def quick_smoke_test():
    """
    Quick smoke test for RuntimeArgumentExpeditor.

    Tests imports, arg parsing, registry lookup, and help capture.
    Does NOT require a running server or LLM.
    """
    cu.print_banner( "Runtime Argument Expeditor Smoke Test", prepend_nl=True )

    tests_passed = 0
    tests_failed = 0

    # Test 1: Imports
    print( "\n1. Testing imports..." )
    try:
        from cosa.agents.runtime_argument_expeditor.agent_registry import AGENTIC_AGENTS, get_cli_help
        from cosa.agents.runtime_argument_expeditor.xml_models import ExpeditorResponse
        from cosa.agents.runtime_argument_expeditor.expeditor import RuntimeArgumentExpeditor
        print( "   ✓ All imports successful" )
        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Import failed: {e}" )
        tests_failed += 1

    # Test 2: _parse_lora_args
    print( "\n2. Testing _parse_lora_args..." )
    try:
        # Create a minimal expeditor for testing parse method
        class MockConfig:
            def get( self, key, **kwargs ):
                return "test"
        expeditor = RuntimeArgumentExpeditor.__new__( RuntimeArgumentExpeditor )
        expeditor.debug = False

        # Test various formats
        result = expeditor._parse_lora_args( 'topic="quantum computing" budget=10' )
        assert result[ "topic" ] == "quantum computing", f"Expected 'quantum computing', got '{result.get( 'topic' )}'"
        assert result[ "budget" ] == "10"
        print( "   ✓ Double-quoted args parsed" )

        result = expeditor._parse_lora_args( "topic='AI safety'" )
        assert result[ "topic" ] == "AI safety"
        print( "   ✓ Single-quoted args parsed" )

        result = expeditor._parse_lora_args( "budget=50" )
        assert result[ "budget" ] == "50"
        print( "   ✓ Unquoted args parsed" )

        result = expeditor._parse_lora_args( "" )
        assert result == {}
        print( "   ✓ Empty string returns empty dict" )

        result = expeditor._parse_lora_args( None )
        assert result == {}
        print( "   ✓ None returns empty dict" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 3: Registry lookup
    print( "\n3. Testing registry lookup..." )
    try:
        entry = AGENTIC_AGENTS.get( "agent router go to deep research" )
        assert entry is not None
        assert "query" in entry[ "required_user_args" ]
        print( "   ✓ Deep research registry entry found" )

        entry = AGENTIC_AGENTS.get( "agent router go to podcast generator" )
        assert entry is not None
        assert "research" in entry[ "required_user_args" ]
        assert entry[ "special_handlers" ][ "research" ] == "fuzzy_file_match"
        print( "   ✓ Podcast generator registry entry found (with special handler)" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 4: CLI help capture
    print( "\n4. Testing CLI help capture..." )
    try:
        help_text = get_cli_help( "agent router go to deep research" )
        if help_text:
            print( f"   ✓ Deep research help captured ({len( help_text )} chars)" )
        else:
            print( "   ⚠ Help returned None (CLI module may not be runnable)" )

        help_none = get_cli_help( "nonexistent" )
        assert help_none is None
        print( "   ✓ Missing command returns None" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Test 5: ExpeditorResponse XML round-trip
    print( "\n5. Testing ExpeditorResponse XML round-trip..." )
    try:
        response = ExpeditorResponse(
            all_required_met = "false",
            args_present     = "query=test topic",
            args_missing     = "budget, audience"
        )

        assert not response.is_complete()
        assert response.get_missing_list() == [ "budget", "audience" ]
        assert response.get_present_dict() == { "query": "test topic" }

        xml = response.to_xml()
        parsed = ExpeditorResponse.from_xml( xml )
        assert parsed.all_required_met == "false"
        assert parsed.args_present == "query=test topic"
        print( "   ✓ XML round-trip works" )

        complete = ExpeditorResponse(
            all_required_met = "true",
            args_present     = "query=biodiversity",
            args_missing     = ""
        )
        assert complete.is_complete()
        assert complete.get_missing_list() == []
        print( "   ✓ Complete response detected correctly" )

        tests_passed += 1
    except Exception as e:
        print( f"   ✗ Failed: {e}" )
        tests_failed += 1

    # Summary
    print( f"\n{'=' * 60}" )
    print( f"Expeditor Smoke Test: {tests_passed} passed, {tests_failed} failed" )
    print( "=" * 60 )

    return tests_failed == 0


if __name__ == "__main__":
    success = quick_smoke_test()
    exit( 0 if success else 1 )
