import json
import os
import asyncio

from pydantic_ai import Agent

import cosa.utils.util as du

from cosa.agents.v1.llm_client import LlmClient
from cosa.agents.v1.token_counter import TokenCounter
from cosa.app.configuration_manager import ConfigurationManager


class LlmClientFactory:
    """
    Singleton factory for creating LLM clients.
    """
    _instance = None
    
    def __new__( cls ):
        if cls._instance is None:
            cls._instance = super( LlmClientFactory, cls ).__new__( cls )
            # Initialize the instance
            cls._instance._initialized = False
        return cls._instance
    
    def __init__( self ):
        # Only initialize once
        if self._initialized:
            return
        
        # Instantiate the global config manager
        self.config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        self._initialized = True
    
    def get_client( self, model_descriptor: str, debug: bool = False, verbose: bool = False ):
        
        # test to see if the key exists
        if not self.config_mgr.exists( model_descriptor ):
            
            print(
                f"Configuration key '{model_descriptor}' not found in the configuration manager, getting vendor specific client..."
                )
            return self._get_vendor_specific_client( model_descriptor, debug, verbose )
        
        else:
            
            model_spec = self.config_mgr.get( model_descriptor, default=None )
            model_params = self.config_mgr.get( f"{model_descriptor}_params", default="{}", return_type="dict" )
            
            # model_tokenizer_map = self.config_mgr.get( "model_tokenizer_map", default="{}", return_type="json" )
            if debug:
                du.print_banner( f"Model params for '{model_descriptor}':" )
                print( json.dumps( model_params, indent=4, sort_keys=True ) )
            
            if model_spec.startswith( "vllm://" ):
                
                completion_mode = model_params.get( "completion", False )
                
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
                    # TODO: add support for passing in the remaining parameters
                    # model_tokenizer_map=model_tokenizer_map,
                    # **model_params
                )
            else:
                # Assume OpenAI, Groq, Google, etc.
                return Agent( model_spec, **model_params )
    
    # Vendor configuration
    VENDOR_URLS = {
        "openai"    : "https://api.openai.com/v1",
        "groq"      : "https://api.groq.com/openai/v1",
        "anthropic" : "https://api.anthropic.com/v1",
        "google-gla": "https://generativelanguage.googleapis.com/v1",
        "vllm"      : "http://192.168.1.21:3001/v1",
        "deepily"   : "http://192.168.1.21:3001/v1"
    }
    
    # API key environment variables
    VENDOR_API_ENV_VARS = {
        "openai"    : "OPENAI_API_KEY",
        "groq"      : "GROQ_API_KEY",
        "anthropic" : "ANTHROPIC_API_KEY",
        "google-gla": "GOOGLE_API_KEY",
        "vllm"      : None,  # Local server, no key needed
        "deepily"   : None  # Local server, no key needed
    }
    
    # Default parameters for LlmClient
    CLIENT_DEFAULT_PARAMS = {
        "temperature": 0.7,
        "max_tokens" : 1024
    }
    
    # Generation parameters for Agent (pydantic-ai needs different params than OpenAI)
    AGENT_GENERATION_PARAMS = {
        # Empty by default - the library has its own defaults
    }
    
    class AgentWrapper:
        """
        A wrapper class that provides a synchronous interface to the async Agent class.
        This allows the Agent to be used like other LLM clients.
        """
        
        def __init__( self, agent, debug=False ):
            self.agent = agent
            self.debug = debug
        
        def run( self, prompt, **kwargs ):
            """
            Synchronous version of agent.run that handles the async/await internally
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
    
    def _get_vendor_specific_client( self, model_descriptor: str, debug=False, verbose=False ):
        """
        Creates a client for a specific vendor based on the model descriptor.
        
        Model descriptor formats:
        - "vendor:model-name" (e.g., "groq:llama-3.1-8b-instant")
        - "vendor/model-name" (e.g., "Groq/llama-3.1-8b-instant")
        """
        # Parse the vendor and model name
        vendor, model_name = self._parse_model_descriptor( model_descriptor )
        
        # Get vendor-specific configuration
        base_url = self.VENDOR_URLS.get( vendor.lower() )
        api_key_env = self.VENDOR_API_ENV_VARS.get( vendor.lower() )
        
        if not base_url:
            raise ValueError( f"Unsupported vendor: {vendor}" )
        
        # Get API key from environment if available
        api_key = None
        if api_key_env and api_key_env in os.environ:
            api_key = os.environ[ api_key_env ]
        
        if debug:
            du.print_banner( f"Creating {vendor} client for model {model_name}" )
            print( f"Base URL: {base_url}" )
            print( f"API Key env var: {api_key_env}" )
        
        # Different handling based on vendor
        if vendor.lower() == "openai":
            # For OpenAI, use pydantic_ai Agent with openai: prefix
            # First check if OPENAI_API_KEY exists in environment
            if "OPENAI_API_KEY" in os.environ:
                if debug: print( "Using OPENAI_API_KEY from environment" )
                openai_api_key = os.environ[ "OPENAI_API_KEY" ]
            else:
                if debug: print( "OPENAI_API_KEY not found in environment, using du.get_api_key()..." )
                openai_api_key = du.get_api_key( "openai" )
                
            # Set environment variable for OpenAI client
            os.environ[ "OPENAI_API_KEY" ] = openai_api_key
            
            if debug: print( f"Using Agent with model string: openai:{model_name}" )
                
            agent = Agent( f"openai:{model_name}" )
            return self.AgentWrapper( agent, debug=debug )
        
        elif vendor.lower() == "groq":
            # Groq uses OpenAI-compatible API but with its own API key
            # First check if GROQ_API_KEY exists
            if "GROQ_API_KEY" in os.environ:
                if debug: print( "Using GROQ_API_KEY from environment" )
                groq_api_key = os.environ[ "GROQ_API_KEY" ]
            else:
                if debug: print( "GROQ_API_KEY not found in environment, using du.get_api_key()..." )
                groq_api_key = du.get_api_key( "groq" )
                
            # Set both API keys since OpenAI client will use OPENAI_API_KEY by default
            os.environ[ "OPENAI_API_KEY" ] = groq_api_key
            # For pydantic-ai, we also need GROQ_API_KEY
            os.environ[ "GROQ_API_KEY" ] = groq_api_key
            os.environ[ "OPENAI_BASE_URL" ] = base_url
            
            if debug:
                print( f"Set OPENAI_BASE_URL={base_url}" )
                print( f"Set OPENAI_API_KEY and GROQ_API_KEY" )
                print( f"Using Agent with model string: openai:{model_name}" )
            
            # Create an agent with appropriate credentials
            agent = Agent( f"openai:{model_name}" )
            return self.AgentWrapper( agent, debug=debug )
        
        elif vendor.lower() == "anthropic":
            # Claude models from Anthropic
            # First check if ANTHROPIC_API_KEY exists in environment
            if "ANTHROPIC_API_KEY" in os.environ:
                if debug: print( "Using ANTHROPIC_API_KEY from environment" )
                anthropic_api_key = os.environ[ "ANTHROPIC_API_KEY" ]
            else:
                if debug: print( "ANTHROPIC_API_KEY not found in environment, using du.get_api_key()..." )
                anthropic_api_key = du.get_api_key( "claude" )
                
            # Set environment variable for Anthropic client
            os.environ[ "ANTHROPIC_API_KEY" ] = anthropic_api_key
            
            if debug: print( f"Using Agent with model string: anthropic:{model_name}" )
                
            agent = Agent( f"anthropic:{model_name}" )
            return self.AgentWrapper( agent, debug=debug )
        
        elif vendor.lower() == "google-gla":
            # Google Gemini models
            # First check if GEMINI_API_KEY exists in environment
            if "GEMINI_API_KEY" in os.environ:
                if debug: print( "Using GEMINI_API_KEY from environment" )
                gemini_api_key = os.environ[ "GEMINI_API_KEY" ]
            else:
                if debug: print( "GEMINI_API_KEY not found in environment, using du.get_api_key()..." )
                gemini_api_key = du.get_api_key( "gemini" )
                
            # Set environment variable for Google client
            os.environ[ "GEMINI_API_KEY" ] = gemini_api_key
            
            if debug: print( f"Using Agent with model string: google-gla:{model_name}" )
                
            agent = Agent( f"google-gla:{model_name}" )
            return self.AgentWrapper( agent, debug=debug )
        
        elif vendor.lower() in [ "vllm", "deepily" ]:
            # # Local models via vLLM
            # return LlmClient(
            #     base_url=base_url,
            #     model_name=model_name,
            #     completion_mode=False,  # Default to chat mode
            #     debug=debug,
            #     verbose=verbose,
            #     **default_params
            # )
            raise NotImplementedError(
                f"Local models via vLLM w/o configuration definitions or keys are not implemented yet."
                )
        else:
            # Fallback - try using Agent with the raw model descriptor
            agent = Agent( model_descriptor )
            return self.AgentWrapper( agent, debug=debug )
    
    def _parse_model_descriptor( self, model_descriptor: str ) -> tuple:
        """
        Parse a model descriptor to extract vendor and model name.
        
        Supports formats:
        - "vendor:model-name"
        - "vendor/model-name"
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


if __name__ == "__main__":
    factory = LlmClientFactory()
    
    # client =      factory.get_client( LlmClient.PHI_4_14B )
    # client          = factory.get_client( LlmClient.DEEPILY_MINISTRAL_8B_2410 )
    # client = factory.get_client( LlmClient.GROQ_LLAMA_3_1_8B )
    # client = factory.get_client( LlmClient.OPENAI_GPT_4o_MINI )
    # client = factory.get_client( LlmClient.GOOGLE_GEMINI_1_5_FLASH )
    client = factory.get_client( LlmClient.ANTHROPIC_CLAUDE_SONNET_3_5 )
    template_path = du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt"
    prompt_template = du.get_file_as_string( template_path )
    voice_command = "can I please talk to a human?"
    prompt = prompt_template.format( voice_command=voice_command )
    response = client.run( prompt )
    
    print( response )
