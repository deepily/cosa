import gc
import sys
import json
import pandas as pd

import torch, os, multiprocessing
from peft import LoraConfig, prepare_model_for_kbit_training, PeftModel
from torch.ao.quantization import quantize
from torch.utils.benchmark import timer

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    set_seed
)
from datasets import Dataset
from datasets.formatting.formatting import LazyBatch
from trl import SFTTrainer, SFTConfig
from auto_round import AutoRoundConfig
from huggingface_hub import login

import cosa.utils.util         as du
import cosa.utils.util_pytorch as dupt

from cosa.agents.llm           import Llm
from cosa.training.quantizer   import Quantizer
from cosa.utils.util_stopwatch import Stopwatch

from cosa.training.xml_fine_tuning_prompt_generator import XmlFineTuningPromptGenerator

set_seed( 42 )

def release_gpus( models ):
    
    for model in models:
        
        # move it to the CPU before deleting it, but test to make sure the attribute actually exists before you do though
        if hasattr( model, 'cpu' ) and callable( getattr( model, 'cpu' ) ):
            model.cpu()
        del model
        
    gc.collect()
    torch.cuda.empty_cache()

class PeftTrainer:
    
    def __init__(
        self, model_hf_id, model_name, test_train_path, lora_dir=None, debug=False, verbose=False
    ):
        
        du.print_banner( f"Initializing PEFT Trainer for {model_name}" )
        print( f"Model ID: {model_hf_id}" )
        print( f"Path to test/train data: {test_train_path}" )
        
        self.debug                   = debug
        self.verbose                 = verbose
        self.trainer                 = None
        self.model                   = None
        self.model_hf_id             = model_hf_id
        self.tokenizer               = None
        self.output_dir              = None
        self.checkpoint_dir          = None
        self.model_name              = model_name
        self.test_train_dir          = test_train_path
        self.lora_dir                = lora_dir
        self.merged_adapter_dir      = None
        self.quantized_model_dir     = None
        
        # stats tracking
        self.start_gpu_memory        = -1
        self.max_memory              = -1
        
        # models supported by this trainer
        self.supported_model_names   = [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]
    
    def login_to_hf( self ):
        
        hf_token = du.get_api_key( "huggingface", project_root=os.getenv( "GENIE_IN_THE_BOX_ROOT" ) )
        print( f"Logging in to Hugging Face with token [{hf_token}]... ", end="" )
        login( token=hf_token )
        print( "Done!" )
        
    def get_training_prompt_stats( self, backend="cuda", device_map="auto", device="cuda:1", debug=False, verbose=False ):
        
        self._load_model_and_tokenizer( backend=backend, device_map=device_map, mode="training" )
        
        df = pd.read_json(f"/{self.test_train_dir}/voice-commands-xml-train.jsonl", lines=True )#.sample( 1000, random_state=42 )
        
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
            if debug and verbose:
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
        
        if self.debug:
            du.print_banner( "Token stats", prepend_nl=True )
            print( token_stats )
            du.print_banner( "Last prompt" )
            print( prompt )
            
        return token_stats, word_stats
    
    def fine_tune( self, batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.20, backend="cuda", sample_size=1.0, device_map="auto", output_dir="./results" ):
        
        du.print_banner( f"Fine-tuning model {self.model_name} with PEFT", prepend_nl=True )
        run_start = f"Run started @ {du.get_current_time( format='%H:%M' )}"
        print( run_start )
        timer = Stopwatch( msg=None )
        
        self._load_model_and_tokenizer( backend=backend, device_map=device_map, mode="training" )
        
        # I used this when loading a quantized model. Since I'm not quantizing now, it's commented out
        # self.model         = prepare_model_for_kbit_training( self.model, gradientoow_checkpointing_kwargs={ 'use_reentrant': True } )
        peft_config        = self._get_peft_config()
        training_arguments = self._get_training_args( output_dir=output_dir, batch_size=batch_size, gradient_accumulation_steps=gradient_accumulation_steps, logging_steps=logging_steps, eval_steps=eval_steps )
        test_train_data    = self._get_test_train_data( sample_size=sample_size )
        
        du.print_banner( "Training data" )
        print( test_train_data[ "train" ] )
        du.print_banner( "Validation data" )
        print( test_train_data[ "test" ] )
        
        self.trainer = SFTTrainer(
        # self.trainer = MyKludgySFTTrainer(
            
            # workaround for buggy safe tensors behavior when a model is loaded across multiple GPUs
            # save_safetensors=False,
            model=self.model,
            train_dataset=test_train_data[ "train" ],
            eval_dataset=test_train_data[ "test" ],
            peft_config=peft_config,
            processing_class=self.tokenizer,
            args=training_arguments,
            # packing=False,
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
        
        du.print_banner(f"Last checkpoint: {self.checkpoint_dir}")
        du.print_simple_file_list( self.checkpoint_dir )
        
        return self.checkpoint_dir

    def get_last_checkpoint_dir( self ):
        
        return self.checkpoint_dir

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
        
    def save_model( self ):
        
        date = du.get_current_date()
        time = du.get_current_time( format='%H-%M', include_timezone=False )
        path = f"{self.output_dir}/final-{date}-at-{time}"
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
        
    def run_validation_in_memory( self,
        switch="", adapter_path=None,  path_prefix="/var/model/genie-in-the-box", device_map={"": 0},
        sample_size=1000, debug=None, verbose=None
    ):
        du.print_banner( f"Validating {self.model_name} w/ {sample_size} samples..." )
       
        # set debug and verbose to the class defaults if not provided
        if debug   is None: debug   = self.debug
        if verbose is None: verbose = self.verbose
        
        df = pd.read_json(f"{self.test_train_dir}/voice-commands-xml-validate.jsonl", lines=True ).sample( sample_size, random_state=42 )

        # update the prompt field
        # KLUDGE: this is a workaround for the fact that the prompt field is not being created when the validation df is created
        print( f"Updating the prompt field for [{sample_size}] rows..." )
        df[ "prompt" ] = df.apply( lambda row: self.get_prompt( row[ "instruction" ], row[ "input" ], output="" ), axis=1 )
        print( f"Updating the prompt field for [{sample_size}] rows... Done!" )
        
        # Print value counts for the command column to see how many unique commands we have
        print( "Value counts for the 'command' column:" )
        print( df.command.value_counts(), end="\n\n" )
        
        xml_ftp_generator = XmlFineTuningPromptGenerator( path_prefix=path_prefix, debug=debug, verbose=verbose )
        
        du.print_banner( "Querying LLM in memory" )
        # load model and tokenizer...
        self._load_model_and_tokenizer( backend="cuda", device_map=device_map, mode="inference" )
        
        # ...and adapter...
        if adapter_path is not None:
            print( f"Loading adapter from user provided path: [{adapter_path}]" )
            self._load_adapter( adapter_path )
        elif self.checkpoint_dir is not None:
            print( f"Loading adapter created by the last fine tuning job: [{self.checkpoint_dir}]" )
            self._load_adapter( self.checkpoint_dir )
        else:
            print( "No adapter path provided or found, proceeding with validation, using model by itself" )
            
        # generate responses...
        df = xml_ftp_generator.generate_responses(
            df, tokenizer=self.tokenizer, model=self.model, switch=switch, model_name=self.model_name, device=device_map,
            max_new_tokens=128, debug=debug, verbose=verbose
        )
        # validate responses...
        df = xml_ftp_generator.validate_responses( df )
        # print validation stats...
        xml_ftp_generator.print_validation_stats( df, title=f"Validation stats for model {self.model_name}" )
        
        return df
    
    def run_validation_with_server(
            self, model=None, switch="", path_prefix="/var/model/genie-in-the-box",
            device_map={ "": 0 }, sample_size=1000, debug=None, verbose=None
    ):
        
        # set debug and verbose to the class defaults if not provided
        if debug   is None: debug = self.debug
        if verbose is None: verbose = self.verbose
        
        if model is None:
            raise ValueError( "Model must be provided" )
        else:
            self.model = model
        
        # advise that we're going to query a server instead
        du.print_banner( f"Querying an LLM server w/ model [{self.model}]" )
        
        df = pd.read_json(
            f"{self.test_train_dir}/voice-commands-xml-validate.jsonl", lines=True
        ).sample( sample_size, random_state=42 )
        
        # update the prompt field
        # KLUDGE: this is a workaround for the fact that the prompt field is not being created when the validation df is created
        print( f"Updating the prompt field for [{sample_size}] rows..." )
        df[ "prompt" ] = df.apply( lambda row: self.get_prompt( row[ "instruction" ], row[ "input" ], output="" ), axis=1 )
        print( f"Updating the prompt field for [{sample_size}] rows... Done!" )
        
        du.print_banner( f"Validating {self.model_name} w/ {sample_size} samples..." )
        # Print value counts for the command column to see how many unique commands we have
        print( df.command.value_counts(), end="\n\n" )
        
        xml_ftp_generator = XmlFineTuningPromptGenerator( path_prefix=path_prefix, debug=debug, verbose=verbose )
        
        # generate responses...
        df = xml_ftp_generator.generate_responses(
            df, tokenizer=self.tokenizer, model=self.model, switch=switch, model_name=self.model_name,
            device=device_map, max_new_tokens=128, debug=debug, verbose=verbose
        )
        # validate responses...
        df = xml_ftp_generator.validate_responses( df )
        # print validation stats...
        xml_ftp_generator.print_validation_stats( df, title=f"Validation stats for model {self.model_name}" )
        
        return df
    
    def load_and_merge_adapter( self, checkpoint_dir=None, device_map={ "": 0 } ):
        
        du.print_banner( f"Load and merge adapter {checkpoint_dir}" )
        self._load_model_and_tokenizer( backend="cuda", device_map=device_map, mode="inference" )
        
        if checkpoint_dir is not None:
            self.checkpoint_dir = checkpoint_dir
        elif self.checkpoint_dir is None:
            raise ValueError( "No adapter path provided or found" )
            
        print( f"Loading adapter from {self.checkpoint_dir}... ", end="" )
        self.model = PeftModel.from_pretrained( self.model, self.checkpoint_dir )
        print( "Done!" )
        
        print( "Merging adapter... ", end="" )
        self.model = self.model.merge_and_unload()
        print( "Done!" )
    
    def save_merged_adapter( self, lora_dir=None ):
        
        if lora_dir is not None:
            self.lora_dir = lora_dir
        elif self.lora_dir is None:
            raise ValueError( "lora_dir directory is neither provided nor found" )
        
        du.print_banner( f"Save merged adapter to {self.lora_dir}" )
        
        date = du.get_current_date()
        time = du.get_current_time( format='%H-%M', include_timezone=False )
        path = f"{self.lora_dir}/merged-on-{date}-at-{time}"
        
        if not os.path.exists( path ):
            print( f"Creating output directory {path}... ", end="" )
            os.makedirs( path )
            print( "Done!" )
        
        print( f"Saving merged adapter to {path}... ", end="" )
        self.model.save_pretrained( path )
        self.tokenizer.save_pretrained( path )
        print( "Done!" )
        
        self.merged_adapter_dir = path
        
        return self.merged_adapter_dir
        
    def quantize_merged_adapter( self, merged_adapter_dir=None ):
        
        # sanity check
        if merged_adapter_dir is not None:
            self.merged_adapter_dir = merged_adapter_dir
        elif self.merged_adapter_dir is None:
            raise ValueError( "merged_adapter_dir is neither provided nor found" )
        
        du.print_banner( f"Quantize merged adapter in {self.merged_adapter_dir}" )
        quantizer = Quantizer( self.merged_adapter_dir )
        quantizer.quantize_model()
        self.quantized_model_dir = quantizer.save( self.merged_adapter_dir, include_model_name=False )
        
        return self.quantized_model_dir
    
    def _load_model_and_tokenizer( self, backend="cuda", device_map="auto", mode=None ):
        
        # Quick sanity checks
        if "HF_HOME" not in os.environ:
            raise ValueError( "Environment variable HF_HOME must be set, try calling trainer.set_hf_env_vars() first?" )
        
        if mode is None or mode not in [ "training", "inference" ]:
            raise ValueError( "Mode MUST be specified, either 'training' or 'inference'" )
        
        torch_dtype         = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        attn_implementation = "flash_attention_2"
        cache_dir           = os.getenv( "HF_HOME" ) + "/hub"
        original_cwd        = os.getcwd()
        # quantization_config = AutoRoundConfig( backend=backend )
        
        if self.model is None:
            
            print( f"Loading {self.model_hf_id}..." )
            print( f"Switching from current working directory: {original_cwd}..." )
            os.chdir( os.environ[ "HF_HOME" ] )
            print( f"To new working directory: {os.getcwd()}" )
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_hf_id, device_map=device_map, low_cpu_mem_usage=True, use_cache=False,
                torch_dtype=torch_dtype, local_files_only=True, cache_dir=cache_dir,
                attn_implementation=attn_implementation
            )
            
            if self.debug and self.verbose:
                dupt.print_device_allocation( self.model )
                
            # previously used this to load auto round config
            # ¡OJO! Note that in the first use of self.model it represents a path, but in the second use it represents a model object
            # self.model = AutoModelForCausalLM.from_pretrained(
            #     self.model,
            #     # device_map="auto", # distributed training
            #     device_map=device_map,  # {"": 0} = single GPU
            #     quantization_config=quantization_config,
            #     attn_implementation=attn_implementation
            # )
        else:
            print( "Model already loaded. Skipping" )
            
        if self.tokenizer is None:
            
            self.tokenizer = AutoTokenizer.from_pretrained( self.model_hf_id, force_download=True, from_slow=False )
            
            # ad-hoc padding configurations
            if self.model_name in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410" ]:
                
                self.tokenizer.pad_token = self.tokenizer.eos_token
                
            elif self.model_name == "Llama-3.2-3B-Instruct":
            
                self.tokenizer.pad_token = "<|finetune_right_pad_id|>"
                self.tokenizer.pad_token_id = 128004
                self.tokenizer.padding_side = 'right'
                
            elif self.model_name == "Phi-4-mini-instruct":
                
                self.tokenizer.pad_token = self.tokenizer.unk_token
                self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids( self.tokenizer.pad_token )
                self.tokenizer.padding_side = 'left'
            
            else:
                raise ValueError(
                    f"Unsupported model_name: '{self.model_name}', MUST be {self.supported_model_names} for now"
                )
            
            if mode == "training":
                print( "Setting padding side to 'right' for training" )
                self.tokenizer.padding_side = "right"
            elif mode == "inference":
                print( "Setting padding side to 'left' for inference" )
                self.tokenizer.padding_side = "left"
            else:
                # this is checked above, this will never be called
                raise ValueError( "Mode MUST be specified, either 'training' or 'inference'" )
        else:
            print( "Tokenizer already loaded. Skipping" )
            
        if original_cwd != os.getcwd():
            print( f"Switching back to original working directory: {original_cwd}" )
            os.chdir( original_cwd )
            # print( f"New working directory: {os.getcwd()}" )
        
    def _get_peft_config( self ):
        
        if self.model_name == "Mistral-7B-Instruct-v0.2":
            r = 4
        elif self.model_name == "Ministral-8B-Instruct-2410":
            # why so big? r = 16 only yielded: trainable params: 43,646,976 || all params: 8,063,455,232 || trainable%: 0.54
            r = 32
        elif self.model_name in [ "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:
            r = 64
        else:
            raise ValueError( f"Unsupported completion type: '{self.model_name}', MUST be {self.supported_model_names} for now" )
        
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
            # output_dir=f"{output_dir}/peft-output-{du.get_current_date()}-at-{du.get_current_time( format='%H-%M', include_timezone=False )}",
            output_dir=f"{output_dir}/training-{du.get_current_date()}-at-{du.get_current_time( format='%H-%M', include_timezone=False )}",
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
        
        if self.model_name == "Mistral-7B-Instruct-v0.2":
            return 779
        elif self.model_name in [ "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:
            return 683
        else:
            raise ValueError( f"Unsupported completion type: '{self.model_name}', MUST be {self.supported_model_names} for now" )
        
    def _get_test_train_data( self, sample_size=1.0 ):
        
        if self.model_name in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:
            extract_gpt_message = False
        else:
            raise ValueError( f"Unsupported completion type: '{self.model_name}', MUST be {self.supported_model_names} for now" )
        
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
            
            if self.model_name == "Mistral-7B-Instruct-v0.2":
                prompt = f"""### Instruction:
                Use the Task below and the Input given to write a Response that can solve the following Task:
                
                ### Task:
                {rows[ "instruction" ][ i ]}
                
                ### Input:
                {rows[ "input" ][ i ]}
                
                ### Response:
                {rows[ "output" ][ i ]}
                """
            elif self.model_name in [ "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:
                
                du.print_banner( "formatting prompts..." )
                print( rows[ "instruction" ][ i ] )
                print( rows[ "input" ][ i ] )
                # print( rows[ "output" ][ i ] )
                
                prompt = f"""<s>[INST]{rows[ "instruction" ][ i ]}

                {rows[ "input" ][ i ]}
                [/INST]
                {rows[ "output" ][ i ]}
                </s>"""
            else:
                raise ValueError( f"Unsupported completion_type: '{self.model_name}', MUST be {self.supported_model_names} for now" )
            
            prompts.append( prompt )
            
        return prompts
    
    def get_prompt( self, instruction, input, output="" ):
        
        if self.model_name == "Mistral-7B-Instruct-v0.2":
            return f"""### Instruction:
            Use the Task below and the Input given to write a Response that can solve the following Task:
    
            ### Task:
            {instruction}
    
            ### Input:
            {input}
    
            ### Response:
            {output}
            """
        elif self.model_name in [ "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:

            if output == "":
                last_tag = ""
            else:
                last_tag = "</s>"

            return f"""<s>[INST]{instruction}

            {input}
            [/INST]
            {output}
            {last_tag}"""
        else:
            raise ValueError( f"Unsupported completion_type: '{self.model_name}', MUST be {self.supported_model_names} for now" )
    
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
        print( "Usage: python peft_trainer.py <model> <model_name> <test_train_path> <lora_dir>" )
        sys.exit( 1 )
    # sanity check for environment variables
    if not os.getenv( "NCCL_P2P_DISABLE" ):
        print( "Please set env variable NCCL_P2P_DISABLE=1" )
        sys.exit( 1 )
    if not os.getenv( "NCCL_IB_DISABLE" ):
        print( "Please set env variable NCCL_IB_DISABLE=1" )
        sys.exit( 1 )
    if not os.getenv( "GENIE_IN_THE_BOX_ROOT" ):
        print( "Please set env variable GENIE_IN_THE_BOX_ROOT=___________________" )
        sys.exit( 1 )
    if not os.getenv( "GIB_CONFIG_MGR_CLI_ARGS" ):
        print( "Please set env variable GIB_CONFIG_MGR_CLI_ARGS=___________________" )
        sys.exit( 1 )
        
    model           = sys.argv[ 1 ]
    model_name      = sys.argv[ 2 ]
    test_train_path = sys.argv[ 3 ]
    lora_dir        = sys.argv[ 4 ]
    gib_root        = os.getenv( "GENIE_IN_THE_BOX_ROOT" )
    
    timer   = Stopwatch( msg=None )
    trainer = PeftTrainer( model, model_name, test_train_path, lora_dir=lora_dir, debug=True, verbose=True )
    
    trainer.login_to_hf()

    # for Ministral-8B-Instruct-2410
    # checkpoint_dir = trainer.fine_tune( sample_size=1.0, batch_size=3, gradient_accumulation_steps=8, logging_steps=0.10, eval_steps=0.10, device_map="auto", output_dir=lora_dir )
    # for Llama-3.2-3B-instruct
    # checkpoint_dir = trainer.fine_tune( sample_size=1.0, batch_size=6, gradient_accumulation_steps=4, logging_steps=0.10, eval_steps=0.10, device_map="auto", output_dir=lora_dir )
    # for Phi-3.5/4-mini-instruct
    checkpoint_dir = trainer.fine_tune( sample_size=0.01, batch_size=8, gradient_accumulation_steps=4, logging_steps=0.50, eval_steps=0.50, device_map="auto", output_dir=lora_dir )
    release_gpus( [ trainer.model, trainer.tokenizer ] )
    # TODO: this is still showing 60-some megabytes of GPU RAM as allocated...
    trainer.load_and_merge_adapter( checkpoint_dir=checkpoint_dir )
    merged_adapter_dir = trainer.save_merged_adapter( lora_dir=lora_dir )
    release_gpus( [ trainer.model, trainer.tokenizer ] )

    quantized_model_dir = trainer.quantize_merged_adapter( merged_adapter_dir=merged_adapter_dir )

    # quantized_model_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-4-bits-sym.gptq/2025-02-12-at-02-27"
    # quantized_model_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-02-12-at-02-05/autoround-8-bits-sym.gptq/2025-02-24-at-21-39"
    # quantized_model_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Llama-3.2-3B-Instruct.lora/merged-on-2025-02-23-at-21-59/autoround-4-bits-sym.gptq/2025-02-23-at-22-09"
    timer.print( f"Finished fine-tuning, merging and quantizing {model_name}" )
    du.print_banner( f"Finished quantizing {model_name}" )
    print( f"Quantized model: {quantized_model_dir}" )
    du.print_simple_file_list( quantized_model_dir )

    # wait for user input before continuing
    choice = input( "Press 'Enter' to validate model, 'n' to exit:" )
    if choice.lower() == 'n':
        sys.exit( 0 )

    model = Llm.get_model( quantized_model_dir )
    stats_df = trainer.run_validation_with_server(
        model=model, path_prefix=os.getenv( "GENIE_IN_THE_BOX_ROOT" ), switch="deepily", device_map="cuda:0", sample_size=1000, debug=False, verbose=False
    )
    print( stats_df )
