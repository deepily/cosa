import requests
import json

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch

def get_completion(
    prompt,
    url="http://192.168.1.21:3000/v1/completions",
    model="/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
):
    
    headers = {
        'Content-Type' : 'application/json',
        # 'Authorization': f'Bearer {api_key}',
    }
    
    # Request a completion
    data = {
        "model": model,
        "prompt": prompt,
        "max_tokens": 64,
        "temperature": 0.25,
    }
    timer = Stopwatch( msg="Requesting completion..." )
    response = requests.post( url, headers=headers, data=json.dumps( data ) )
    timer.print( msg="Done!", use_millis=True )
    
    if response.status_code == 200:
        completion = response.json()
        return completion[ 'choices' ][ 0 ][ 'text' ].replace( "```", "" ).strip()
    else:
        print( f"Error: {response.status_code}" )
        raise Exception( f"Error requesting completion: {response.text}" )
    

if __name__ == "__main__":
    
    # url = "http://192.168.1.21:3000/v1/completions"
    
    prompt_template = du.get_file_as_string( du.get_project_root() + "/src/conf/prompts/vox-command-template-completion-mistral-8b.txt" )
    # voice_command = "I want you to open a new tab and do a Google scholar search on agentic behaviors"
    voice_command = "ask perplexity for best homemade corn tortilla recipes"
    prompt = prompt_template.format( voice_command=voice_command )
    print( prompt )
    
    response = get_completion( prompt )
    print( response )