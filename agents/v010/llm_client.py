import os
import time
import asyncio
from typing import Optional, Any

from boto3 import client
from openai import base_url
from sqlalchemy.util import counter

import cosa.utils.util as du
from cosa.agents.v010.llm_completion import LlmCompletion

from cosa.agents.v010.token_counter import TokenCounter

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from cosa.app.configuration_manager import ConfigurationManager


class LlmClient:
    """
    A flexible client for interacting with local and remote LLM services.
    
    This client provides a unified interface for both chat and completion modes,
    handles token counting, supports streaming, and collects performance metrics.
    
    Requires:
        - Valid base_url for the LLM API endpoint
        - Valid model_name compatible with the API
        - API key if required by the service
        - TokenCounter for tracking token usage
        
    Ensures:
        - Consistent interface for both completion and chat-based models
        - Token counting for prompt and completion
        - Performance metrics (tokens/second, duration)
        - Proper environment variable configuration for API access
        - Streaming and non-streaming response options
    
    Usage:
        client = LlmClient(base_url="https://api.endpoint.com/v1", 
                          model_name="model-name",
                          completion_mode=False)
        response = client.run("Your prompt here", stream=True)
    """
    # for ad hoc use when creating the ephemeral models
    DEEPILY_PREFIX                    = "deepily"
    # Model identifier constants
    PHI_4_14B                         = "kaitchup/phi_4_14b"
    DEEPILY_MINISTRAL_8B_2410_FT_LORA = "deepily/ministral_8b_2410_ft_lora"
    MINISTRAL_8B_2410                 = "mistralai/Ministral-8B-Instruct-2410"
    GROQ_LLAMA_3_1_8B                 = "groq:llama-3.1-8b-instant"
    OPENAI_GPT_01_MINI                = "openai:o1-mini-2024-09-12"
    GOOGLE_GEMINI_1_5_FLASH           = "google-gla:gemini-1.5-flash"
    ANTHROPIC_CLAUDE_SONNET_3_5       = "anthropic:claude-3-5-sonnet-latest"
    
    # QWEN_2_5_32B = "kaitchup/Qwen2.5-Coder-32B-Instruct-AutoRound-GPTQ-4bit"
    
    @staticmethod
    def get_model( mnt_point: str, prefix: str=DEEPILY_PREFIX ) -> str:
        """
        Construct a model identifier in the required format.
        
        Requires:
            - mnt_point is a non-empty string
            - prefix is a non-empty string
            
        Ensures:
            - Returns model string in 'prefix//mnt_point' format
            - Validates that '//' is present in the constructed model
            
        Raises:
            - ValueError if the constructed model doesn't contain '//'
        """
        
        model = f"{prefix}/{mnt_point}"
        if "//" not in model:
            raise ValueError( f"ERROR: Model [{model}] not in 'prefix//mnt/point' format!" )
        return model
    
    def __init__( self,
        
        base_url: str = "http://192.168.1.21:3001/v1",
        model_name: str = "F00",
        completion_mode: bool = False,
        prompt_format: str = "",
        api_key: Optional[ str ] = "EMPTY",
        model_tokenizer_map: Optional[dict[str, str]] = None,
        debug: bool = False,
        verbose: bool = False,
        **generation_args: Any
    ) -> None:
        """
        Initialize an LLM client with the given configuration.
        
        Requires:
            - base_url: A valid API endpoint URL
            - model_name: A valid model identifier for the service
            - api_key: If required, a valid API key for the service
            
        Ensures:
            - Sets up environment variables for API access
            - Initializes appropriate client based on completion_mode
            - Creates TokenCounter for usage tracking
            - Stores generation parameters for use with LLM calls
            
        Raises:
            - Various initialization errors depending on client type and parameters
        """
        os.environ[ "OPENAI_API_KEY" ]  = api_key or "EMPTY"
        os.environ[ "OPENAI_BASE_URL" ] = base_url
        
        self.model_name      = model_name
        self.completion_mode = completion_mode
        self.prompt_format   = prompt_format
        self.token_counter   = TokenCounter( model_tokenizer_map )
        self.generation_args = generation_args
        self.debug           = debug
        self.verbose         = verbose
        
        if completion_mode:
            if self.debug:
                du.print_banner( f"TODO: Fetch COMPLETION style prompt formatter HERE", prepend_nl=True, expletive=True, chunk="¿?"  )
                print( f"¿? '{model_name}'" )
                print( f"Using LlmCompletion with prompt_format: '{prompt_format}'" )
            self.model = LlmCompletion( base_url=base_url, model_name=model_name, api_key=api_key, **generation_args )
        else:
            # For normal chat mode, use the Agent class
            # if self.debug: print( f"Using Agent with model: 'openai:{model_name}'" )
            du.print_banner( f"TODO: fetch and set system prompt HERE! for model 'openai:{model_name}'", prepend_nl=True, expletive=True )
            self.model = Agent( f"openai:{model_name}", **generation_args )
    
    async def _stream_async( self, prompt: str, **generation_args: Any ) -> str:
        """
        Internal method to handle async streaming.
        
        This asynchronous method handles streaming responses from the LLM,
        capturing chunks as they arrive and returning the combined result.
        It works with both Agent (Chat) and LlmCompletion modes.
        
        Requires:
            - prompt: A non-empty string to send to the LLM
            - self.model: An initialized model with async streaming capability
            - self.completion_mode: Boolean indicating whether to use completion API
            
        Ensures:
            - Streams response chunks from the LLM
            - Displays progress if self.debug is True
            - Collects all chunks into a single response
            - Handles both chat and completion API formats
            
        Returns:
            - Complete response string from the LLM
        """
        output = [ ]
        
        if self.completion_mode:
            # Use run_stream for LlmCompletion
            async with self.model.run_stream( prompt, **generation_args ) as result:
                # Stream text as deltas
                counter = 0
                async for chunk in result.stream_text( delta=True ):
                    if self.debug:
                        print( chunk, end="", flush=True )
                    else:
                        counter += 1
                        if counter % 128 == 0: print()
                        print( ".", end="", flush=True )
                    output.append( chunk )
        else:
            # Use run_stream for Agent (Chat)
            async with self.model.run_stream( prompt, **generation_args ) as result:
                # Stream text as deltas
                async for chunk in result.stream_text( delta=True ):
                    counter = 0
                    if self.debug:
                        print( chunk, end="", flush=True )
                    else:
                        counter += 1
                        if counter % 128 == 0: print()
                        print( ".", end="", flush=True )
                    output.append( chunk )
        
        return "".join( output )
    
    def run( self, prompt: str, stream: bool=False, **kwargs: Any ) -> str:
        """
        Send a prompt to the LLM and get the response.
        
        This is the main method for interacting with the LLM. It handles both
        streaming and non-streaming responses, measures performance metrics,
        and provides debugging information.
        
        Requires:
            - prompt: A non-empty string to send to the LLM
            - self.model: An initialized model with run capability
            - self.token_counter: An initialized TokenCounter
            
        Ensures:
            - Sends the prompt to the LLM and receives a response
            - Counts tokens for both prompt and completion
            - Measures performance metrics (duration, tokens/sec)
            - Handles both streaming and non-streaming modes
            - Displays performance metrics
            
        Args:
            - prompt: The text to send to the LLM
            - stream: Whether to stream the response (default: False)
            
        Returns:
            - String response from the LLM
            
        TODO:
            - Add support for distinguishing between system and user messages
            - Improve handling of chat vs completion formats
            - Develop more sophisticated message history management
        """
        
        prompt_tokens = self.token_counter.count_tokens( self.model_name, prompt )
        
        # update generation arguments
        if self.debug: print( "Updating generation arguments..." )
        updated_gen_args = {
            "temperature": kwargs.get( "temperature", self.generation_args.get( "temperature", 0.7 ) ),
            "max_tokens" : kwargs.get( "max_tokens", self.generation_args.get( "max_tokens", 64 ) ),
            "stop"       : kwargs.get( "stop", self.generation_args.get( "stop", None ) ),
            "top_p"      : kwargs.get( "top_p", self.generation_args.get( "top_p", 1.0 ) ),
            # Allow stream to be set from generation_args if not explicitly provided
            "stream"     : stream or self.generation_args.get( "stream", False ),
        }
        # Check both the explicit parameter and the updated_gen_args
        if not updated_gen_args["stream"]:
            
            # Add timing for non-streaming mode too
            start_time = time.perf_counter()
            
            if not self.completion_mode:
                # For Agent, use run_sync for synchronous operation
                response = self.model.run_sync( prompt, **updated_gen_args ).data
            else:
                # For OpenAIModel, use run
                response = self.model.run( prompt, **updated_gen_args )
            
            duration = time.perf_counter() - start_time
            completion_tokens = self.token_counter.count_tokens( self.model_name, response )
            if self.debug and self.verbose: self._print_metadata( prompt_tokens, completion_tokens, duration=duration )
            return response
        
        # Streaming mode
        output = ""
        print( f"🔄 Streaming from model: {self.model_name}\n" )
        start_time = time.perf_counter()
        
        # Need to use asyncio to handle the async streaming API
        import asyncio
        try:
            # Get or create an event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create a new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop( loop )
        
        output = loop.run_until_complete( self._stream_async( prompt, **updated_gen_args ) )
        
        duration = time.perf_counter() - start_time
        completion_tokens = self.token_counter.count_tokens( self.model_name, output )
        
        if self.debug and self.verbose: self._print_metadata( prompt_tokens, completion_tokens, duration )
        return output
    
    def _format_duration( self, seconds: float ) -> str:
        """
        Format a duration in seconds to a readable string.
        
        Requires:
            - seconds: A float representing seconds
            
        Ensures:
            - Returns a formatted string in milliseconds
            
        Returns:
            - String in the format "XXXms"
        """
        # return f"{seconds:.3f}" if seconds > 1 else f"{seconds * 1000:.3f} ms"
        return f"{int( seconds * 1000 )}ms"
    
    def _print_metadata( self, prompt_tokens: int, completion_tokens: int, duration: Optional[ float ] ):
        """
        Print performance metadata about an LLM request.
        
        This method calculates and displays key metrics about the LLM interaction,
        including token counts, duration, and tokens per second.
        
        Requires:
            - prompt_tokens: Integer count of tokens in the prompt
            - completion_tokens: Integer count of tokens in the completion
            - duration: Float representing seconds taken, or None
            
        Ensures:
            - Calculates total tokens and tokens per second
            - Formats duration appropriately
            - Displays a formatted summary of metrics
            
        TODO:
            - Add cost estimation based on token usage and model pricing
            - Implement more detailed performance metrics
            - Add optional logging to file for performance tracking
            - Fix potential division by zero issues in TPS calculation
            - Support different output formats (JSON, CSV, etc.)
        """
        
        total_tokens = prompt_tokens + completion_tokens
        tps = completion_tokens / duration if (duration and duration > 0) else float( 'inf' )
        duration_str = self._format_duration( duration ) if duration is not None else "N/A"
        
        du.print_banner( "📊 Stream Summary", prepend_nl=True )
        print( f"🧠 Model              : {self.model_name}" )
        print( f"⏱️ Duration           : {duration_str}" )
        print( f"🔢 Prompt tokens      : {prompt_tokens}" )
        print( f"💬 Completion tokens  : {completion_tokens}" )
        print( f"🧮 Total tokens       : {total_tokens}" )
        print( f"⚡ Tokens/sec          : {tps:.2f}" )
        print( "=" * 40 )


