import sys
import json

import torch, os, multiprocessing
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    set_seed
)
from datasets import Dataset
from trl import SFTTrainer, SFTConfig
from auto_round import AutoRoundConfig

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch

set_seed( 42 )

class PeftTrainer():
    
    def __init__( self, path_to_quantized_model, model_name, test_train_path ):
        
        du.print_banner( f"Initializing PEFT Trainer for {model_name}" )
        print( f"Path to quantized model: {path_to_quantized_model}" )
        print( f"Path to test/train data: {test_train_path}" )
        
        self.path_to_quantized_model = path_to_quantized_model
        self.model_name = model_name
        self.test_train_dir = test_train_path
        
        # stats tracking
        self.start_gpu_memory = -1
        self.max_memory       = -1
        
    def fine_tune( self, batch_size=8, gradient_accumulation_steps=32, backend="cuda", sample_size=1.0, device_map="auto" ):
        
        du.print_banner( f"Fine-tuning model {self.model_name} with PEFT", prepend_nl=True )
        run_start = f"Run started @ {du.get_current_time( format='%H:%M' )}"
        print( run_start )
        timer = Stopwatch( msg=None )
        
        compute_dtype       = torch.bfloat16
        attn_implementation = 'flash_attention_2'
        quantization_config = AutoRoundConfig( backend=backend )
        
        self.model = AutoModelForCausalLM.from_pretrained(
            self.path_to_quantized_model,
            # device_map="auto", # distributed training
            device_map=device_map, # {"": 0} = single GPU
            quantization_config=quantization_config,
            attn_implementation=attn_implementation
        )
        tokenizer = AutoTokenizer.from_pretrained( self.path_to_quantized_model )
        tokenizer.pad_token = "<|finetune_right_pad_id|>"
        tokenizer.pad_token_id = 128004
        tokenizer.padding_side = 'right'
        
        self.model         = prepare_model_for_kbit_training( self.model, gradient_checkpointing_kwargs={ 'use_reentrant': True } )
        peft_config        = self._get_peft_config()
        training_arguments = self._get_training_args( output_dir="peft-output", batch_size=batch_size, gradient_accumulation_steps=gradient_accumulation_steps )
        test_train_data    = self._get_test_train_data( sample_size=sample_size)
        
        self.trainer = SFTTrainer(
            # workaround for buggy safe tensors behavior a model is loaded across multiple GPUs
            # save_safetensors=False,
            model=self.model,
            train_dataset=test_train_data[ "train" ],
            eval_dataset=test_train_data[ "test" ],
            peft_config=peft_config,
            processing_class=tokenizer,
            args=training_arguments,
            # formatting_func=self._prompt_instruction_format,
        )
        
        self._print_trainable_parameters()
        self._print_stats_pre()
        self.trainer.train()
        self._print_stats_post()
        print( run_start )
        print( f"Run completed @ {du.get_current_time( format='%H:%M' )}")
        timer.print( msg=None )
      
    def save_adapter( self, output_dir ):
        
        date = du.get_current_date()
        time = du.get_current_time( format='%H-%M', include_timezone=False )
        path = f"{output_dir}/{date}-at-{time}"
        if not os.path.exists( path ):
            print( f"Creating output directory {path}..." )
            os.makedirs( path )
            print( f"Creating output directory {path}... Done!" )
            
        # change directory to save adapter
        os.chdir( path )
        print( f"Saving adapter to {path}..." )
        self.model.save_pretrained( output_dir, safe_serialization=False )
        print( f"Saving adapter to {path}... Done!" )
        
    def _get_peft_config( self ):
        
        return LoraConfig(
            lora_alpha=16,
            lora_dropout=0.05,
            r=16,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[ 'k_proj', 'q_proj', 'v_proj', 'o_proj', "gate_proj", "down_proj", "up_proj" ]
        )
    
    def _get_training_args( self, output_dir="peft-output", batch_size=8, gradient_accumulation_steps=32 ):
        return SFTConfig(
            output_dir=output_dir,
            eval_strategy="steps",
            do_eval=True,
            optim="adamw_8bit",
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            per_device_eval_batch_size=batch_size,
            log_level="debug",
            save_strategy="epoch",
            logging_steps=25,
            learning_rate=1e-5,
            bf16=True,
            eval_steps=25,
            num_train_epochs=1,
            warmup_ratio=0.1,
            lr_scheduler_type="linear",
            dataset_text_field="text",
            max_seq_length=512,
        )
    
    def _get_test_train_data( self, sample_size=1.0 ):
        
        path = self.test_train_dir + "/voice-commands-xml-train.jsonl"
        train_dataset = du.get_file_as_list( path )
        # retain a sample of the data set expressed as a percentage
        if sample_size < 1.0:
            train_dataset = train_dataset[ : int( len( train_dataset ) * sample_size ) ]
        train_dataset = [ json.loads( line )[ "gpt_message" ] for line in train_dataset ]
        print( f"Loaded {len( train_dataset )} training items" )
        train_dataset = Dataset.from_list( train_dataset )
        
        path = self.test_train_dir + "/voice-commands-xml-test.jsonl"
        test_dataset = du.get_file_as_list( path )
        # retain a sample of the data set expressed as a percentage
        if sample_size < 1.0:
            test_dataset = test_dataset[ : int( len( test_dataset ) * sample_size ) ]
        test_dataset = [ json.loads( line )[ "gpt_message" ] for line in test_dataset ]
        print( f"Loaded {len( test_dataset )} test items" )
        test_dataset = Dataset.from_list( test_dataset )
        
        return { 'train': train_dataset, 'test': test_dataset }
        
    def _prompt_instruction_format( sample ):
    
        return f"""### Instruction:
        Use the Task below and the Input given to write a Response that can solve the following Task:
        
        ### Task:
        {sample['instruction']}
        
        ### Input:
        {sample['input']}
        
        ### Response:
        {sample['output']}
        """
    
    def _print_trainable_parameters( self ):
        """
        Prints the number of trainable parameters in the model.
        """
        trainable_params = 0
        all_param = 0
        for _, param in self.model.named_parameters():
            all_param += param.numel()
            if param.requires_grad:
                trainable_params += param.numel()
        print(
            f"trainable params: {trainable_params:,} || all params: {all_param:,} || trainable%: {100 * trainable_params / all_param:.2f}"
        )

    def _print_stats_pre( self ):
        
        gpu_stats = torch.cuda.get_device_properties( 0 )
        self.start_gpu_memory = round( torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3 )
        self.max_memory = round( gpu_stats.total_memory / 1024 / 1024 / 1024, 3 )
        print( f"GPU = {gpu_stats.name}. Max memory = {self.max_memory} GB." )
        print( f"{self.start_gpu_memory} GB of memory reserved." )
        
    def _print_stats_post( self ):
        
        used_memory = round( torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3 )
        used_memory_for_trainer = round( used_memory - self.start_gpu_memory, 3 )
        used_percentage = round( used_memory / self.max_memory * 100, 3 )
        trainer_percentage = round( used_memory_for_trainer / self.max_memory * 100, 3 )
        # print( f"{self.trainer.metrics[ 'train_runtime' ]} seconds used for training." )
        # print( f"{round( self.trainer.metrics[ 'train_runtime' ] / 60, 2 )} minutes used for training." )
        print( f"Peak reserved memory = {used_memory} GB." )
        print( f"Peak reserved memory for training = {used_memory_for_trainer} GB." )
        print( f"Peak reserved memory % of max memory = {used_percentage} %." )
        print( f"Peak reserved memory for training % of max memory = {trainer_percentage} %." )
       
        # error thrown when referencing metrics field:
        # File "/mnt/DATA01/include/www.deepily.ai/projects/genie-in-the-box/src/cosa/training/peft_trainer.py", line 171, in _print_stats_post
        # print( f"{self.trainer.metrics[ 'train_runtime' ]} seconds used for training." )
        #           ^^^^^^^^^^^^^^^^^^^^
        # AttributeError: 'SFTTrainer' object has no attribute 'metrics'
       
    
