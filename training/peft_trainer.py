import sys
import json
import pandas as pd

import torch, os, multiprocessing
from IPython.core.debugger import prompt
from peft import LoraConfig, prepare_model_for_kbit_training, PeftModel

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    set_seed
)
from datasets import Dataset
from datasets.formatting.formatting import LazyBatch
from trl import SFTTrainer, SFTConfig
from auto_round import AutoRoundConfig

import cosa.utils.util as du
from cosa.utils.util_stopwatch import Stopwatch
from cosa.training.xml_fine_tuning_prompt_generator import XmlFineTuningPromptGenerator

set_seed( 42 )

class PeftTrainer:
    
    def __init__( self, path_to_quantized_model, model_name, test_train_path, padding_type="set-padding-type-HERE", completion_type="YOUR-COMPLETION-TYPE-HERE!", debug=False, verbose=False ):
        
        du.print_banner( f"Initializing PEFT Trainer for {model_name}" )
        print( f"Path to quantized model: {path_to_quantized_model}" )
        print( f"Path to test/train data: {test_train_path}" )
        
        self.debug                   = debug
        self.verbose                 = verbose
        self.trainer                 = None
        self.model                   = None
        self.tokenizer               = None
        self.output_dir              = None
        self.checkpoint_dir          = None
        self.path_to_quantized_model = path_to_quantized_model
        self.model_name              = model_name
        self.test_train_dir          = test_train_path
        self.padding_type            = padding_type
        self.completion_type         = completion_type
        
        # stats tracking
        self.start_gpu_memory        = -1
        self.max_memory              = -1
    
    def get_training_prompt_stats( self, backend="cuda", device_map="auto", device="cuda:1", debug=False ):
        
        self._load_model_and_tokenizer( backend=backend, device_map=device_map, mode="training" )
        
        df = pd.read_json(
            f"/{self.test_train_dir}/voice-commands-xml-train.jsonl", lines=True
        )
        
        token_stats = { "min": -1, "max": -1, "mean": -1 }
        word_stats  = { "min": -1, "max": -1, "mean": -1 }
        
        token_counts = [ ]
        word_counts  = [ ]
        counter = 0
        for row in df.itertuples():
            
            prompt = self.get_prompt( getattr( row, "instruction" ), getattr( row, "input" ), output=getattr( row, "output" ) )
            tokens_metadata = self.tokenizer( prompt, return_tensors="pt" ).to( device )
            
            tokens_count = len( tokens_metadata[ "input_ids" ][ 0 ] )
            word_count = len( prompt.split( ' ' ) )
            
            token_counts.append( tokens_count )
            word_counts.append( word_count )
            if debug:
                print( f"  Word count: {len( prompt.split( ' ' ) )}" )
                print( f"Tokens count: {tokens_count}" )
                # print( tokens_metadata[ "input_ids" ] )
            else:
                counter += 1
                if counter % 100 == 0: print( ".", end="" )
        
        print()
        
        token_stats[ "min" ] = min( token_counts )
        token_stats[ "max" ] = max( token_counts )
        token_stats[ "mean" ] = sum( token_counts ) / len( token_counts )
        
        word_stats[ "min" ] = min( word_counts )
        word_stats[ "max" ] = max( word_counts )
        word_stats[ "mean" ] = sum( word_counts ) / len( word_counts )
        
        return token_stats, word_stats
    
    def fine_tune( self, batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.20, backend="cuda", sample_size=1.0, device_map="auto", output_dir="./results" ):
        
        du.print_banner( f"Fine-tuning model {self.model_name} with PEFT", prepend_nl=True )
        run_start = f"Run started @ {du.get_current_time( format='%H:%M' )}"
        print( run_start )
        timer = Stopwatch( msg=None )
        
        self._load_model_and_tokenizer( backend=backend, device_map=device_map, mode="training" )
        
        self.model         = prepare_model_for_kbit_training( self.model, gradient_checkpointing_kwargs={ 'use_reentrant': True } )
        peft_config        = self._get_peft_config()
        training_arguments = self._get_training_args( output_dir=output_dir, batch_size=batch_size, gradient_accumulation_steps=gradient_accumulation_steps, logging_steps=logging_steps, eval_steps=eval_steps )
        test_train_data    = self._get_test_train_data( sample_size=sample_size )
        
        # self.trainer = SFTTrainer(
        self.trainer = MyKludgySFTTrainer(
            
            # workaround for buggy safe tensors behavior when a model is loaded across multiple GPUs
            # save_safetensors=False,
            model=self.model,
            train_dataset=test_train_data[ "train" ],
            eval_dataset=test_train_data[ "test" ],
            peft_config=peft_config,
            processing_class=self.tokenizer,
            args=training_arguments,
            packing=False,
            formatting_func=self._format_prompts,
        )
        
        self._print_trainable_parameters()
        self._print_stats_pre()
        self.trainer.train()
        self._print_stats_post()
        print( run_start )
        print( f"Run completed @ {du.get_current_time( format='%H:%M' )}")
        timer.print( msg=None )
        
        print( f"LORA checkpoints stashed here [{training_arguments.output_dir}]" )
        # the output directory contains the original lora_dir + date and time, and also now contains...
        self.output_dir     = training_arguments.output_dir
        # ...the last checkpoint directory created by the fine-tuning job
        self.checkpoint_dir = self._get_last_checkpoint_dir( training_arguments.output_dir )
        
        du.print_banner(f"Last checkpoint, here: {self.checkpoint_dir}")
        du.print_simple_file_list( self.checkpoint_dir )
    
    def _get_last_checkpoint_dir( self, output_dir ):
        
        # List all subdirectories in the output directory
        subdirs = [ d for d in os.listdir( output_dir ) if os.path.isdir( os.path.join( output_dir, d ) ) ]
        
        # Filter out checkpoint directories
        checkpoint_dirs = [ d for d in subdirs if d.startswith( 'checkpoint-' ) ]
        
        # Sort checkpoint directories by their step number
        checkpoint_dirs.sort( key=lambda x: int( x.split( '-' )[ -1 ] ) )
        
        # Get the path to the last checkpoint directory in the list
        last_checkpoint_dir = os.path.join( output_dir, checkpoint_dirs[ -1 ] ) if checkpoint_dirs else None
        
        return last_checkpoint_dir
        
    def save_model( self, output_dir ):
        
        date = du.get_current_date()
        time = du.get_current_time( format='%H-%M', include_timezone=False )
        path = f"{output_dir}/model-{date}-at-{time}"
        if not os.path.exists( path ):
            print( f"Creating output directory {path}..." )
            os.makedirs( path )
            print( f"Creating output directory {path}... Done!" )
            
        # get the current working directory
        cwd = os.getcwd()
        # change directory to save adapter
        os.chdir( path )
        
        print( f"Saving MODEL to {path}..." )
        self.model.save_pretrained( path, safe_serialization=False )
        print( f"Saving MODEL to {path}... Done!" )
        
        print( f"Saving TOKENIZER to {path}..." )
        self.tokenizer.save_pretrained( path )
        print( f"Saving TOKENIZER to {path}... Done!" )
        
        # change back to the original working directory
        os.chdir( cwd )
    
    def _load_adapter( self, adapter_path ):
        
        print( f"Loading adapter from {adapter_path}" )
        self.model = PeftModel.from_pretrained( self.model, adapter_path )
        print( f"Loading adapter from {adapter_path}... Done!" )
        
    def run_validation( self, adapter_path=None, path_prefix="/var/model/genie-in-the-box", device_map={"": 0}, sample_size=1000, debug=None, verbose=None ):
        
        if debug   is None: debug   = self.debug
        if verbose is None: verbose = self.verbose
        
        df = pd.read_json(f"{self.test_train_dir}/voice-commands-xml-validate.jsonl", lines=True ).sample( sample_size, random_state=42 )

        # update the prompt field
        # KLUDGE: this is a workaround for the fact that the prompt field is not being created when the validation df is created
        print( f"Updating the prompt field for [{sample_size}] rows..." )
        df[ "prompt" ] = df.apply( lambda row: self.get_prompt( row[ "instruction" ], row[ "input" ], output="" ), axis=1 )
        print( f"Updating the prompt field for [{sample_size}] rows... Done!" )
        
        du.print_banner( f"Validating {self.model_name} w/ {sample_size} samples..." )
        # Print value counts for the command column to see how many unique commands we have
        print( df.command.value_counts(), end="\n\n" )
        
        xml_ftp_generator = XmlFineTuningPromptGenerator( path_prefix=path_prefix, debug=debug, verbose=verbose )
        
        # load model and tokenizer...
        self._load_model_and_tokenizer( backend="cuda", device_map=device_map, mode="inference" )
        
        # load adapter...
        if adapter_path is not None:
            print( f"Loading adapter from user provided path: [{adapter_path}]" )
            self._load_adapter( adapter_path )
        elif self.checkpoint_dir is not None:
            print( f"Loading adapter created by the last fine tuning job: [{self.checkpoint_dir}]" )
            self._load_adapter( self.checkpoint_dir )
        else:
            print( "No adapter path provided or found" )
            return
        
        # generate responses...
        df = xml_ftp_generator.generate_responses(
            df, tokenizer=self.tokenizer, model=self.model, switch="huggingface", model_name=self.model_name, device=device_map,
            max_new_tokens=128, debug=debug, verbose=verbose
        )
        # validate responses...
        df = xml_ftp_generator.validate_responses( df )
        # print validation stats...
        xml_ftp_generator.print_validation_stats( df, title=f"Validation stats for model {self.model_name}" )
        
        return df
    
    def _load_model_and_tokenizer( self, backend="cuda", device_map="auto", mode="training" ):
        
        # compute_dtype = torch.bfloat16
        attn_implementation = 'flash_attention_2'
        quantization_config = AutoRoundConfig( backend=backend )
        
        if self.model is None:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.path_to_quantized_model,
                # device_map="auto", # distributed training
                device_map=device_map,  # {"": 0} = single GPU
                quantization_config=quantization_config,
                attn_implementation=attn_implementation
            )
        else:
            print( "Model already loaded. Skipping" )
            
        if self.tokenizer is None:
            self.tokenizer = AutoTokenizer.from_pretrained( self.path_to_quantized_model )
        else:
            print( "Tokenizer already loaded. Skipping" )
            
        # ad-hoc padding configuration
        if self.padding_type in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410" ]:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            if mode == "training":
                self.tokenizer.padding_side = "right"
            else:
                self.tokenizer.padding_side = "left"
        # TODO: add padding for other models
        # elif self.padding_type == "llama-3b":
        #     self.tokenizer.pad_token = "<|finetune_right_pad_id|>"
        #     self.tokenizer.pad_token_id = 128004
        #     self.tokenizer.padding_side = 'right'
        else:
            raise ValueError( f"Unsupported padding type: {self.padding_type}, MUST be 'Mistral-7B-Instruct-v0.2' or 'Ministral-8B-Instruct-2410' for now" )
        
    def _get_peft_config( self ):
        
        if self.completion_type == "Mistral-7B-Instruct-v0.2":
            r = 4
        elif self.completion_type == "Ministral-8B-Instruct-2410":
            r = 16
        else:
            raise ValueError( f"Unsupported completion type: {self.completion_type}, MUST be 'Mistral-7B-Instruct-v0.2' or 'Ministral-8B-Instruct-2410' for now" )
        
        return LoraConfig(
            lora_alpha=16,
            lora_dropout=0.05,
            r=r,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[ 'k_proj', 'q_proj', 'v_proj', 'o_proj', "gate_proj", "down_proj", "up_proj" ]
        )
    
    def _get_training_args( self, output_dir="./results", batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.5 ):
        return SFTConfig(
            # set logging dir
            output_dir=f"{output_dir}/peft-output-{du.get_current_date()}-at-{du.get_current_time( format='%H-%M', include_timezone=False )}",
            eval_strategy="steps",
            do_eval=True,
            optim="adamw_8bit",
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            # for a batch size of 8: Gradient checkpointing nearly reduces the memory consumption by 40%.
            # For a batch size of 8: Fine-tuning is twice as fast without gradient checkpointing.
            gradient_checkpointing=False,
            log_level="debug",
            save_strategy="epoch",
            logging_steps=logging_steps,
            learning_rate=1e-5,
            bf16=torch.cuda.is_bf16_supported(),
            fp16=not torch.cuda.is_bf16_supported(),
            eval_steps=eval_steps,
            num_train_epochs=1,
            warmup_ratio=0.1,
            lr_scheduler_type="linear",
            dataset_text_field="text",
            max_seq_length=self._get_max_seq_length()
        )
    
    def _get_max_seq_length( self ):
        
        if self.completion_type == "Mistral-7B-Instruct-v0.2":
            return 779
        elif self.completion_type == "Ministral-8B-Instruct-2410":
            return 683
        else:
            raise ValueError( f"Unsupported completion type: {self.completion_type}, MUST be 'Mistral-7B-Instruct-v0.2' or 'Ministral-8B-Instruct-2410' for now" )
        
    def _get_test_train_data( self, sample_size=1.0 ):
        
        if self.completion_type in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410" ]:
            extract_gpt_message = False
        else:
            raise ValueError( f"Unsupported completion type: [{self.completion_type}], MUST be 'Mistral-7B-Instruct-v0.2' or 'Ministral-8B-Instruct-2410' for now" )
        
        path = f"/{self.test_train_dir}/voice-commands-xml-train.jsonl"
        train_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        path = f"/{self.test_train_dir}/voice-commands-xml-test.jsonl"
        test_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        return { 'train': train_dataset, 'test': test_dataset }
    
    def _get_dataset( self, path, sample_size=1.0, extract_gpt_message=False ):
        
        rows = du.get_file_as_list( path )
        # retain a sample of the data set expressed as a percentage
        row_count = len( rows )
        if sample_size < 1.0:
            rows = rows[ : int( row_count * sample_size ) ]
        if extract_gpt_message:
            rows = [ json.loads( line )[ "gpt_message" ] for line in rows ]
        else:
            rows = [ json.loads( line ) for line in rows ]
        
        print( f"Loaded {len( rows )} of {row_count} training rows" )
        
        return Dataset.from_list( rows )
        
    def _format_prompts( self, rows ):
        
        prompts = []
        
        for i in range( len( rows[ "instruction" ] ) ):
            
            if self.completion_type == "Mistral-7B-Instruct-v0.2":
                prompt = f"""### Instruction:
                Use the Task below and the Input given to write a Response that can solve the following Task:
                
                ### Task:
                {rows[ "instruction" ][ i ]}
                
                ### Input:
                {rows[ "input" ][ i ]}
                
                ### Response:
                {rows[ "output" ][ i ]}
                """
            elif self.completion_type == "Ministral-8B-Instruct-2410":
                
                prompt = f"""<s>[INST]### Instruction:
                Use the Task below along with the Input given after that to write a Response that can solve the following Task:
                
                ### Task:
                {rows[ "instruction" ][ i ]}
                
                ### Input:
                {rows[ "input" ][ i ]}
                [/INST]
                ### Response:
                {rows[ "output" ][ i ]}
                </s>"""
            else:
                raise ValueError( f"Unsupported completion_type: [{self.completion_type}], MUST be 'Mistral-7B-Instruct-v0.2' or 'Ministral-8B-Instruct-2410' for now" )
            prompts.append( prompt )
            
        return prompts
    
    def get_prompt( self, instruction, input, output="" ):
        
        if self.completion_type == "Mistral-7B-Instruct-v0.2":
            return f"""### Instruction:
            Use the Task below and the Input given to write a Response that can solve the following Task:
    
            ### Task:
            {instruction}
    
            ### Input:
            {input}
    
            ### Response:
            {output}
            """
        elif self.completion_type == "Ministral-8B-Instruct-2410":
            
            return f"""<s>[INST]### Instruction:
            Use the Task below along with the Input given after that to write a Response that can solve the following Task:

            ### Task:
            {instruction}

            ### Input:
            {input}
            [/INST]
            ### Response:
            {output}
            </s>"""
    
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
    
    def set_hf_env_vars( self, hf_home="/var/model/models", hf_hub_etag_timeout="60", hf_hub_download_timeout="60" ):
        """
        Set environment variables for the Hugging Face model hub.
        """
        os.environ[ "HF_HOME"                 ] = hf_home
        os.environ[ "HF_HUB_ETAG_TIMEOUT"     ] = hf_hub_etag_timeout
        os.environ[ "HF_HUB_DOWNLOAD_TIMEOUT" ] = hf_hub_download_timeout
        
        du.print_banner( "Hugging Face Environment Variables:" )
        print( os.environ[ "HF_HOME" ] )
        print( os.environ[ "HF_HUB_ETAG_TIMEOUT" ] )
        print( os.environ[ "HF_HUB_DOWNLOAD_TIMEOUT" ] )
    
    def set_gib_env_vars( self, wandb_disable_service="True", gib_root="/var/model/genie-in-the-box" ):
        """
        Set environment variables for the Genie in the Box model.
        """
        os.environ[ "GENIE_IN_THE_BOX_ROOT"   ] = gib_root
        os.environ[ "GIB_CONFIG_MGR_CLI_ARGS" ] = "config_path=/src/conf/gib-app.ini splainer_path=/src/conf/gib-app-splainer.ini config_block_id=Genie+in+the+Box:+Development"
        os.environ[ "WANDB_DISABLE_SERVICE"   ] = wandb_disable_service
    

