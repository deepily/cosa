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
    
    def __init__( self, model_name: str, local_files_only: bool=True, device_map: str="auto" ) -> None:
        """
        Initialize a new Quantizer instance for model quantization.
        
        Requires:
            - model_name is a valid HuggingFace model identifier or local path
            - local_files_only is a boolean flag indicating whether to use only local files
            - device_map is a valid device mapping strategy string
            
        Ensures:
            - Model and tokenizer are loaded from the specified source
            - Default quantization settings are established (4-bit, autoround method, symmetrical)
            
        Raises:
            - ValueError if model_name is invalid or model not found
            - RuntimeError if model loading fails due to resource constraints
        """
        self.model_name      = model_name
        self.model           = AutoModelForCausalLM.from_pretrained( model_name, torch_dtype=torch.float16, local_files_only=local_files_only, device_map=device_map )
        self.tokenizer       = AutoTokenizer.from_pretrained( model_name, local_files_only=local_files_only )
        self.bits            = 4
        self.quantize_method = "autoround"
        self.symmetrical     = True
        
    def quantize_model( self, quantize_method: str="autoround", batch_size: int=1, bits: int=4, group_size: int=128, sym: bool=True ) -> None:
        """
        Quantize the loaded model using the specified parameters.
        
        Requires:
            - The model and tokenizer have been successfully loaded in __init__
            - quantize_method is a supported quantization method (currently only "autoround")
            - batch_size is a positive integer
            - bits is a positive integer representing quantization precision (typically 2, 3, 4, or 8)
            - group_size is a positive integer for quantization grouping
            - sym is a boolean indicating whether to use symmetric quantization
            
        Ensures:
            - Model is quantized according to specified parameters
            - self.autoround is initialized with appropriate configuration
            - self.bits, self.quantize_method, and self.symmetrical are updated
            
        Raises:
            - Exception if an unsupported quantization method is provided
            - Various exceptions from the AutoRound process if quantization fails
        """
        self.bits            = bits
        self.quantize_method = quantize_method
        self.symmetrical     = sym
        
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
        
    def save( self, output_dir: str, include_model_name: bool=True, format: str='auto_gptq', inplace: bool=True ) -> str:
        """
        Save the quantized model to disk with appropriate naming conventions.
        
        Requires:
            - Model has been successfully quantized via quantize_model()
            - output_dir is a valid directory path (will be created if it doesn't exist)
            - include_model_name is a boolean indicating whether to include the model name in the output path
            - format is a valid export format (currently only 'auto_gptq' is fully supported)
            - inplace is a boolean indicating whether to modify the model in-place
            
        Ensures:
            - Creates a uniquely named directory with timestamp
            - Saves the quantized model to the specified location
            - Returns the full path to the saved model directory
            
        Raises:
            - IOError if directory creation fails
            - Various exceptions from the AutoRound save process if saving fails
            - Exception if autoround hasn't been initialized (if quantize_model wasn't called)
        """
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
        
    model_name: str = sys.argv[ 1 ]
    save_to_path: str = sys.argv[ 2 ]
    
    # check if bits is provided, if not default to 4
    if len( sys.argv ) == 4:
        bits: int = int( sys.argv[ 3 ] )
    else:
        bits: int = 4
    
    quantizer = Quantizer( model_name )
    quantizer.quantize_model( bits=bits )
    quantizer.save( save_to_path, include_model_name=True )
    