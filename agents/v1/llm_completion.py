import os
from typing import Optional

import requests
import json

import cosa.utils.util as du
from cosa.agents.v1.token_counter import TokenCounter
from cosa.utils.util_stopwatch import Stopwatch

class LlmCompletion:
    
    def __init__( self,
        base_url: str = "http://192.168.1.21:3000/v1/completions",
        model_name: str = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27",
        api_key: Optional[ str ] = "EMPTY",
        model_tokenizer_map: Optional[ dict ] = None,
        debug = False,
        verbose = False,
        **generation_args
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.token_counter = TokenCounter( model_tokenizer_map )
        self.generation_args = generation_args
        self.debug = debug
        self.verbose = verbose
        self.generation_args = generation_args

    def run( self, prompt: str, stream: bool = False ) -> str:
        
        if stream:
            raise NotImplementedError( "Streaming not implemented for this client" )
        
        headers = {
            'Content-Type' : 'application/json',
            # 'Authorization': f'Bearer {api_key}',
        }
        
        # Request a completion
        data = {
            "model": self.model_name,
            "prompt": prompt,
            # TODO: add support for generation arguments
            "max_tokens": 64,
            "temperature": 0.25,
        }
        timer = Stopwatch( msg="Requesting completion..." )
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