class MyKludgySFTTrainer(SFTTrainer):

    # overwriting the evaluation loop suggested here: https://chatgpt.com/share/67983b91-a950-8006-97c4-dfeb2d02b3ea
    def evaluation_loop(self, *args, **kwargs):
        # Set padding_side to 'left' for evaluation
        self.tokenizer.padding_side = 'left'
        result = super().evaluation_loop(*args, **kwargs)
        # Revert padding_side to 'right' after evaluation
        self.tokenizer.padding_side = 'right'
        return result
    
# def suss_out_dataset():
#
#     path = "/mnt/DATA01/include/www.deepily.ai/projects/genie-in-the-box/src/ephemera/prompts/data/voice-commands-xml-train.jsonl"
#     train_dataset = du.get_file_as_list( path )
#     train_dataset = [ json.loads( line )[ "gpt_message" ] for line in train_dataset ]
#     print( f"Loaded {len( train_dataset )} training items" )
#
#     # for i in range( 10 ):
#     print( train_dataset[ 0 ] )
#
#     train_dataset = Dataset.from_list( train_dataset )
#     print( train_dataset[ 0 ] )
    
if __name__ == "__main__":
    
    # suss_out_dataset()
    # sanity check for command line arguments
    if len( sys.argv ) != 5:
        print( "Usage: python peft_trainer.py <path_to_quantized_model> <model_name> <test_train_path> <output_dir>" )
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
    output_dir = sys.argv[ 4 ]
    
    trainer = PeftTrainer( path_to_quantized_model, model_name, test_train_path )
    # trainer.fine_tune( batch_size=20, gradient_accumulation_steps=40, sample_size=0.1, output_dir=output_dir )
    # trainer.save_model( output_dir )
    
    # Wait 10 seconds before exiting
    os.system( "sleep 30" )
    
