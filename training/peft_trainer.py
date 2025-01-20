import sys
import torch, os, multiprocessing
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    set_seed
)
from trl import SFTTrainer, SFTConfig
set_seed(1234)

class PeftTrainer():
    
    def __init__( self, model_name, local_files_only=True ):
        
        self.model_name = model_name
        self.model = AutoModelForCausalLM.from_pretrained( model_name, local_files_only=local_files_only )
        self.tokenizer = AutoTokenizer.from_pretrained( model_name, local_files_only=local_files_only )
        self.bits = 4
        self.quantize_method = "autoround"
        self.symmetrical = True
        
    
if __name__ == "__main__":
    
    # sanity check for command line arguments
    if len( sys.argv ) != 2:
        print( "Usage: python peft_trainer.py <repo_id>" )
        sys.exit( 1 )
    # sanity check for huggingface home
    if not os.getenv( "HF_HOME" ):
        print( "Please set the HF_HOME environment variable to the directory where you want to download models" )
        sys.exit( 1 )
        
    # Authenticate with Hugging Face
    hf_token = os.getenv( "HF_TOKEN" )
    if not hf_token:
        print( "Please set the HF_TOKEN environment variable with your Hugging Face API token" )
        sys.exit( 1 )
    
    repo_id = sys.argv[ 1 ]
    downloader = HuggingFaceDownloader( token=hf_token )
    downloader.download_model( repo_id )
    
    model_name = "EleutherAI/gpt-neo-2.7B"
    trainer = PeftTrainer( model_name )
    trainer.train()
    trainer.save( output_dir="output", format='auto_gptq', inplace=True )
    
    