if __name__ == "__main__":
    
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/vox-command-template-completion-mistral-8b.txt" )
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt" )
    prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/date-and-time.txt" )
    # prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agents/date-and-time-reasoner.txt" )
    
    # voice_command = "can I please talk to a human?"
    question = "What time is it?"
    # prompt = prompt_template.format( voice_command=voice_command )
    prompt = prompt_template.format( question=question )
    
    # model_name = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
    # model_name = "/mnt/DATA01/include/www.deepily.ai/projects/models/OpenCodeReasoning-Nemotron-14B-autoround-4-bits-sym.gptq/2025-05-12-at-21-15"
    model_name = "kaitchup/Phi-4-AutoRound-GPTQ-4bit"
    # base_url   = "http://192.168.1.21:3000/v1/completions"
    base_url   = "http://192.168.1.21:3001/v1/completions"
    client = LlmClient( base_url=base_url, model_name=model_name, completion_mode=True, debug=True, verbose=True )

    # model_name = LlmClient.GROQ_LLAMA3_1_8B
    # client = LlmClient( model_name=model_name )
    
    response = client.run( prompt, stream=True, **{ "temperature": 0.25, "max_tokens": 7500 } )
    # response = client.run( prompt, stream=False, **{ "temperature": 1.0, "max_tokens": 1000, "stop": [ "foo" ] } )
    du.print_banner( "Response", prepend_nl=True )
    print( response )
    
    # model_name = "kaitchup/Phi-4-AutoRound-GPTQ-4bit"
    # base_url   = "http://192.168.1.21:3001/v1"
    # client = LlmClient( base_url=base_url, model_name=model_name )
    # prompt = "how many 'R's are there in the word strawberry?"
    # # prompt = "what's the square root of 144? Please think out loud about how you going to answer this question before you actually do, and show your thinking before you do"
    # response = client.run( prompt, stream=True )
    # print( f"Response: {response}" )