def suss_out_dataset():
    
    path = "/mnt/DATA01/include/www.deepily.ai/projects/genie-in-the-box/src/ephemera/prompts/data/voice-commands-xml-train.jsonl"
    train_dataset = du.get_file_as_list( path )
    train_dataset = [ json.loads( line )[ "gpt_message" ] for line in train_dataset ]
    print( f"Loaded {len( train_dataset )} training items" )
    
    # for i in range( 10 ):
    print( train_dataset[ 0 ] )
    
    train_dataset = Dataset.from_list( train_dataset )
    print( train_dataset[ 0 ] )
    
if __name__ == "__main__":
    
    # suss_out_dataset()
    # sanity check for command line arguments
    if len( sys.argv ) != 5:
        print( "Usage: python peft_trainer.py <path_to_quantized_model> <model_name> <test_train_path> <lora_dir>" )
        sys.exit( 1 )
    # sanity check for environment variables
    if not os.getenv( "NCCL_P2P_DISABLE" ):
        print( "Please set env variable NCCL_P2P_DISABLE=1" )
        sys.exit( 1 )
    if not os.getenv( "NCCL_IB_DISABLE" ):
        print( "Please set env variable NCCL_IB_DISABLE=1" )
        sys.exit( 1 )
        
    path_to_quantized_model = sys.argv[ 1 ]
    model_name = sys.argv[ 2 ]
    test_train_path = sys.argv[ 3 ]
    lora_dir = sys.argv[ 4 ]
    
    trainer = PeftTrainer( path_to_quantized_model, model_name, test_train_path )
    trainer.fine_tune( batch_size=20, gradient_accumulation_steps=40 )
    trainer.save_adapter( lora_dir )
    
    # Wait 10 seconds before exiting
    os.system( "sleep 30" )
    
