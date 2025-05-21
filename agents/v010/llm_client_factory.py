import json
import os
import asyncio
from typing import Any, Optional, Union

from pydantic_ai import Agent

import cosa.utils.util as du
# from app import config_mgr
# from cosa.utils.util_stopwatch import Stopwatch

from cosa.agents.v010.llm_client import LlmClient
from cosa.app.configuration_manager import ConfigurationManager

class LlmClientFactory:
    """
    Singleton factory for creating LLM clients.
    
    This factory provides a unified interface to create clients for different LLM providers
    (OpenAI, Groq, Anthropic, Google, etc.) while handling the specifics of authentication,
    API endpoints, and client implementation details.
    
    Requires:
        - ConfigurationManager instance to read configuration values
        - API keys for requested providers set in environment variables or available via du.get_api_key()
        
    Ensures:
        - Only one instance of the factory exists at runtime (singleton pattern)
        - Returns appropriate LLM client instances based on model descriptors
        - Handles authentication and API endpoints transparently
        - Provides consistent interface across different LLM providers
        
    TODO:
        - Add comprehensive error handling and retry logic
        - Support fallback models when primary models are unavailable
        - Implement caching of responses for identical prompts
        - Add support for model-specific parameter validation
        - Develop monitoring and telemetry for LLM usage metrics
        - Implement cost tracking and budget management features
    """
    _instance: Optional['LlmClientFactory'] = None
    
    def __new__( cls, debug: bool=False, verbose: bool=False ):
        """
        Create or return the singleton instance of LlmClientFactory.
        
        Requires:
            - Class is LlmClientFactory or a subclass
            
        Ensures:
            - Only one instance of the factory exists at runtime
            - Returns existing instance if already created
            - Creates new instance if first call
            - Initializes _initialized flag on new instance
            
        Raises:
            - None
        """
        if cls._instance is None:
            cls._instance = super( LlmClientFactory, cls ).__new__( cls )
            # Initialize the instance
            cls._instance._initialized = False
        return cls._instance
    
    def __init__( self, debug: bool=False, verbose: bool=False ):
        """
        Initialize the singleton factory.
        
        Requires:
            - self._initialized attribute exists
            
        Ensures:
            - Initializes only once (subsequent calls are no-ops)
            - Creates ConfigurationManager instance
            - Sets debug and verbose flags
            - Sets _initialized to True
            
        Raises:
            - ConfigException if configuration manager initialization fails
        """
        # Only initialize once
        if self._initialized:
            return
        
        # Instantiate the global config manager
        self.config_mgr   = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        self._initialized = True
        self.debug        = debug
        self.verbose      = verbose
    
    def get_client( self, model_config_key: str, debug: bool=None, verbose: bool=None ) -> Union['LlmClient', 'AgentWrapper']:
        """
        Get an LLM client for the given model descriptor.
        
        This method first tries to find the model in the configuration manager.
        If found, it uses the configuration settings to create the client.
        If not found, it parses the model descriptor to determine the vendor
        and creates a vendor-specific client.
        
        Requires:
            - model_config_key: A string identifying the model, which can be either:
                1. A configuration key (e.g., "deepily/ministral_8b_2410_ft_lora")
                2. A vendor prefixed model name (e.g., "openai:gpt-4", "groq:llama-3.1-8b-instant")
            - Valid API keys for the requested vendor if using cloud APIs
            
        Ensures:
            - Returns an appropriate LLM client instance that supports the run() method
            - Handles authentication and API endpoint selection transparently
            - Provides debug information when debug=True
            
        Raises:
            - ValueError if the vendor is not supported
            - Various API errors if authentication fails or the model is unavailable
        """
        if debug   is not None: self.debug   = debug
        if verbose is not None: self.verbose = verbose
        
        # test to see if the key exists
        if self.debug: print( f"Checking if '{model_config_key}' exists in config_mgr..." )
        
        if not self.config_mgr.exists( model_config_key ):
            
            print( f"Configuration key '{model_config_key}' not found in config_mgr, getting vendor specific client...")
            return self._get_vendor_specific_client( model_config_key, debug, verbose )
        
        else:
            
            model_spec   = self.config_mgr.get( model_config_key, default=None )
            model_params = self.config_mgr.get( f"{model_config_key}_params", default="{}", return_type="dict" )
            
            # model_tokenizer_map = self.config_mgr.get( "model_tokenizer_map", default="{}", return_type="json" )
            if debug:
                du.print_banner( f"Model params for '{model_config_key}':" )
                print( json.dumps( model_params, indent=4, sort_keys=True ) )
            
            default_prompt_format = self.config_mgr.get( "prompt_format_default", default="json_message" )
            prompt_format         = model_params.get( "prompt_format", default_prompt_format )
            completion_mode       = prompt_format in [ "instruction_completion", "special_token" ]
            
            # Extract stream parameter if present (will be used in run() calls)
            self.stream_enabled   = model_params.get( "stream", False )
            
            # Remove parameters that will be passed explicitly, so that **model_params doesn't complain about multiple values
            model_params.pop( "prompt_format", None )
            model_params.pop( "model_name", None )
            
            if model_spec.startswith( "vllm://" ):
                
                # Format: vllm://host:port@model_id
                body = model_spec[ len( "vllm://" ): ]
                host_port, model_name = body.split( "@", 1 )
                if completion_mode:
                    base_url = f"http://{host_port}/v1/completions"
                else:
                    base_url = f"http://{host_port}/v1"
                
                print( f"Creating LLM client for {model_name} with base URL {base_url}" )
                
                return LlmClient(
                    base_url=base_url,
                    model_name=model_name,
                    completion_mode=completion_mode,
                    prompt_format=prompt_format,
                    # TODO: add support for passing in the remaining parameters
                    # model_tokenizer_map=model_tokenizer_map,
                    **model_params
                )
            else:
                # Assume OpenAI, Groq, Google, etc.
                return Agent( model_spec, **model_params )
    
    # Vendor configuration
    VENDOR_URLS: dict[str, str] = {
        "openai"    : "https://api.openai.com/v1",
        "groq"      : "https://api.groq.com/openai/v1",
        "anthropic" : "https://api.anthropic.com/v1",
        "google-gla": "https://generativelanguage.googleapis.com/v1",
        "vllm"      : "http://192.168.1.21:3001/v1",
        "deepily"   : "http://192.168.1.21:3001/v1",
        "mistralai" : "https://api.mistral.ai/v1"
    }
    
    # API key environment variables
    VENDOR_API_ENV_VARS: dict[str, Optional[str]] = {
        "openai"    : "OPENAI_API_KEY",
        "groq"      : "GROQ_API_KEY",
        "anthropic" : "ANTHROPIC_API_KEY",
        "google-gla": "GOOGLE_API_KEY",
        "vllm"      : None,  # Local server, no key needed
        "deepily"   : None,  # Local server, no key needed
        "mistralai" : "MISTRAL_API_KEY"
    }
    
    # Default parameters for LlmClient
    CLIENT_DEFAULT_PARAMS: dict[str, Any] = {
        "temperature": 0.7,
        "max_tokens" : 1024
    }
    # Comprehensive vendor configuration for the v2 method
    VENDOR_CONFIG: dict[str, dict[str, Any]] = {
        "openai"    : {
            "env_var"     : "OPENAI_API_KEY",
            "key_name"    : "openai",
            "agent_prefix": "openai:",
        },
        "groq"      : {
            "env_var"       : "GROQ_API_KEY",
            "key_name"      : "groq",
            "agent_prefix"  : "openai:",  # Groq uses OpenAI-compatible API
            "set_openai_env": True,  # Also set OPENAI_API_KEY for compatibility
        },
        "anthropic" : {
            "env_var"     : "ANTHROPIC_API_KEY",
            "key_name"    : "claude",
            "agent_prefix": "anthropic:",
        },
        "google-gla": {
            "env_var"     : "GEMINI_API_KEY",
            "key_name"    : "gemini",
            "agent_prefix": "google-gla:",
        },
        "mistralai" : {
            "env_var"       : "MISTRAL_API_KEY",
            "key_name"      : "mistral",
            "agent_prefix"  : "openai:",  # Mistral uses OpenAI-compatible API
            "set_openai_env": True,  # Also set OPENAI_API_KEY for compatibility
        },
        "vllm"      : {
            "client_class": "LlmClient",  # Use LlmClient instead of Agent
        },
        "deepily"   : {
            "client_class": "LlmClient",  # Use LlmClient instead of Agent
        }
    }
    
    class AgentWrapper:
        """
        A wrapper class that provides a synchronous interface to the async Agent class.
        This allows the Agent to be used like other LLM clients.
        
        The wrapper handles the async/await logic internally, so clients can use
        a synchronous run() method without worrying about async handling.
        
        Requires:
            - agent: A valid pydantic_ai Agent instance
            - asyncio module available for async/await handling
            
        Ensures:
            - Provides a synchronous run() method that matches the interface of other clients
            - Handles async/await logic internally
            - Returns the response data directly, not wrapped in a Response object
            - Provides debug output when debug=True
        """
        
        def __init__( self, agent: Agent, debug: bool=False ):
            """
            Initialize the wrapper with an async Agent.
            
            Requires:
                - agent is a valid pydantic_ai Agent instance
                
            Ensures:
                - Stores agent reference
                - Sets debug flag
                
            Raises:
                - TypeError if agent is not a valid Agent instance
            """
            self.agent = agent
            self.debug = debug
        
        def run( self, prompt: str, **kwargs: Any ) -> str:
            """
            Synchronous version of agent.run that handles the async/await internally.
            
            This method provides a synchronous interface to the async Agent.run() method,
            handling all the event loop and async/await logic transparently.
            
            Requires:
                - prompt: A non-empty string containing the prompt to send to the LLM
                - self.agent: A valid pydantic_ai Agent instance with a run() method
                
            Ensures:
                - Executes the prompt against the LLM in a synchronous manner
                - Handles event loop creation/reuse automatically
                - Extracts and returns the response data directly
                - Provides debug output when self.debug=True
                
            Raises:
                - Any exceptions from the underlying Agent.run() method
                - RuntimeError if async event loop issues occur
                
            Returns:
                - String response from the LLM
            """
            if self.debug:
                print( f"Running prompt through AgentWrapper..." )
            
            try:
                # Create a new event loop if one is not available
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop( loop )
                
                # Run the coroutine in the event loop
                response = loop.run_until_complete( self.agent.run( prompt, **kwargs ) )
                
                # Extract data attribute if present (pydantic_ai sometimes wraps responses)
                if hasattr( response, 'data' ):
                    return response.data
                return response
            
            except Exception as e:
                if self.debug:
                    print( f"Error in AgentWrapper.run: {str( e )}" )
                raise
    
    def _parse_model_descriptor( self, model_descriptor: str ) -> tuple[str, str]:
        """
        Parse a model descriptor to extract vendor and model name.
        
        This method handles different model descriptor formats and extracts
        the vendor and model name from the descriptor.
        
        Requires:
            - model_descriptor: A non-empty string in one of the following formats:
                1. "vendor:model-name" (e.g., "openai:gpt-4", "groq:llama-3.1-8b-instant")
                2. "vendor/model-name" (e.g., "Groq/llama-3.1-8b-instant")
                3. Special format for Deepily models (e.g., "deepily/ministral_8b_2410_ft_lora")
                4. Any other model name (will be assumed to be a vLLM model)
                
        Ensures:
            - Returns a tuple of (vendor, model_name)
            - vendor is a string identifying the LLM provider
            - model_name is a string identifying the specific model
            - Special handling for Deepily models and fallback to vLLM
            
        Returns:
            - Tuple of (vendor, model_name)
        """
        if ":" in model_descriptor:
            # Format is vendor:model-name (e.g., "groq:llama-3.1-8b-instant")
            vendor, model_name = model_descriptor.split( ":", 1 )
            return vendor.strip(), model_name.strip()
        
        elif "/" in model_descriptor:
            # Format is vendor/model-name (e.g., "Groq/llama-3.1-8b-instant")
            vendor, model_name = model_descriptor.split( "/", 1 )
            return vendor.strip(), model_name.strip()
        
        elif model_descriptor.startswith( "llm_deepily_" ):
            # Special case for Deepily models
            return "deepily", model_descriptor
        
        else:
            # If no vendor specified, assume vLLM for local models
            return "vllm", model_descriptor
            
    def _get_vendor_specific_client( self, model_descriptor: str, debug: bool=False, verbose: bool=False ) -> 'AgentWrapper':
        """
        A more compact version of the vendor-specific client creation.
        Uses configuration maps to reduce repetitive code.
        
        This implementation centralizes vendor configuration in a single map
        and follows a consistent pattern for handling API keys and client creation.
        
        Requires:
            - model_descriptor: String in format "vendor:model" or "vendor/model"
            - VENDOR_CONFIG map with complete vendor-specific configuration
            - Valid API keys for the requested vendor available in environment or via du.get_api_key()
            
        Ensures:
            - Returns appropriate client instance based on vendor
            - Sets all required environment variables for API access
            - Handles authentication consistently across vendors
            - Provides debug output when debug=True
            
        Raises:
            - ValueError if vendor is not supported in VENDOR_CONFIG
            - NotImplementedError for certain vendor types that are not yet implemented
            - API-specific errors if authentication fails
        """
        # Parse the vendor and model name
        vendor, model_name = self._parse_model_descriptor( model_descriptor )
        vendor_key = vendor.lower()
        
        # Get vendor configuration or default
        config = self.VENDOR_CONFIG.get( vendor_key, {} )
        if not config: raise ValueError( f"Unsupported vendor: {vendor}" )
            
        # Get base URL from vendor URLs map
        base_url = self.VENDOR_URLS.get( vendor_key )
        
        # Handle API keys if needed
        if "env_var" in config:
            env_var  = config[ "env_var" ]
            key_name = config[ "key_name" ]
            
            # Get API key from environment or utility function
            if env_var in os.environ:
                if debug: print( f"Using {env_var} from environment" )
                api_key = os.environ[env_var]
            else:
                if debug: print( f"{env_var} not found in environment, using du.get_api_key()..." )
                api_key = du.get_api_key( key_name )
                
            # Set environment variable
            os.environ[env_var] = api_key
            
            # Set additional keys if needed (for compatibility)
            if config.get( "set_openai_env" ):
                os.environ["OPENAI_API_KEY"] = api_key
                os.environ["OPENAI_BASE_URL"] = base_url
                if debug: print( f"Set OPENAI_BASE_URL={base_url} and OPENAI_API_KEY" )
                
        # Create client based on vendor configuration
        if config.get( "client_class" ) == "LlmClient":
            # For vendors using LlmClient
            if debug: print( f"Using LlmClient with base_url={base_url}, model={model_name}" )
                
            # Not implemented for vLLM/Deepily yet
            raise NotImplementedError( f"Local models via vLLM w/o configuration definitions are not implemented yet." )
        else:
            # For vendors using Agent
            agent_prefix = config.get( "agent_prefix", "" )
            full_model_string = f"{agent_prefix}{model_name}"
            
            if debug: print( f"Using Agent with model string: {full_model_string}" )
            
            agent = Agent( full_model_string )
            return self.AgentWrapper( agent, debug=debug )


