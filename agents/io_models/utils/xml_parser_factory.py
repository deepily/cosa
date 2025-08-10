#!/usr/bin/env python3
"""
XML Parser Factory for CoSA Agent Migration

This module provides a factory for creating XML parsing strategies that support
gradual migration from legacy baseline parsing to modern Pydantic-based structured parsing.

The factory supports three parsing strategies:
- baseline: Legacy util_xml.py parsing (backward compatible)
- hybrid_v1: Runtime comparison between baseline and Pydantic (migration/testing)
- structured_v2: Full Pydantic XML models only (target architecture)

Configuration is driven by lupin-app.ini settings that control:
- Global strategy selection
- Per-agent strategy overrides  
- Migration debugging and comparison logging
"""

import time
from typing import Dict, Any, Optional, Type, Union
from abc import ABC, abstractmethod

import cosa.utils.util_xml as dux
from cosa.config.configuration_manager import ConfigurationManager
from cosa.agents.io_models.utils.util_xml_pydantic import BaseXMLModel
from cosa.agents.io_models.xml_models import (
    ReceptionistResponse, SimpleResponse, CommandResponse, 
    YesNoResponse, CodeResponse, CalendarResponse
)


class XmlParsingStrategy( ABC ):
    """
    Abstract base class for XML parsing strategies.
    
    Defines the interface that all parsing strategies must implement
    for consistent integration with AgentBase.
    """
    
    @abstractmethod
    def parse_xml_response( self, xml_response: str, agent_routing_command: str, xml_tag_names: list[str], debug: bool = False, verbose: bool = False ) -> Dict[str, Any]:
        """
        Parse XML response into dictionary format.
        
        Requires:
            - xml_response is valid XML string
            - agent_routing_command identifies agent type for model selection
            - xml_tag_names contains expected XML tags
            
        Ensures:
            - Returns dictionary with parsed values
            - Dictionary keys match xml_tag_names
            - Missing tags have appropriate default values
            
        Raises:
            - XMLParsingError for invalid XML or parsing failures
        """
        pass
    
    @abstractmethod
    def get_strategy_name( self ) -> str:
        """Get human-readable name of this parsing strategy."""
        pass


class BaselineXmlParsingStrategy( XmlParsingStrategy ):
    """
    Legacy baseline XML parsing strategy using util_xml.py.
    
    This strategy maintains backward compatibility with existing
    agent implementations by using the original XML parsing logic.
    """
    
    def parse_xml_response( self, xml_response: str, agent_routing_command: str, xml_tag_names: list[str], debug: bool = False, verbose: bool = False ) -> Dict[str, Any]:
        """
        Parse XML response using legacy util_xml.py methods.
        
        Requires:
            - xml_response contains valid XML structure
            - xml_tag_names lists expected XML tags to extract
            
        Ensures:
            - Returns dictionary with extracted tag values
            - 'code' and 'examples' tags parsed as nested lists
            - Other tags parsed as string values
            
        Raises:
            - None (malformed XML results in empty/partial dictionary)
        """
        if debug and verbose:
            print( f"BaselineXmlParsingStrategy: parsing XML response..." )
            
        prompt_response_dict = { }
        
        for xml_tag in xml_tag_names:
            if debug and verbose:
                print( f"  Looking for xml_tag [{xml_tag}]" )
                
            if xml_tag in [ "code", "examples" ]:
                # Legacy nested list parsing for code/examples
                xml_string = f"<{xml_tag}>" + dux.get_value_by_xml_tag_name( xml_response, xml_tag ) + f"</{xml_tag}>"
                prompt_response_dict[ xml_tag ] = dux.get_nested_list( xml_string, tag_name=xml_tag, debug=debug, verbose=verbose )
            else:
                prompt_response_dict[ xml_tag ] = dux.get_value_by_xml_tag_name( xml_response, xml_tag )
        
        return prompt_response_dict
    
    def get_strategy_name( self ) -> str:
        return "baseline"


