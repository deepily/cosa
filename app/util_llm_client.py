import re

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch

def query_llm_in_memory( model, tokenizer, prompt, device="cuda:0", model_name="ACME LLMs, Inc.", max_new_tokens=128, silent=False, debug=False, verbose=False ):

    timer = Stopwatch( msg=f"Asking LLM [{model_name}]...".format( model_name ), silent=silent )
    
    inputs        = tokenizer( prompt, return_tensors="pt" ).to( device )
    stop_token_id = tokenizer.encode( "</response>" )[ 0 ]
    
    du.print_banner( "Stop Token IDs " )
    print( stop_token_id )
    
    generation_output = model.generate(
        input_ids=inputs[ "input_ids" ],
        attention_mask=inputs[ "attention_mask" ],
        max_new_tokens=max_new_tokens,
        eos_token_id=stop_token_id,
        pad_token_id=stop_token_id
    )
    
    # Skip decoding the prompt part of the output
    input_length = inputs[ "input_ids" ].size( 1 )
    raw_response   = tokenizer.decode( generation_output[ 0 ][ input_length: ] )
    
    timer.print( msg="Done!", use_millis=True, end="\n" )
    seconds = timer.get_delta_ms() / 1000.0
    tokens_per_second = len( generation_output[ 0 ][ input_length: ] ) / seconds
    print( f"Tokens per second [{round( tokens_per_second, 1 )}] input tokens [{input_length}] + xml response tokens [{len( generation_output[ 0 ][ input_length: ] )}] = total tokens i/o [{len( generation_output[ 0 ] )}]" )
    
    if debug and verbose:
        du.print_banner( "Raw response" )
        print( raw_response )
    
    # Remove the <s> and </s> tags
    response = raw_response.replace( "</s><s>", "" ).strip()
    # Remove white space outside XML tags
    response = re.sub( r'>\s+<', '><', response )
    
    return response