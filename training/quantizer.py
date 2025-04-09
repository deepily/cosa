import sys
import os

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from auto_round import AutoRound

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch


# make this a class called Quantizer
# with a method called quantize_model
class Quantizer:
    
    def __init__( self, model_name, local_files_only=True, device_map="auto" ):

        self.model_name = model_name
        self.model = AutoModelForCausalLM.from_pretrained( model_name, torch_dtype=torch.float16, local_files_only=local_files_only, device_map=device_map )
        self.tokenizer = AutoTokenizer.from_pretrained( model_name, local_files_only=local_files_only )
        self.bits = 4
        self.quantize_method = "autoround"
        self.symmetrical = True
        
    def quantize_model( self, quantize_method="autoround", batch_size=1, bits=4, group_size=128, sym=True ):
        
        self.bits = bits
        self.quantize_method = quantize_method
        self.symmetrical = sym
        
        if quantize_method == "autoround":
            self.autoround = AutoRound( self.model, self.tokenizer, nsamples=128, iters=512, low_gpu_mem_usage=True, batch_size=batch_size,
                gradient_accumulation_steps=8, bits=self.bits, group_size=group_size, sym=sym, enable_torch_compile=True  # Enable torch.compile optimizations
            )
        else:
            raise Exception( f"Unsupported quantization method: {quantize_method}" )
        
        du.print_banner( f"Quantizing model [{self.model_name}] with {self.quantize_method} method using {self.bits}-bits", prepend_nl=True )
        timer = Stopwatch( msg="Quantizing model..." )
        self.autoround.quantize()
        timer.print( msg="Done!" )
        
    def save( self, output_dir, include_model_name=True, format='auto_gptq', inplace=True ):
        
        extension  = "gptq" if format == "auto_gptq" else "unknown"
        sym_flag   = "sym"  if self.symmetrical else "asym"
        date       = du.get_current_date()
        time       = du.get_current_time( format='%H-%M', include_timezone=False )
        
        if include_model_name:
            full_path  = f"{output_dir}/{self.model_name.split( '/' )[ 1 ]}-{self.quantize_method}-{self.bits}-bits-{sym_flag}.{extension}/{date}-at-{time}"
        else:
            full_path  = f"{output_dir}/{self.quantize_method}-{self.bits}-bits-{sym_flag}.{extension}/{date}-at-{time}"
        
        # check to see if the path exists, if not create
        if not os.path.exists( full_path ):
            
            print( f"Creating output directory [{full_path}]..." )
            os.makedirs( full_path )
            print( f"Creating output directory [{full_path}]... Done!" )
        
        print( f"Saving quantized model to [{full_path}]..." )
        self.autoround.save_quantized( full_path, format=format, inplace=inplace )
        print( f"Saving quantized model to [{full_path}]... Done!" )
        
        return full_path

if __name__ == "__main__":
    
    # sanity check for command line arguments
    if len( sys.argv ) < 3:
        print( "Usage: python quantizer.py <model_name> <save_to_path> <bits>" )
        sys.exit( 1 )
        
    model_name   = sys.argv[ 1 ]
    save_to_path = sys.argv[ 2 ]
    
    # check if bits is provided, if not default to 4
    if len( sys.argv ) == 4:
        bits = int( sys.argv[ 3 ] )
    else:
        bits = 4
    
    quantizer = Quantizer( model_name )
    quantizer.quantize_model( bits=bits )
    quantizer.save( save_to_path, include_model_name=False )
    