class PydanticXmlParsingStrategy( XmlParsingStrategy ):
    """
    Modern Pydantic-based XML parsing strategy.
    
    This strategy uses strongly-typed Pydantic models for XML parsing,
    providing validation, type safety, and structured data access.
    """
    
    def __init__( self ):
        """
        Initialize Pydantic XML parsing strategy.
        
        Requires:
            - XML models are properly imported and available
            
        Ensures:
            - Agent routing command to model mapping is established
            - All supported agent types have corresponding Pydantic models
            
        Raises:
            - ImportError if required Pydantic models cannot be imported
        """
        # Map agent routing commands to their corresponding Pydantic models
        self.agent_model_map = {
            "agent router go to receptionist": ReceptionistResponse,
            "agent router go to todo list": CodeResponse,
            "agent router go to calendar": CalendarResponse,
            # Future mappings will be added as more agents are migrated
            # "agent router go to math": MathResponse,
            # "agent router go to date and time": MathBrainstormResponse,
            # etc.
        }
    
    def parse_xml_response( self, xml_response: str, agent_routing_command: str, xml_tag_names: list[str], debug: bool = False, verbose: bool = False ) -> Dict[str, Any]:
        """
        Parse XML response using Pydantic models with validation.
        
        Requires:
            - xml_response is valid XML matching expected model structure
            - agent_routing_command maps to a known Pydantic model
            
        Ensures:
            - Returns validated dictionary with type-safe values
            - All required fields are present and validated
            - Field types match Pydantic model specifications
            
        Raises:
            - ValueError if agent_routing_command not supported yet
            - ValidationError if XML doesn't match model requirements
            - XMLParsingError for XML parsing failures
        """
        if debug and verbose:
            print( f"PydanticXmlParsingStrategy: parsing XML for agent [{agent_routing_command}]" )
            
        # Get the appropriate Pydantic model for this agent
        model_class = self.agent_model_map.get( agent_routing_command )
        
        if model_class is None:
            raise ValueError( f"Pydantic model not yet implemented for agent: {agent_routing_command}" )
            
        if debug and verbose:
            print( f"  Using Pydantic model: {model_class.__name__}" )
            
        # Parse XML using the Pydantic model
        try:
            model_instance = model_class.from_xml( xml_response )
            result_dict = model_instance.model_dump()
            
            if debug and verbose:
                print( f"  Successfully parsed {len( result_dict )} fields" )
                
            return result_dict
            
        except Exception as e:
            if debug:
                print( f"  Pydantic parsing failed: {e}" )
            raise
    
    def get_strategy_name( self ) -> str:
        return "structured_v2"


