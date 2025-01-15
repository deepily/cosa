import sys
import os

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from auto_round import AutoRound

import utils.util as du

# make this a class called Quantizer
# with a method called quantize_model
class Quantizer:
    
    def __init__( self, model_name, local_files_only=True ):

        self.model_name = model_name
        self.model = AutoModelForCausalLM.from_pretrained( model_name, torch_dtype=torch.float16, local_files_only=local_files_only )
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
                graddient_accumulation_steps=8, bits=self.bits, group_size=group_size, sym=sym
            )
        else:
            raise Exception( f"Unsupported quantization method: {quantize_method}" )
        
        du.print_banner( f"Quantizing model [{self.model_name}] with {self.quantize_method} method using {self.bits}-bits", prepend_newline=True )
        self.autoround.quantize()
        
    def save_quantized( self, output_dir, format='auto_gptq', inplace=True ):
        
        extension  = "gptq" if format == "auto_gptq" else format
        sym_flag   = "sym"  if self.symmetrical else "asym"
        output_dir = f"{output_dir}/{self.model_name.split( '/' )[ 1 ]}-{self.quantize_method}-{self.bits}-bits-{sym_flag}.{extension}/{du.get_current_date()}"
        
        # check to see if the path exists, if not create
        if not os.path.exists( output_dir ):
            print( f"Creating output directory [{output_dir}]..." )
            os.makedirs( output_dir )
            print( f"Creating output directory [{output_dir}]... Done!" )
            # make sure that this directory is world-readable?
            # os.chmod( output_dir, 0o755 )
        
        print( f"Saving quantized model to [{output_dir}]..." )
        self.autoround.save_quantized( output_dir, format=format, inplace=inplace )
        print( f"Saving quantized model to [{output_dir}]... Done!" )

if __name__ == "__main__":
    
    # sanity check for command line arguments
    if len( sys.argv ) != 3:
        print( "Usage: python quantizer.py <model_name> <save_to_path>" )
        sys.exit( 1 )
        
    model_name   = sys.argv[ 1 ]
    save_to_path = sys.argv[ 2 ]
    
    quantizer = Quantizer( model_name )
    quantizer.quantize_model()
    quantizer.save_quantized( save_to_path )
    