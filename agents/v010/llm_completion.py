import os
from typing import Optional, Dict, List, Union, Any

import requests
import json

import cosa.utils.util as du
from cosa.agents.v010.token_counter import TokenCounter
from cosa.utils.util_stopwatch import Stopwatch

class LlmCompletion:
    """
    Client for interacting with LLM completion APIs.
    
    This class provides a simplified interface for making completion requests
    to LLM APIs that follow the OpenAI-compatible completions format.
    
    Requires:
        - Valid base_url for a completions API endpoint
        - Valid model_name compatible with the API
        - TokenCounter for tracking token usage
        
    Ensures:
        - Makes HTTP requests to the completions API
        - Formats requests according to the completions API spec
        - Processes responses into usable text output
        - Provides performance metrics
    """
    
    def __init__( self,
        base_url: str = "http://192.168.1.21:3000/v1/completions",
        model_name: str = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27",
        api_key: Optional[ str ] = "EMPTY",
        model_tokenizer_map: Optional[ Dict[str, str] ] = None,
        debug: bool = False,
        verbose: bool = False,
        **generation_args: Any
    ):
        """
        Initialize a completion API client.
        
        Requires:
            - base_url: A valid URL for an OpenAI-compatible completions API
            - model_name: A valid model name or path
            
        Ensures:
            - Sets up client configuration for API requests
            - Initializes TokenCounter for token counting
            - Stores generation parameters
            
        Args:
            base_url: URL of the completions API endpoint
            model_name: Name or path of the model to use
            api_key: Optional API key for authentication
            model_tokenizer_map: Optional mapping from model to tokenizer names
            debug: Enable debug output
            verbose: Enable verbose output
            **generation_args: Additional arguments for generation
        """
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.token_counter = TokenCounter( model_tokenizer_map )
        self.generation_args = generation_args
        self.debug = debug
        self.verbose = verbose
        self.generation_args = generation_args

    def run( self, prompt: str, stream: bool=False, **kwargs: Any ) -> str:
        """
        Send a prompt to the LLM and get a completion response.
        
        This method sends a request to the completions API and processes
        the response. It handles timing, token counting, and error handling.
        
        Requires:
            - prompt: A non-empty string to send to the LLM
            - self.base_url: A valid API endpoint URL
            - self.model_name: A valid model name or path
            
        Ensures:
            - Sends a properly formatted request to the completions API
            - Measures performance metrics
            - Processes and returns the response text
            - Provides debug information if enabled
            
        Raises:
            - NotImplementedError if streaming is requested
            - May raise HTTP exceptions for API errors
            
        Args:
            prompt: The text prompt to send to the LLM
            stream: Whether to stream the response (not implemented)
            **generation_args: Additional arguments for generation
            
        Returns:
            String response from the LLM
        """
        
        if stream:
            raise NotImplementedError( "Streaming not implemented for this client" )
        
        headers = {
            'Content-Type' : 'application/json',
            # 'Authorization': f'Bearer {api_key}',
        }
        
        # Request a completion
        data = {
            "model"      : self.model_name,
            "prompt"     : prompt,
            # override the object's generation arguments if they're present in this method's kwargs
            "max_tokens" : kwargs.get( "max_tokens", self.generation_args.get( "max_tokens", 64 ) ),
            "temperature": kwargs.get( "temperature", self.generation_args.get( "temperature", 0.25 ) ),
            "top_p"      : kwargs.get( "top_p", self.generation_args.get( "top_p", 1.0 ) ),
            "stop"       : kwargs.get( "stop", self.generation_args.get( "stop", None ) ),
        }
        timer    = Stopwatch( msg="Requesting completion..." )
        response = requests.post( self.base_url, headers=headers, data=json.dumps( data ) )
        timer.print( msg="Done!", use_millis=True )
        
        if response.status_code == 200:
            completion = response.json()
            return completion[ 'choices' ][ 0 ][ 'text' ].replace( "```", "" ).strip()
        else:
            print( f"Error: {response.status_code}" )
            raise Exception( f"Error requesting completion: {response.text}" )


if __name__ == "__main__":
    
    # url = "http://192.168.1.21:3000/v1/completions"
    
    # template_path = du.get_project_root() + "/src/conf/prompts/vox-command-template-completion-mistral-8b.txt"
    template_path = du.get_project_root() + "/src/conf/prompts/agent-router-template-completion.txt"
    # template_path = du.get_project_root() + "/src/conf/prompts/vox-command-template-completion.txt"
    prompt_template = du.get_file_as_string( template_path )
    
    # voice_command = "I want you to open a new tab and do a Google scholar search on agentic behaviors"
    # voice_command = "ask perplexity for best homemade corn tortilla recipes"
    voice_command = "can I please talk to a human?"

    prompt = prompt_template.format( voice_command=voice_command )
    print( prompt )
    
    llm_completion = LlmCompletion()
    response = llm_completion.run( prompt )
    print( response )