class HybridXmlParsingStrategy( XmlParsingStrategy ):
    """
    Hybrid parsing strategy for migration testing and validation.
    
    This strategy runs both baseline and Pydantic parsing, compares results,
    and returns the configured strategy's results while logging differences.
    Useful for migration validation and testing.
    """
    
    def __init__( self ):
        """
        Initialize hybrid parsing strategy.
        
        Requires:
            - Both baseline and Pydantic strategies can be initialized
            
        Ensures:
            - Both parsing strategies are available
            - Comparison logging is configured
            
        Raises:
            - Any initialization errors from constituent strategies
        """
        self.baseline_strategy = BaselineXmlParsingStrategy()
        self.pydantic_strategy = PydanticXmlParsingStrategy()
    
    def parse_xml_response( self, xml_response: str, agent_routing_command: str, xml_tag_names: list[str], debug: bool = False, verbose: bool = False ) -> Dict[str, Any]:
        """
        Parse XML using both strategies and compare results.
        
        Requires:
            - xml_response is valid XML
            - Configuration manager available for logging settings
            
        Ensures:
            - Returns baseline strategy results (for compatibility)
            - Logs differences between strategies if comparison enabled
            - Performance timing recorded for both strategies
            
        Raises:
            - Any exceptions from baseline strategy (for compatibility)
        """
        if debug and verbose:
            print( f"HybridXmlParsingStrategy: running dual parsing comparison..." )
            
        # Get configuration for comparison logging
        config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        comparison_logging = config_mgr.get( "xml parsing migration comparison logging", default=False, return_type="boolean" )
        
        # Time baseline parsing
        start_time = time.time()
        try:
            baseline_result = self.baseline_strategy.parse_xml_response( 
                xml_response, agent_routing_command, xml_tag_names, debug=debug, verbose=verbose 
            )
            baseline_time = time.time() - start_time
            baseline_success = True
        except Exception as e:
            baseline_time = time.time() - start_time
            baseline_success = False
            baseline_error = str( e )
            if debug:
                print( f"  Baseline parsing failed: {e}" )
        
        # Time Pydantic parsing
        start_time = time.time()
        try:
            pydantic_result = self.pydantic_strategy.parse_xml_response( 
                xml_response, agent_routing_command, xml_tag_names, debug=debug, verbose=verbose 
            )
            pydantic_time = time.time() - start_time
            pydantic_success = True
        except Exception as e:
            pydantic_time = time.time() - start_time
            pydantic_success = False
            pydantic_error = str( e )
            if debug:
                print( f"  Pydantic parsing failed: {e}" )
        
        # Log comparison results if enabled
        if comparison_logging:
            print( f"\n=== XML Parsing Strategy Comparison ===" )
            print( f"Agent: {agent_routing_command}" )
            print( f"Baseline: {'SUCCESS' if baseline_success else 'FAILED'} ({baseline_time:.4f}s)" )
            print( f"Pydantic: {'SUCCESS' if pydantic_success else 'FAILED'} ({pydantic_time:.4f}s)" )
            
            if baseline_success and pydantic_success:
                # Compare field counts and values
                baseline_fields = set( baseline_result.keys() )
                pydantic_fields = set( pydantic_result.keys() )
                
                if baseline_fields != pydantic_fields:
                    print( f"FIELD MISMATCH:" )
                    print( f"  Baseline only: {baseline_fields - pydantic_fields}" )
                    print( f"  Pydantic only: {pydantic_fields - baseline_fields}" )
                
                # Check value differences for common fields
                common_fields = baseline_fields & pydantic_fields
                for field in common_fields:
                    if baseline_result[ field ] != pydantic_result[ field ]:
                        print( f"VALUE DIFF [{field}]:" )
                        print( f"  Baseline: {baseline_result[ field ]}" )
                        print( f"  Pydantic: {pydantic_result[ field ]}" )
            
            print( f"=== End Comparison ===\n" )
        
        # For migration compatibility, return baseline results
        # (This can be changed once migration is complete)
        if baseline_success:
            return baseline_result
        else:
            # If baseline fails but Pydantic succeeds, this is valuable data
            if pydantic_success:
                print( f"⚠️  Baseline failed but Pydantic succeeded for {agent_routing_command}" )
                return pydantic_result
            else:
                # Both failed - re-raise baseline error for compatibility
                raise Exception( baseline_error )
    
    def get_strategy_name( self ) -> str:
        return "hybrid_v1"