if __name__ == "__main__":
    
    # Initialize factory
    factory = LlmClientFactory()
    
    # Prepare test prompt
    # template_path = du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt"
    # prompt_template = du.get_file_as_string( template_path )
    # voice_command = "can I please talk to a human?"
    # prompt = prompt_template.format( voice_command=voice_command )
    
    prompt_template = du.get_file_as_string( du.get_project_root() + ConfigurationManager().get( "prompt template for agent router go to date and time" ) )
    question = "What time is it?"
    prompt = prompt_template.format( question=question )
    
    # List of all available models to test
    models = [
        # # Local models
        LlmClient.PHI_4_14B,
        # LlmClient.MINISTRAL_8B_2410,
        # LlmClient.DEEPILY_MINISTRAL_8B_2410_FT_LORA,
        # # Cloud API models
        # LlmClient.GROQ_LLAMA_3_1_8B,
        # # LlmClient.OPENAI_GPT_01_MINI,
        # LlmClient.GOOGLE_GEMINI_1_5_FLASH,
        # LlmClient.ANTHROPIC_CLAUDE_SONNET_3_5
    ]
    
    # Iterate through all models
    for model in models:
        try:
            du.print_banner( f"Testing model: {model}..." )

            # Get client using the appropriate method
            # timer = Stopwatch( msg=f"Calling {model}..." )

            client   = factory.get_client( model, debug=True, verbose=True )
            response = client.run( prompt )

            # Print results
            du.print_banner( f"Response from {model}" )
            print( response )
            # timer.print( use_millis=True )

        except Exception as e:

            du.print_banner("Error", expletive=True)
            print(f"Error with {model}: {str(e)}")

            du.print_banner("Stack Trace", expletive=True)
            import traceback
            traceback.print_exc()
            print()

    print( "All LLM's iterated." )