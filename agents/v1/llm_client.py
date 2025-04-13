import os
import time
import asyncio
from typing import Optional

from boto3 import client
from openai import base_url

import cosa.utils.util as du
from cosa.agents.v1.llm_completion import LlmCompletion

from cosa.agents.v1.token_counter import TokenCounter

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from cosa.app.configuration_manager import ConfigurationManager


class LlmClient:
    
    DEEPILY_MINISTRAL_8B_2410   = "llm_deepily_ministral_8b_2410"
    PHI_4_14B                   = "llm_deepily_phi_4_14b"
    GROQ_LLAMA_3_1_8B           = "groq:llama-3.1-8b-instant"
    GROQ_LLAMA_3_1_70B          = "groq:llama-3.1-70b-versatile"
    OPENAI_GPT_4o_MINI          = "openai:gpt-4o-mini"
    GOOGLE_GEMINI_1_5_FLASH     = "google-gla:gemini-1.5-flash"
    ANTHROPIC_CLAUDE_SONNET_3_5 = "anthropic:claude-3-5-sonnet-latest"
    
    # QWEN_2_5_32B = "kaitchup/Qwen2.5-Coder-32B-Instruct-AutoRound-GPTQ-4bit"
    
    
    def __init__( self,
        
        base_url: str = "http://192.168.1.21:3001/v1",
        model_name: str = "F00",
        completion_mode: bool = False,
        api_key: Optional[ str ] = "EMPTY",
        model_tokenizer_map: Optional[ dict ] = None,
        debug=False,
        verbose=False,
        **generation_args
    ):
        os.environ[ "OPENAI_API_KEY" ]  = api_key or "EMPTY"
        os.environ[ "OPENAI_BASE_URL" ] = base_url
        
        self.model_name      = model_name
        self.completion_mode = completion_mode
        self.token_counter   = TokenCounter( model_tokenizer_map )
        self.generation_args = generation_args
        self.debug           = debug
        self.verbose         = verbose
        
        if completion_mode:
            self.model = LlmCompletion( base_url=base_url, model_name=model_name, api_key=api_key, **generation_args )
        else:
            # For normal chat mode, use the Agent class
            if self.debug: print( f"Using Agent with model: {model_name}" )
            self.model = Agent( f"openai:{model_name}", **generation_args )
    
    async def _stream_async( self, prompt: str ):
        """
        Internal method to handle async streaming.
        """
        output = [ ]
        
        # Use run_stream which returns a context manager for streaming
        async with self.model.run_stream( prompt ) as result:
            # Stream text as deltas
            async for chunk in result.stream_text( delta=True ):
                if self.debug:
                    print( chunk, end="", flush=True )
                else:
                    print( ".", end="", flush=True )
                output.append( chunk )
        
        return "".join( output )
    
    def run( self, prompt: str, stream: bool=False ) -> str:
        
        prompt_tokens = self.token_counter.count_tokens( self.model_name, prompt )
        
        if not stream:
            # Add timing for non-streaming mode too
            start_time = time.perf_counter()
            
            if not self.completion_mode:
                # For Agent, use run_sync for synchronous operation
                response = self.model.run_sync( prompt ).data
            else:
                # For OpenAIModel, use run
                response = self.model.run( prompt )
            
            duration = time.perf_counter() - start_time
            completion_tokens = self.token_counter.count_tokens( self.model_name, response )
            self._print_metadata( prompt_tokens, completion_tokens, duration=duration )
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
        
        output = loop.run_until_complete( self._stream_async( prompt ) )
        
        duration = time.perf_counter() - start_time
        completion_tokens = self.token_counter.count_tokens( self.model_name, output )
        
        self._print_metadata( prompt_tokens, completion_tokens, duration )
        return output
    
    def _format_duration( self, seconds: float ) -> str:
        
        # return f"{seconds:.3f}" if seconds > 1 else f"{seconds * 1000:.3f} ms"
        return f"{int( seconds * 1000 )}ms"
    
    def _print_metadata( self, prompt_tokens: int, completion_tokens: int, duration: Optional[ float ] ):
        
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
    prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt" )
    
    voice_command = "can I please talk to a human?"
    prompt = prompt_template.format( voice_command=voice_command )

    model_name = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
    base_url   = "http://192.168.1.21:3000/v1/completions"
    client = LlmClient( base_url=base_url, model_name=model_name, completion_mode=True )

    # model_name = LlmClient.GROQ_LLAMA3_1_8B
    # client = LlmClient( model_name=model_name )
    
    response = client.run( prompt, stream=False )
    print( f"Response: {response}" )
    
    # model_name = "kaitchup/Phi-4-AutoRound-GPTQ-4bit"
    # base_url   = "http://192.168.1.21:3001/v1"
    # client = LlmClient( base_url=base_url, model_name=model_name )
    # prompt = "how many 'R's are there in the word strawberry?"
    # # prompt = "what's the square root of 144? Please think out loud about how you going to answer this question before you actually do, and show your thinking before you do"
    # response = client.run( prompt, stream=True )
    # print( f"Response: {response}" )