class XmlParserFactory:
    """
    Factory for creating XML parsing strategies based on configuration.
    
    This factory provides centralized creation and caching of XML parsing strategies,
    with configuration-driven strategy selection supporting gradual migration
    from baseline to Pydantic-based parsing.
    
    Supports:
    - Global strategy configuration
    - Per-agent strategy overrides
    - Strategy caching for performance
    - Migration debugging and testing
    """
    
    def __init__( self, config_mgr: Optional[ConfigurationManager] = None ):
        """
        Initialize XML parser factory with configuration.
        
        Requires:
            - Configuration manager provides access to XML parsing settings
            
        Ensures:
            - Factory is configured with appropriate parsing strategies
            - Strategy cache is initialized for performance
            - Default fallback behavior is established
            
        Raises:
            - ConfigException if required configuration is missing
        """
        self.config_mgr = config_mgr or ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        self.strategy_cache = { }
        
        # Load global configuration
        self.global_strategy = self.config_mgr.get( "xml_parsing_global_strategy", default="baseline" )
        self.debug_mode = self.config_mgr.get( "xml parsing migration debug mode", default=False, return_type="boolean" )
        self.force_both = self.config_mgr.get( "xml parsing migration force both strategies", default=False, return_type="boolean" )
        
        if self.debug_mode:
            print( f"XmlParserFactory initialized with global strategy: {self.global_strategy}" )
    
    def get_parser_strategy( self, agent_routing_command: str, debug: bool = False, verbose: bool = False ) -> XmlParsingStrategy:
        """
        Get appropriate XML parsing strategy for the specified agent.
        
        Requires:
            - agent_routing_command is a valid agent identifier
            - Configuration contains strategy settings
            
        Ensures:
            - Returns appropriate strategy based on global/override settings
            - Strategy instances are cached for performance
            - Fallback to baseline strategy if configuration issues
            
        Raises:
            - None (graceful fallback to baseline strategy)
        """
        # Check for agent-specific override (using plain English keys)
        override_key = f"xml parsing strategy for {agent_routing_command}"
        strategy_name = self.config_mgr.get( override_key, default=self.global_strategy )
        
        # Force hybrid strategy if force_both is enabled (for testing)
        if self.force_both and strategy_name != "hybrid_v1":
            if debug or self.debug_mode:
                print( f"Forcing hybrid_v1 strategy due to force_both_strategies setting" )
            strategy_name = "hybrid_v1"
        
        # Check cache first
        cache_key = f"{agent_routing_command}:{strategy_name}"
        if cache_key in self.strategy_cache:
            return self.strategy_cache[ cache_key ]
        
        # Create strategy instance
        try:
            if strategy_name == "baseline":
                strategy = BaselineXmlParsingStrategy()
            elif strategy_name == "hybrid_v1":
                strategy = HybridXmlParsingStrategy()
            elif strategy_name == "structured_v2":
                strategy = PydanticXmlParsingStrategy()
            else:
                if debug or self.debug_mode:
                    print( f"Unknown strategy '{strategy_name}', falling back to baseline" )
                strategy = BaselineXmlParsingStrategy()
                
        except Exception as e:
            if debug or self.debug_mode:
                print( f"Failed to create strategy '{strategy_name}': {e}, falling back to baseline" )
            strategy = BaselineXmlParsingStrategy()
        
        # Cache and return
        self.strategy_cache[ cache_key ] = strategy
        
        if debug or self.debug_mode:
            print( f"Created {strategy.get_strategy_name()} strategy for agent: {agent_routing_command}" )
            
        return strategy
    
    def parse_agent_response( self, xml_response: str, agent_routing_command: str, xml_tag_names: list[str], debug: bool = False, verbose: bool = False ) -> Dict[str, Any]:
        """
        Parse agent XML response using appropriate strategy.
        
        This is the main entry point for agent XML parsing, providing
        a consistent interface regardless of the underlying parsing strategy.
        
        Requires:
            - xml_response is valid XML string
            - agent_routing_command identifies the agent type
            - xml_tag_names contains expected XML tags to extract
            
        Ensures:
            - Returns parsed dictionary with expected field structure
            - Uses configuration-appropriate parsing strategy
            - Provides consistent interface across all strategies
            
        Raises:
            - XMLParsingError for parsing failures
            - ValidationError for Pydantic model validation failures
        """
        strategy = self.get_parser_strategy( agent_routing_command, debug=debug, verbose=verbose )
        
        if debug or self.debug_mode:
            print( f"Parsing XML response using {strategy.get_strategy_name()} strategy" )
            
        return strategy.parse_xml_response( 
            xml_response, agent_routing_command, xml_tag_names, debug=debug, verbose=verbose 
        )


