import requests
import json

from huggingface_hub import InferenceClient

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch

import openai

def get_completion_by_requests( prompt, url ):
    
    headers = {
        'Content-Type' : 'application/json',
        # 'Authorization': f'Bearer {api_key}',
    }
    
    # Request a completion
    data = {
        "model": "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410/merged-00-2025-01-09.gptq",
        "prompt": prompt,
        "max_tokens": 32,
        "temperature": 0.25,
    }
    timer = Stopwatch( msg="Requesting completion..." )
    response = requests.post( url, headers=headers, data=json.dumps( data ) )
    timer.print( msg="Done!", use_millis=True )
    
    if response.status_code == 200:
        completion = response.json()
        return completion[ 'choices' ][ 0 ][ 'text' ]
    else:
        print( f"Error: {response.status_code}" )
        raise Exception( f"Error requesting completion: {response.text}" )
    
def get_completion_by_openai( prompt, api_key ):
    
    return None

# def get_completion_by_hfc( prompt, url, model_name="ACME LLMs, Inc.", max_new_tokens=1024, temperature=0.25, top_k=10,top_p=0.9, silent=False, debug=False, verbose=False ):
#
#     timer = Stopwatch( msg=f"Asking LLM [{model_name}]...".format( model_name ), silent=silent )
#
#     client = InferenceClient( url )
#     token_list = [ ]
#     ellipsis_count = 0
#
#     # if self.debug and self.verbose:
#     #     for line in prompt.split( "\n" ):
#     #         print( line )
#
#     for token in client.text_generation(
#             prompt, max_new_tokens=max_new_tokens, stream=True, temperature=temperature, top_k=top_k, top_p=top_p,
#             stop_sequences=[ "</response>" ]
#     ):
#         if debug:
#             print( token, end="" )
#         else:
#             if not silent: print( ".", end="" )
#             ellipsis_count += 1
#             if ellipsis_count == 120:
#                 ellipsis_count = 0
#                 print()
#
#         token_list.append( token )
#
#     response = "".join( token_list ).strip()
#
#     timer.print( msg="Done!", use_millis=True, prepend_nl=True, end="\n" )
#     tokens_per_second = len( token_list ) / (timer.get_delta_ms() / 1000.0)
#     print( f"Tokens per second [{round( tokens_per_second, 1 )}]" )
#
#     if debug:
#         print( f"Token list length [{len( token_list )}]" )
#         if verbose:
#             for line in response.split( "\n" ):
#                 print( line )
#
#     return response

if __name__ == "__main__":
    
    url = "http://192.168.1.21:3000/v1/completions"
    
    prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/vox-command-template.txt" )
    voice_command = "I want you to open a new tab and do a Google scholar search on agentic behaviors"
    prompt = prompt_template.format( voice_command=voice_command )
    print( prompt )
    
    response = get_completion_by_requests( prompt, url )
    # response = get_completion_by_hfc( prompt, url )
    print( response )