def quick_smoke_test() -> bool:
    """
    Quick smoke test for XmlParserFactory.
    
    Tests factory initialization, strategy creation, and basic parsing
    functionality across all supported parsing strategies.
    
    Returns:
        True if all tests pass
    """
    print( "Testing XmlParserFactory..." )
    
    try:
        # Test 1: Factory initialization
        print( "  - Testing factory initialization..." )
        factory = XmlParserFactory()
        print( "    ✓ Factory created successfully" )
        
        # Test 2: Strategy creation for each type
        print( "  - Testing strategy creation..." )
        strategies_to_test = [
            ( "baseline", "agent router go to receptionist" ),
            ( "structured_v2", "agent router go to receptionist" ),
            ( "hybrid_v1", "agent router go to receptionist" )
        ]
        
        # Temporarily override global strategy for testing
        original_global = factory.global_strategy
        
        for strategy_name, routing_command in strategies_to_test:
            factory.global_strategy = strategy_name
            strategy = factory.get_parser_strategy( routing_command, debug=True )
            actual_name = strategy.get_strategy_name()
            
            # Both structured_v2 and hybrid_v1 might fall back to baseline if Pydantic model not available
            if strategy_name in ["structured_v2", "hybrid_v1"] and actual_name == "baseline":
                print( f"    ✓ {strategy_name} strategy fell back to baseline (expected for unimplemented agents)" )
            else:
                expected_names = {
                    "baseline": "baseline",
                    "hybrid_v1": "hybrid_v1", 
                    "structured_v2": "structured_v2"
                }
                expected = expected_names.get( strategy_name, strategy_name )
                assert actual_name == expected, f"Strategy name mismatch: expected {expected}, got {actual_name}"
                print( f"    ✓ {strategy_name} strategy created (returns {actual_name})" )
        
        # Restore original setting
        factory.global_strategy = original_global
        
        # Test 3: Basic XML parsing with receptionist (only implemented model)
        print( "  - Testing XML parsing..." )
        test_xml = '''<response>
            <thoughts>Testing the parser factory</thoughts>
            <category>benign</category>
            <answer>Factory test successful</answer>
        </response>'''
        
        # Test baseline parsing
        factory.global_strategy = "baseline"
        result = factory.parse_agent_response( 
            test_xml, 
            "agent router go to receptionist", 
            [ "thoughts", "category", "answer" ]
        )
        assert "thoughts" in result and "category" in result and "answer" in result
        print( "    ✓ Baseline parsing works" )
        
        # Test Pydantic parsing (if supported)
        try:
            factory.global_strategy = "structured_v2" 
            result = factory.parse_agent_response( 
                test_xml, 
                "agent router go to receptionist", 
                [ "thoughts", "category", "answer" ]
            )
            assert "thoughts" in result and "category" in result and "answer" in result
            print( "    ✓ Pydantic parsing works" )
        except ValueError as e:
            if "not yet implemented" in str( e ):
                print( "    ℹ Pydantic parsing not implemented for this agent (expected)" )
            else:
                raise
        
        # Test 4: Configuration override
        print( "  - Testing configuration override..." )
        # This would require modifying config, so just verify the key lookup works
        override_key = "xml parsing strategy for agent router go to receptionist"
        override_value = factory.config_mgr.get( override_key, default="baseline" )
        print( f"    ✓ Configuration override lookup works: {override_value}" )
        
        # Test 5: Cache behavior
        print( "  - Testing strategy caching..." )
        factory.strategy_cache.clear()  # Clear cache
        strategy1 = factory.get_parser_strategy( "agent router go to receptionist" )
        strategy2 = factory.get_parser_strategy( "agent router go to receptionist" )  
        assert strategy1 is strategy2, "Strategy caching not working"
        print( "    ✓ Strategy caching works" )
        
        print( "✓ XmlParserFactory smoke test PASSED" )
        return True
        
    except Exception as e:
        print( f"✗ XmlParserFactory smoke test FAILED: {e}" )
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run smoke test when executed directly
    success = quick_smoke_test()
    exit( 0 if success else 1 )