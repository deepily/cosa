import gc
import sys
import json
import pandas as pd
import argparse
import time
import subprocess
import threading
import requests
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

# Import the model configuration loader
from cosa.training.conf import load_model_config

import cosa.utils.util         as du
import cosa.utils.util_pytorch as dupt

from cosa.agents.llm_v0        import Llm_v0
from cosa.training.quantizer   import Quantizer
from cosa.utils.util_stopwatch import Stopwatch

from cosa.training.xml_coordinator import XmlCoordinator

set_seed( 42 )

@staticmethod
def release_gpus( models ):
    """
    Releases GPU memory by moving models to CPU and clearing CUDA cache.
    
    Preconditions:
    - models must be an iterable collection of model objects.
    - Each model in models may or may not have a 'cpu' method.
    
    Postconditions:
    - All models in the collection are moved to CPU if they have a 'cpu' method.
    - All models are deleted from Python's memory.
    - Python's garbage collector is run to reclaim memory.
    - GPU memory cache is cleared using torch.cuda.empty_cache().
    
    Parameters:
    - models (Iterable): A collection of model objects to be released from GPU memory.
    
    Notes:
    - This function handles models that might not have a 'cpu' method safely by checking
      for the attribute's existence and callability before invoking it.
    - This function is particularly useful after fine-tuning or inference to ensure 
      GPU memory is properly released for subsequent operations.
    """
    for model in models:
        
        # move it to the CPU before deleting it, but test to make sure the attribute actually exists before you do
        if hasattr( model, 'cpu' ) and callable( getattr( model, 'cpu' ) ):
            print( f"Moving model {model} to CPU before deleting it..." )
            model.cpu()
        del model
        
    gc.collect()
    torch.cuda.empty_cache()

class PeftTrainer:
    
    def __init__(
        self, model_hf_id, model_name, test_train_path, lora_dir=None, debug=False, verbose=False
    ):
        """
        Initializes a new PEFT Trainer instance with the provided parameters.
        
        Preconditions:
        - `model_hf_id` is a valid model identifier in Hugging Face Hub format.
        - `model_name` is a string representing one of the supported model names.
        - `test_train_path` is a valid path where test/train data is located.
        - `lora_dir` is either None or a valid directory path for storing LoRA adapter files.
        - `debug` and `verbose` are boolean values to control logging verbosity.
        
        Postconditions:
        - A new PeftTrainer instance is created with all necessary attributes initialized.
        - The model name is validated against the list of supported models.
        - Initial debug information is printed if debug mode is enabled.
        
        Raises:
        - ValueError: if `model_name` is not in the list of supported models.
        
        Parameters:
        - model_hf_id (str): The Hugging Face model ID to use for fine-tuning.
        - model_name (str): The name of the model (must be one of the supported models).
        - test_train_path (str): Path to the directory containing test/train data.
        - lora_dir (str, optional): Directory for saving LoRA adapter files. Defaults to None.
        - debug (bool, optional): Enable debug mode with additional logging. Defaults to False.
        - verbose (bool, optional): Enable verbose mode with more detailed output. Defaults to False.
        """
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
        
        # Validate the model name
        self._validate_model_name()
    
    def _validate_model_name( self ):
        """
        Validates the model name against a list of supported model names.
    
        Precondition:
        - `self.model_name` is a string representing the name of the model to be validated.
        - The `conf` module contains model configurations for the supported models.
    
        Postcondition:
        - If `self.model_name` is supported, the method completes without error.
        - If `self.model_name` is not supported, a ValueError is raised with a message 
          indicating the unsupported model name and listing the supported model names.
    
        Raises:
        - ValueError: If `self.model_name` is not supported.
        """
        # Import the model config map which has all supported models
        from cosa.training.conf import MODEL_CONFIG_MAP
        
        if self.model_name not in MODEL_CONFIG_MAP:
            raise ValueError(f"Unsupported model_name: '{self.model_name}'. Must be one of: {', '.join(MODEL_CONFIG_MAP.keys())}")
            
        # For backward compatibility, also check supported_model_names
        if hasattr(self, 'supported_model_names') and self.model_name not in self.supported_model_names:
            print(f"Warning: Model '{self.model_name}' not in self.supported_model_names. Updating supported_model_names.")
            self.supported_model_names = list(MODEL_CONFIG_MAP.keys())
    
    def login_to_hf( self ):
        """
        Authenticates with the Hugging Face API using API token from environment.
        
        Preconditions:
        - The GENIE_IN_THE_BOX_ROOT environment variable is set to a valid project root path.
        - A valid Hugging Face API token is accessible via the utility method du.get_api_key.
        
        Postconditions:
        - The application is authenticated with the Hugging Face API.
        - A login confirmation message is printed to the console.
        
        Raises:
        - If du.get_api_key fails to retrieve a valid token, it may raise KeyError or FileNotFoundError.
        - If login fails, Hugging Face's login function may raise various exceptions.
        """
        hf_token = du.get_api_key( "huggingface", project_root=os.getenv( "GENIE_IN_THE_BOX_ROOT" ) )
        print( f"Logging in to Hugging Face with token [{hf_token}]... ", end="" )
        login( token=hf_token )
        print( "Done!" )
        
    def get_training_prompt_stats( self, backend="cuda", device_map="auto", device="cuda:1", debug=False, verbose=False ):
        """
        Analyzes the token and word statistics of training prompts in the dataset.
        
        Preconditions:
        - The model and tokenizer must be available or loadable.
        - A valid training dataset must exist at the path "/{self.test_train_dir}/voice-commands-xml-train.jsonl".
        - The dataset must contain 'instruction', 'input', and 'output' columns.
        
        Postconditions:
        - Token and word statistics (min, max, mean) are calculated for the training dataset.
        - Debug information is printed if debug mode is enabled.
        - The calculated statistics are returned as a tuple of two dictionaries.
        
        Parameters:
        - backend (str, optional): Backend to use for model loading. Defaults to "cuda".
        - device_map (str, optional): Device mapping strategy for model. Defaults to "auto".
        - device (str, optional): Specific device to use for tokenizer calculations. Defaults to "cuda:1".
        - debug (bool, optional): Enable debug mode. Defaults to False.
        - verbose (bool, optional): Enable verbose mode. Defaults to False.
        
        Returns:
        - tuple: A tuple containing two dictionaries:
          - token_stats: Dictionary with 'min', 'max', and 'mean' token counts
          - word_stats: Dictionary with 'min', 'max', and 'mean' word counts
        """
        self._load_model_and_tokenizer( backend=backend, device_map=device_map, mode="training" )
        
        df = pd.read_json(f"/{self.test_train_dir}/voice-commands-xml-train.jsonl", lines=True )#.sample( 1000, random_state=42 )
        
        token_stats = { "min": -1, "max": -1, "mean": -1}
        word_stats  = {"min": -1, "max": -1, "mean": -1}
        
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
    
    def fine_tune( self, batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.20, sample_size=1.0, device_map="auto", output_dir="./results" ):
        """
        Fine-tunes the model using PEFT (Parameter-Efficient Fine-Tuning) techniques.
        
        Preconditions:
        - The model and tokenizer must be available or loadable.
        - Valid test and train datasets must be accessible at the configured paths.
        - Sufficient GPU memory must be available for the specified batch size and model.
        
        Postconditions:
        - The model is fine-tuned with the specified parameters.
        - Training checkpoints are saved to the specified output directory.
        - Training statistics and metrics are captured and displayed.
        - The path to the last checkpoint directory is returned.
        - The following instance attributes are updated:
          - self.output_dir: Set to the output directory used for this fine-tuning run.
          - self.checkpoint_dir: Set to the directory of the last saved checkpoint.
        
        Parameters:
        - batch_size (int, optional): Batch size for training and evaluation. Defaults to 8.
        - gradient_accumulation_steps (int, optional): Number of steps to accumulate gradients. Defaults to 1.
        - logging_steps (float, optional): Fraction of total steps at which to log progress. Defaults to 0.05.
        - eval_steps (float, optional): Fraction of total steps at which to evaluate the model. Defaults to 0.20.
        - backend (str, optional): Backend to use for model computations. Defaults to "cuda".
        - sample_size (float, optional): Fraction of the total data to use (1.0 = all data). Defaults to 1.0.
        - device_map (str, optional): Device mapping strategy for the model. Defaults to "auto".
        - output_dir (str, optional): Directory to save the fine-tuned model checkpoints. Defaults to "./results".
        
        Returns:
        - str: Path to the directory containing the last saved checkpoint.
        """
        du.print_banner( f"Fine-tuning model {self.model_name} with PEFT", prepend_nl=True )
        run_start = f"Run started @ {du.get_current_time( format='%H:%M' )}"
        print( run_start )
        timer = Stopwatch( msg=None )
        
        self._load_model_and_tokenizer( device_map=device_map, mode="training" )
        
        # I used this when loading a quantized model. Since I'm not quantizing now, it's commented out
        # self.model         = prepare_model_for_kbit_training( self.model, gradientoow_checkpointing_kwargs={'use_reentrant': True} )
        peft_config        = self._get_peft_config()
        training_arguments = self._get_training_args( output_dir=output_dir, batch_size=batch_size, gradient_accumulation_steps=gradient_accumulation_steps, logging_steps=logging_steps, eval_steps=eval_steps )
        test_train_data    = self._get_test_train_data( sample_size=sample_size )
        
        du.print_banner( "Training data", prepend_nl=True )
        print( test_train_data[ "train" ] )
        du.print_banner( "Validation data", prepend_nl=True )
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
            formatting_func=self._format_prompt,
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
        """
        Returns the path to the last checkpoint directory from the most recent fine-tuning run.
        
        Preconditions:
        - A fine-tuning run has been completed, and self.checkpoint_dir has been set.
        
        Postconditions:
        - The path to the last checkpoint directory is returned, or None if no fine-tuning has been performed.
        
        Returns:
        - str or None: Path to the directory containing the last saved checkpoint, or None if no checkpoint is available.
        """
        return self.checkpoint_dir

    def _get_last_checkpoint_dir( self, output_dir ):
        """
        Determines the path to the most recent checkpoint directory within the given output directory.
        
        Preconditions:
        - `output_dir` is a valid directory path that contains checkpoint subdirectories.
        - Checkpoint directories follow the naming convention 'checkpoint-N' where N is the step number.
        
        Postconditions:
        - The path to the last checkpoint directory (with the highest step number) is returned.
        - If no checkpoint directories are found, None is returned.
        
        Parameters:
        - output_dir (str): Path to the directory containing the checkpoint subdirectories.
        
        Returns:
        - str or None: Path to the last checkpoint directory, or None if no checkpoints are found.
        """
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
        """
        Saves the current model and tokenizer to disk with timestamped directory name.
        
        Preconditions:
        - self.output_dir is set to a valid directory path.
        - self.model and self.tokenizer are properly initialized.
        
        Postconditions:
        - The model and tokenizer are saved to a timestamped subdirectory within self.output_dir.
        - The original working directory is preserved (method changes directory temporarily but restores it).
        
        Notes:
        - The model is saved with safe_serialization=False to avoid issues with distributed models.
        - The target directory is named with pattern: {self.output_dir}/final-{date}-at-{time}
        
        Returns:
        - None
        """
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
        """
        Loads a PEFT adapter from the specified path and applies it to the current model.
        
        Preconditions:
        - self.model must be initialized with a base model.
        - adapter_path must be a valid path to a saved PEFT adapter.
        
        Postconditions:
        - The adapter is loaded and applied to the model.
        - self.model is updated to be a PeftModel instance with the adapter applied.
        
        Parameters:
        - adapter_path (str): Path to the directory containing the saved adapter.
        
        Returns:
        - None
        """
        print( f"Loading adapter from {adapter_path}" )
        self.model = PeftModel.from_pretrained( self.model, adapter_path )
        print( f"Loading adapter from {adapter_path}... Done!" )
        
    def run_validation_in_memory( self,
        switch="in_memory", adapter_path=None,  path_prefix=du.get_project_root(), device_map={"": 0},
        sample_size=100, debug=None, verbose=None
    ):
        """
        Runs validation on the model with the specified adapter using in-memory inference.
        
        Preconditions:
        - A validation dataset must be available at f"{self.test_train_dir}/voice-commands-xml-validate.jsonl".
        - The model and tokenizer must be available or loadable.
        - If adapter_path is provided, it must be a valid path to a saved PEFT adapter.
        
        Postconditions:
        - The model is loaded with the specified adapter (if provided).
        - Validation is performed on a sample of the validation dataset.
        - Validation results are computed and displayed.
        - The processed DataFrame with validation results is returned.
        
        Parameters:
        - switch (str, optional): Switch parameter for the prompt generator. Defaults to "".
        - adapter_path (str, optional): Path to the adapter to load. If None, uses the adapter 
          from the most recent fine-tuning run if available. Defaults to None.
        - path_prefix (str, optional): Path prefix for the XML generator. Defaults to "/var/model/genie-in-the-box".
        - device_map (dict, optional): Device mapping for the model. Defaults to {"": 0}.
        - sample_size (int, optional): Number of samples to use for validation. Defaults to 1000.
        - debug (bool, optional): Enable debug mode. If None, uses the class default. Defaults to None.
        - verbose (bool, optional): Enable verbose mode. If None, uses the class default. Defaults to None.
        
        Returns:
        - pandas.DataFrame: DataFrame containing the validation results, including original prompts,
                          generated responses, and validation metrics.
        """
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
        
        xml_coordinator = XmlCoordinator( path_prefix=path_prefix, debug=debug, verbose=verbose )
        
        du.print_banner( "Querying LLM in memory" )
        # load model and tokenizer...
        self._load_model_and_tokenizer( device_map=device_map, mode="inference" )
        
        # ...and adapter...
        if adapter_path is not None:
            print( f"Loading adapter from user provided path: [{adapter_path}]" )
            self._load_adapter( adapter_path )
        elif self.checkpoint_dir is not None:
            print( f"Loading adapter created by the last fine tuning job: [{self.checkpoint_dir}]" )
            self._load_adapter( self.checkpoint_dir )
        else:
            print( "No adapter path provided or found, proceeding with validation, using model by itself" )
            
        # generate responses
        df = xml_coordinator.generate_responses(
            df, tokenizer=self.tokenizer, model=self.model, switch=switch, model_name=self.model_name, device="cuda",
            max_new_tokens=128, debug=debug, verbose=verbose
        )
        # validate responses
        df = xml_coordinator.validate_responses( df )
        # print validation stats
        xml_coordinator.print_validation_stats( df, title=f"Validation stats for model {self.model_name}" )
        
        return df
    
    def run_validation_with_server(
            self, model=None, switch="", path_prefix="/var/model/genie-in-the-box",
            device_map={"": 0}, sample_size=1000, debug=None, verbose=None
    ):
        """
        Runs validation against a model server rather than loading the model in memory.
        
        Preconditions:
        - A validation dataset must be available at f"{self.test_train_dir}/voice-commands-xml-validate.jsonl".
        - A model instance must be provided via the model parameter.
        - The tokenizer must be available or can be loaded.
        
        Postconditions:
        - Validation is performed on a sample of the validation dataset.
        - Validation results are computed and displayed.
        - The processed DataFrame with validation results is returned.
        
        Parameters:
        - model (object, required): Model server instance to use for inference. Must support the generation interface.
        - switch (str, optional): Switch parameter for the prompt generator. Defaults to "".
        - path_prefix (str, optional): Path prefix for the XML generator. Defaults to "/var/model/genie-in-the-box".
        - device_map (dict, optional): Device mapping for the model. Defaults to {"": 0}.
        - sample_size (int, optional): Number of samples to use for validation. Defaults to 1000.
        - debug (bool, optional): Enable debug mode. If None, uses the class default. Defaults to None.
        - verbose (bool, optional): Enable verbose mode. If None, uses the class default. Defaults to None.
        
        Returns:
        - pandas.DataFrame: DataFrame containing the validation results, including original prompts,
                          generated responses, and validation metrics.
                          
        Raises:
        - ValueError: If model is None.
        """
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
        
        xml_coordinator = XmlCoordinator( path_prefix=path_prefix, debug=debug, verbose=verbose )
        
        # generate responses
        df = xml_coordinator.generate_responses(
            df, tokenizer=self.tokenizer, model=self.model, switch=switch, model_name=self.model_name,
            device=device_map, max_new_tokens=128, debug=debug, verbose=verbose
        )
        # validate responses
        df = xml_coordinator.validate_responses( df )
        # print validation stats using the coordinator
        xml_coordinator.print_validation_stats( df, title=f"Validation stats for model {self.model_name}" )
        
        return df
    
    def load_and_merge_adapter( self, checkpoint_dir=None, device_map={"": 0} ):
        """
        Loads a PEFT adapter and merges it with the base model.
        
        Preconditions:
        - The model must be available or loadable.
        - If checkpoint_dir is provided, it must be a valid path to a saved PEFT adapter.
        - If checkpoint_dir is not provided, self.checkpoint_dir must be set to a valid adapter path.
        
        Postconditions:
        - The model is loaded if not already loaded.
        - The adapter is loaded and merged with the base model.
        - self.model is updated to contain the merged model.
        
        Parameters:
        - checkpoint_dir (str, optional): Path to the adapter checkpoint directory. If None, 
          uses self.checkpoint_dir. Defaults to None.
        - device_map (dict, optional): Device mapping for the model. Defaults to {"": 0}.
        
        Raises:
        - ValueError: If no adapter path is provided and self.checkpoint_dir is not set.
        """
        du.print_banner( f"Load and merge adapter {checkpoint_dir}" )
        self._load_model_and_tokenizer( device_map=device_map, mode="inference" )
        
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
        """
        Saves the merged model and tokenizer to a timestamped directory.
        
        Preconditions:
        - The model must have been loaded and merged with an adapter via load_and_merge_adapter.
        - If lora_dir is provided, it must be a valid directory path.
        - If lora_dir is not provided, self.lora_dir must be set to a valid directory path.
        
        Postconditions:
        - The merged model and tokenizer are saved to a timestamped subdirectory.
        - self.merged_adapter_dir is updated to the path of the saved merged adapter.
        - The path to the saved merged adapter is returned.
        
        Parameters:
        - lora_dir (str, optional): Base directory where the merged adapter will be saved. 
          If None, uses self.lora_dir. Defaults to None.
        
        Returns:
        - str: Path to the directory where the merged adapter was saved.
        
        Raises:
        - ValueError: If lora_dir is not provided and self.lora_dir is not set.
        """
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
        """
        Quantizes the merged model to reduce its size and memory footprint.
        
        Preconditions:
        - If merged_adapter_dir is provided, it must be a valid path to a saved merged model.
        - If merged_adapter_dir is not provided, self.merged_adapter_dir must be set to a valid path.
        - The Quantizer class must be properly implemented to handle the model quantization.
        
        Postconditions:
        - The merged model is quantized using the Quantizer.
        - The quantized model is saved to disk.
        - self.quantized_model_dir is updated with the path to the quantized model.
        - The path to the quantized model is returned.
        
        Parameters:
        - merged_adapter_dir (str, optional): Path to the merged adapter directory. 
          If None, uses self.merged_adapter_dir. Defaults to None.
        
        Returns:
        - str: Path to the directory containing the quantized model.
        
        Raises:
        - ValueError: If merged_adapter_dir is not provided and self.merged_adapter_dir is not set.
        """
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
    
    def _load_model_and_tokenizer( self, device_map="auto", mode=None ):
        """
        Loads the model and tokenizer for either training or inference.
        
        Preconditions:
        - The HF_HOME environment variable must be set.
        - The model_hf_id must be valid and the model must be available locally 
          (in the cache directory specified by HF_HOME).
        - The mode parameter must be either "training" or "inference".
        
        Postconditions:
        - The model is loaded with appropriate settings for the specified mode.
        - The tokenizer is loaded and configured properly for the model type and mode.
        - If the model and tokenizer were already loaded, this method does nothing.
        - The working directory remains unchanged, even though it temporarily changes during execution.
        
        Parameters:
        - device_map (str or dict, optional): Device mapping strategy for the model. Defaults to "auto".
        - mode (str, required): Mode of operation, must be either "training" or "inference".
        
        Raises:
        - ValueError: If HF_HOME is not set in the environment variables.
        - ValueError: If mode is not specified or not one of "training" or "inference".
        """
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
        else:
            print( "Model already loaded. Skipping" )
            
        if self.tokenizer is None:
            
            self.tokenizer = AutoTokenizer.from_pretrained( self.model_hf_id, force_download=True, from_slow=False )
            
            # Load the model-specific tokenizer configuration
            model_config = load_model_config(self.model_name)
            tokenizer_config = model_config["tokenizer"]
            
            # Apply tokenizer settings from configuration
            pad_token = tokenizer_config["pad_token"]
            
            # Handle different token attribute references
            if pad_token == "eos_token":
                self.tokenizer.pad_token = self.tokenizer.eos_token
            elif pad_token == "unk_token":
                self.tokenizer.pad_token = self.tokenizer.unk_token
                # Convert from unk_token if needed
                if tokenizer_config.get("pad_token_id") == "converted_from_unk_token":
                    self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
            else:
                # Direct string assignment
                self.tokenizer.pad_token = pad_token
                # Set ID if provided
                if "pad_token_id" in tokenizer_config and isinstance(tokenizer_config["pad_token_id"], int):
                    self.tokenizer.pad_token_id = tokenizer_config["pad_token_id"]
            
            # Set padding side based on mode
            if mode == "training":
                print(f"Setting padding side to '{tokenizer_config['padding_side']['training']}' for training")
                self.tokenizer.padding_side = tokenizer_config['padding_side']['training']
            elif mode == "inference":
                print(f"Setting padding side to '{tokenizer_config['padding_side']['inference']}' for inference")
                self.tokenizer.padding_side = tokenizer_config['padding_side']['inference']
            else:
                # this is checked above, this will never be called
                raise ValueError("Mode MUST be specified, either 'training' or 'inference'")
        else:
            print( "Tokenizer already loaded. Skipping" )
            
        if original_cwd != os.getcwd():
            print( f"Switching back to original working directory: {original_cwd}" )
            os.chdir( original_cwd )
            # print( f"New working directory: {os.getcwd()}" )
        
    def _get_peft_config( self ):
        """
        Creates a PEFT configuration tailored to the specific model being fine-tuned.
        
        Preconditions:
        - self.model_name must be one of the supported model names.
        
        Postconditions:
        - A LoraConfig object is returned with parameters appropriate for the model.
        
        Returns:
        - LoraConfig: Configuration object for PEFT (Parameter-Efficient Fine-Tuning).
        
        Notes:
        - Configuration is loaded dynamically from model-specific configuration files
        - Each model has its own LoRA parameters defined in training/conf/{model_name}.py
        """
        # Load the model-specific configuration
        model_config = load_model_config(self.model_name)
        lora_params = model_config["lora"]
        
        return LoraConfig(
            lora_alpha=lora_params["lora_alpha"],
            lora_dropout=lora_params["lora_dropout"],
            r=lora_params["r"],
            bias=lora_params["bias"],
            task_type=lora_params["task_type"],
            target_modules=lora_params["target_modules"]
        )
    
    def _get_training_args( self, output_dir="./results", batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.5 ):
        """
        Creates a configuration object with training arguments for the SFT trainer.
        
        Preconditions:
        - output_dir must be a valid directory path.
        - batch_size, gradient_accumulation_steps, logging_steps, and eval_steps must be valid values.
        
        Postconditions:
        - An SFTConfig object is returned with appropriate training parameters.
        - The output directory is created with a timestamped name.
        
        Parameters:
        - output_dir (str, optional): Base directory for training outputs. Defaults to "./results".
        - batch_size (int, optional): Batch size for training and evaluation. Defaults to 8.
        - gradient_accumulation_steps (int, optional): Number of steps to accumulate gradients. Defaults to 1.
        - logging_steps (float, optional): Fraction of total steps at which to log progress. Defaults to 0.05.
        - eval_steps (float, optional): Fraction of total steps at which to evaluate the model. Defaults to 0.5.
        
        Returns:
        - SFTConfig: Configuration object for Supervised Fine-Tuning.
        
        Notes:
        - Precision is automatically set to bf16 if supported, otherwise fp16.
        - Gradient checkpointing is disabled for speed (reduces memory by 40% but is 2x slower).
        - The max sequence length is model-specific, determined by _get_max_seq_length().
        """
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
            # what is this doing here?
            # dataset_text_field="text",
            max_seq_length=self._get_max_seq_length()
        )
    
    def _get_max_seq_length( self ):
        """
        Determines the maximum sequence length for training based on the model.
        
        Preconditions:
        - self.model_name must be one of the supported model names.
        
        Postconditions:
        - Returns an appropriate maximum sequence length for the specific model type.
        
        Returns:
        - int: The maximum sequence length loaded from the model configuration
        
        Raises:
        - ValueError: If self.model_name is not one of the supported models.
        """
        # Load the model-specific configuration
        model_config = load_model_config(self.model_name)
        return model_config["model"]["max_seq_length"]
        
    def _get_test_train_data( self, sample_size=1.0 ):
        """
        Loads and prepares the training and testing datasets.
        
        Preconditions:
        - self.model_name must be one of the supported model names.
        - self.test_train_dir must be a valid directory containing the required dataset files.
        - The dataset files must be in JSONL format.
        
        Postconditions:
        - Training and testing datasets are loaded and prepared for fine-tuning.
        - If sample_size < 1.0, only a fraction of the data is used.
        - Data is formatted according to the model requirements.
        
        Parameters:
        - sample_size (float, optional): Fraction of the data to use (1.0 = all data). Defaults to 1.0.
        
        Returns:
        - dict: Dictionary containing 'train' and 'test' datasets, each as a Dataset object.
        
        Raises:
        - ValueError: If self.model_name is not one of the supported models (via _validate_model_name).
        """
        if self.model_name in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]:
            extract_gpt_message = False
        else:
            self._validate_model_name()
        
        path = f"/{self.test_train_dir}/voice-commands-xml-train.jsonl"
        train_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        path = f"/{self.test_train_dir}/voice-commands-xml-test.jsonl"
        test_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        return {'train': train_dataset, 'test': test_dataset }
    
    def _get_dataset( self, path, sample_size=1.0, extract_gpt_message=False ):
        """
        Loads and processes a dataset from a JSONL file.
        
        Preconditions:
        - path must be a valid file path to a JSONL file.
        - sample_size must be a float between 0.0 and 1.0.
        - If extract_gpt_message is True, each JSON object must have a "gpt_message" field.
        
        Postconditions:
        - The data is loaded from the file and parsed from JSON.
        - If sample_size < 1.0, only the specified fraction of data is used.
        - If extract_gpt_message is True, only the "gpt_message" field is extracted from each JSON object.
        - A Dataset object is returned containing the processed data.
        
        Parameters:
        - path (str): Path to the JSONL dataset file.
        - sample_size (float, optional): Fraction of the data to use (1.0 = all data). Defaults to 1.0.
        - extract_gpt_message (bool, optional): If True, extract only the "gpt_message" field from each JSON object. 
                                               Defaults to False.
        
        Returns:
        - Dataset: Hugging Face Dataset object containing the processed data.
        """
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
        
    def _format_prompt( self, row ):
        """
        Formats a training example into a prompt suitable for the specific model.
        
        Preconditions:
        - row must be a dictionary-like object containing "instruction", "input", and "output" keys.
        - self.model_name must be one of the supported model names.
        
        Postconditions:
        - A formatted prompt string is returned in the appropriate format for the model type.
        
        Parameters:
        - row (dict): A dictionary containing "instruction", "input", and "output" fields.
        
        Returns:
        - str: A formatted prompt string suitable for the specified model type.
        
        Raises:
        - ValueError: If self.model_name is not one of the supported models.
        - KeyError: If row is missing any of the required fields.
        
        Notes:
        - The prompt format is loaded from the model-specific configuration file
        - Different models require different prompt formats that are defined in their config files
        """
        # Load the model-specific configuration
        model_config = load_model_config(self.model_name)
        template = model_config["model"]["prompt_template"]
        
        # Format using the template from the configuration
        # Check if last_tag_func exists in the configuration
        if "last_tag_func" in model_config["model"]:
            # Use the lambda function directly from the config
            last_tag_func = model_config["model"]["last_tag_func"]
            last_tag = last_tag_func(row["output"])
        else:
            last_tag = ""
            
        # Format the prompt with the template
        return template.format(
            instruction=row["instruction"],
            input=row["input"],
            output=row["output"],
            last_tag=last_tag
        )
    
    def get_prompt( self, instruction, input, output="" ):
        """
        Formats a prompt for a given model based on instruction, input, and optional output.
        
        Preconditions:
        - instruction and input must be valid strings.
        - self.model_name must be one of the supported model names.
        
        Postconditions:
        - A formatted prompt string is returned in the appropriate format for the model type.
        - If output is empty, the prompt is formatted for inference (generation).
        - If output is provided, the prompt is formatted for training.
        
        Parameters:
        - instruction (str): The instruction or task description.
        - input (str): The input data for the task.
        - output (str, optional): The expected output or response. Defaults to "".
        
        Returns:
        - str: A formatted prompt string suitable for the specified model type.
        
        Raises:
        - ValueError: If self.model_name is not one of the supported models.
        
        Notes:
        - The prompt format is loaded from the model-specific configuration file
        - For some models, the closing tag is only included if output is provided
        """
        # Load the model-specific configuration
        model_config = load_model_config(self.model_name)
        template = model_config["model"]["prompt_template"]
        
        # Check if last_tag_func exists in the configuration
        if "last_tag_func" in model_config["model"]:
            # Use the lambda function directly from the config
            last_tag_func = model_config["model"]["last_tag_func"]
            last_tag = last_tag_func(output)
        else:
            last_tag = ""
            
        # Format the prompt with the template
        return template.format(
            instruction=instruction,
            input=input,
            output=output,
            last_tag=last_tag
        )
    
    def _print_trainable_parameters( self ):
        """
        Prints the number of trainable parameters in the model.
        
        Preconditions:
        - self.model must be initialized and loaded.
        - The model must have named parameters that can be iterated over.
        
        Postconditions:
        - The count of trainable parameters, total parameters, and their ratio is printed to the console.
        
        Notes:
        - This is useful for verifying that parameter-efficient fine-tuning is correctly set up, 
          as only a small percentage of parameters should be trainable in PEFT methods.
        - No return value, the results are printed directly to the console.
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
        """
        Captures and prints GPU memory statistics before training.
        
        Preconditions:
        - CUDA must be available.
        - The GPU must be accessible through torch.cuda.
        
        Postconditions:
        - GPU device information and memory usage is captured and printed.
        - self.start_gpu_memory is set to the current reserved memory (used as baseline).
        - self.max_memory is set to the total available GPU memory.
        
        Notes:
        - This method is called before training to establish baseline memory usage.
        - Memory values are converted to GB and rounded to 3 decimal places.
        """
        gpu_stats = torch.cuda.get_device_properties( 0 )
        self.start_gpu_memory = round( torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3 )
        self.max_memory = round( gpu_stats.total_memory / 1024 / 1024 / 1024, 3 )
        print( f"GPU = {gpu_stats.name}. Max memory = {self.max_memory} GB." )
        print( f"{self.start_gpu_memory} GB of memory reserved." )
        
    def _print_stats_post( self ):
        """
        Captures and prints GPU memory statistics after training.
        
        Preconditions:
        - CUDA must be available.
        - The GPU must be accessible through torch.cuda.
        - _print_stats_pre must have been called before this method.
        - self.start_gpu_memory and self.max_memory must be initialized.
        
        Postconditions:
        - GPU memory usage statistics are calculated and printed.
        - Peak memory usage and memory usage specifically for training are displayed.
        - Memory usage is shown both in absolute values (GB) and as percentages of total memory.
        
        Notes:
        - This method is called after training to measure peak memory usage.
        - Training-specific memory usage is calculated as the difference from the baseline.
        - Memory values are converted to GB and rounded to 3 decimal places.
        """
        used_memory = round( torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3 )
        used_memory_for_trainer = round( used_memory - self.start_gpu_memory, 3 )
        used_percentage = round( used_memory / self.max_memory * 100, 3 )
        trainer_percentage = round( used_memory_for_trainer / self.max_memory * 100, 3 )
        print( f"Peak reserved memory = {used_memory} GB." )
        print( f"Peak reserved memory for training = {used_memory_for_trainer} GB." )
        print( f"Peak reserved memory % of max memory = {used_percentage} %." )
        print( f"Peak reserved memory for training % of max memory = {trainer_percentage} %." )
       
        # Note: Attempted to access self.trainer.metrics but SFTTrainer has no metrics attribute
        # AttributeError: 'SFTTrainer' object has no attribute 'metrics'
    
    def set_hf_env_vars( self, hf_home="/var/model/models", hf_hub_etag_timeout="60", hf_hub_download_timeout="60" ):
        """
        Sets environment variables for the Hugging Face model hub.
        
        Preconditions:
        - None specific, this method can be called at any time.
        
        Postconditions:
        - The HF_HOME, HF_HUB_ETAG_TIMEOUT, and HF_HUB_DOWNLOAD_TIMEOUT environment variables 
          are set to the specified values.
        - The environment variable values are printed to the console.
        
        Parameters:
        - hf_home (str, optional): Path to the Hugging Face cache directory. Defaults to "/var/model/models".
        - hf_hub_etag_timeout (str, optional): Timeout in seconds for etag requests. Defaults to "60".
        - hf_hub_download_timeout (str, optional): Timeout in seconds for downloads. Defaults to "60".
        
        Notes:
        - Setting HF_HOME is critical for proper functioning of model loading and caching.
        - The timeouts help prevent hanging if there are network issues during model downloads.
        - These environment variables are used by the Hugging Face Transformers library.
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
        Sets environment variables for the Genie in the Box application.
        
        Preconditions:
        - None specific, this method can be called at any time.
        
        Postconditions:
        - The GENIE_IN_THE_BOX_ROOT, GIB_CONFIG_MGR_CLI_ARGS, and WANDB_DISABLE_SERVICE 
          environment variables are set to the specified values.
        
        Parameters:
        - wandb_disable_service (str, optional): Whether to disable Weights & Biases logging service. 
                                                Defaults to "True".
        - gib_root (str, optional): Root directory of the Genie in the Box application. 
                                   Defaults to "/var/model/genie-in-the-box".
        
        Notes:
        - GIB_CONFIG_MGR_CLI_ARGS contains configuration paths for the application.
        - Setting WANDB_DISABLE_SERVICE to "True" prevents Weights & Biases from attempting to log training data.
        """
        os.environ[ "GENIE_IN_THE_BOX_ROOT"   ] = gib_root
        os.environ[ "GIB_CONFIG_MGR_CLI_ARGS" ] = "config_path=/src/conf/gib-app.ini splainer_path=/src/conf/gib-app-splainer.ini config_block_id=Genie+in+the+Box:+Development"
        os.environ[ "WANDB_DISABLE_SERVICE"   ] = wandb_disable_service
        
    def _start_vllm_server( self, quantized_model_dir, port=3000, max_model_len=2048, gpu_memory_utilization=0.75, timeout=180 ):
        """
        Starts a vLLM server for the quantized model and waits for it to be available.
        
        Preconditions:
        - quantized_model_dir must be a valid directory containing a quantized model.
        - DEEPILY_PROJECTS_DIR environment variable must be set to the projects directory.
        - vLLM must be installed in the virtual environment at $DEEPILY_PROJECTS_DIR/vllm-pip/.venv.
        
        Postconditions:
        - A vLLM server is started in a separate process.
        - The function waits until the server is available or until the timeout is reached.
        - Returns the process object for the vLLM server.
        
        Parameters:
        - quantized_model_dir (str): Path to the directory containing the quantized model.
        - port (int, optional): Port on which to run the vLLM server. Defaults to 3000.
        - max_model_len (int, optional): Maximum sequence length for the model. Defaults to 2048.
        - gpu_memory_utilization (float, optional): Fraction of GPU memory to use. Defaults to 0.75.
        - timeout (int, optional): Maximum time to wait for the server to start (seconds). Defaults to 180.
        
        Returns:
        - subprocess.Popen: Process object for the vLLM server.
        
        Raises:
        - ValueError: If DEEPILY_PROJECTS_DIR is not set.
        - TimeoutError: If the server does not start within the timeout period.
        """
        # Check if DEEPILY_PROJECTS_DIR is set
        projects_dir = os.environ.get( "DEEPILY_PROJECTS_DIR" )
        if not projects_dir:
            raise ValueError( "DEEPILY_PROJECTS_DIR environment variable is not set." )
        
        du.print_banner( "Starting vLLM server" )
        
        # Command to start the vLLM server
        cmd = f"cd {projects_dir}/vllm-pip; source .venv/bin/activate; vllm serve {quantized_model_dir} --port {port} --max-model-len {max_model_len} --gpu_memory_utilization {gpu_memory_utilization}"
        
        if self.debug:
            print( f"Command to start vLLM server: {cmd}" )
        
        # Start the vLLM server in a separate process
        process = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True )
        
        # Start a thread to read and print server output
        def print_server_output( process ):
            for line in process.stdout:
                if self.debug or self.verbose:
                    print( f"[vLLM Server] {line.strip()}" )
        
        output_thread = threading.Thread( target=print_server_output, args=( process, ), daemon=True )
        output_thread.start()
        
        # Wait for the server to be available
        print( f"Waiting for vLLM server to be available on port {port}..." )
        server_url = f"http://localhost:{port}/health"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get( server_url, timeout=1 )
                if response.status_code == 200:
                    print( f"vLLM server is available on port {port}" )
                    return process
            except requests.RequestException:
                # Server not yet available
                time.sleep( 2 )
                if self.debug:
                    elapsed = time.time() - start_time
                    print( f"  Waiting... ({elapsed:.1f}s / {timeout}s)" )
        
        # If we reach here, the server did not start within the timeout
        self._stop_vllm_server( process )
        raise TimeoutError( f"vLLM server did not start within {timeout} seconds" )
    
    def _stop_vllm_server( self, process ):
        """
        Stops the vLLM server process.
        
        Preconditions:
        - process must be a valid subprocess.Popen object representing the vLLM server process.
        
        Postconditions:
        - The vLLM server process is terminated.
        - Any child processes are also terminated.
        
        Parameters:
        - process (subprocess.Popen): The process object for the vLLM server.
        """
        if process:
            du.print_banner( "Stopping vLLM server" )
            
            # On Linux, use process group ID to kill all child processes
            if hasattr( os, 'killpg' ) and hasattr( process, 'pid' ):
                try:
                    # Send SIGTERM to process group
                    os.killpg( os.getpgid( process.pid ), 15 )
                    
                    # Wait for a clean exit, but not too long
                    process.wait( timeout=10 )
                except ( ProcessLookupError, subprocess.TimeoutExpired ):
                    # If it didn't exit cleanly, force kill
                    try:
                        os.killpg( os.getpgid( process.pid ), 9 )
                    except ProcessLookupError:
                        pass
            else:
                # Fallback for platforms without killpg
                process.terminate()
                try:
                    process.wait( timeout=10 )
                except subprocess.TimeoutExpired:
                    process.kill()
            
            print( "vLLM server has been stopped" )
    
    def do_all_the_things( self, pre_training_stats=False, post_training_stats=False ):
        """
        Executes the full training pipeline from fine-tuning to quantization.
        
        This method:
        1. Loads model-specific configuration
        2. Runs pre-training validation if requested
        3. Fine-tunes the model using the proper configuration for the model
        4. Merges the LoRA adapter with the base model
        5. Quantizes the merged model
        6. Optionally runs post-training validation
        
        Args:
            pre_training_stats (bool): Whether to run validation before training
            post_training_stats (bool): Whether to run validation after training
        """
        timer = Stopwatch( msg=None )
        trainer = PeftTrainer(
            args.model, args.model_name, args.test_train_path, lora_dir=args.lora_dir, debug=args.debug, verbose=args.verbose
        )
        
        trainer.login_to_hf()

        # Run a quick pretest in memory
        if pre_training_stats:
            # TODO: add runtime configuration for sample size
            trainer.run_validation_in_memory( device_map="auto", sample_size=100 )

        # Load model-specific fine-tuning configuration
        model_config     = load_model_config( trainer.model_name )
        fine_tune_params = model_config[ "fine_tune" ]

        # Fine-tune using the dynamically loaded configuration
        checkpoint_dir = trainer.fine_tune(
                            sample_size=fine_tune_params[ "sample_size" ],
                             batch_size=fine_tune_params[ "batch_size" ],
            gradient_accumulation_steps=fine_tune_params[ "gradient_accumulation_steps" ],
                          logging_steps=fine_tune_params[ "logging_steps" ],
                             eval_steps=fine_tune_params[ "eval_steps" ],
                             device_map=fine_tune_params[ "device_map" ],
                             output_dir=args.lora_dir
        )

        release_gpus( [ trainer.model, trainer.tokenizer ] )

        # Load and merge the adapter
        trainer.load_and_merge_adapter( checkpoint_dir=checkpoint_dir )
        merged_adapter_dir = trainer.save_merged_adapter( lora_dir=args.lora_dir )
        release_gpus( [ trainer.model, trainer.tokenizer ] )

        # Quantize the merged adapter
        quantized_model_dir = trainer.quantize_merged_adapter( merged_adapter_dir=merged_adapter_dir )

        # Print completion information
        timer.print( f"Finished fine-tuning, merging and quantizing {args.model_name}" )
        du.print_banner( f"Finished quantizing {args.model_name}" )
        print( f"Quantized model: {quantized_model_dir}" )
        du.print_simple_file_list( quantized_model_dir )
        
        # quantized_model_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-04-08-at-21-26/autoround-4-bits-sym.gptq/2025-04-08-at-21-47"
        if post_training_stats:
        
            # release GPU before doing anything else
            release_gpus( [ trainer.model, trainer.tokenizer ] )
            
            du.print_banner( f"Running post-training validation for {args.model_name}" )
            
            # Start vLLM server and wait for it to be available
            vllm_server_process = self._start_vllm_server( quantized_model_dir )
            
            # create a custom model name using as an ID the mount point for the recently quantized model directory
            model = Llm_v0.get_model( quantized_model_dir )
            # TODO: add runtime configuration for sample size
            trainer.run_validation_with_server(
                model=model, path_prefix=gib_root, switch="deepily", device_map="cuda:0", sample_size=1000, debug=False,
                verbose=False
            )
            
            # Terminate the vLLM server process
            self._stop_vllm_server( vllm_server_process )
    
def check_env():
    """
    Verifies that required environment variables are set for proper application functioning.

    Preconditions:
    - None, this function checks the environment variables itself.

    Postconditions:
    - If all required environment variables are set, the GENIE_IN_THE_BOX_ROOT path is returned.
    - If any required variables are missing, the function prints an error message and exits the program.

    Required Environment Variables:
    - NCCL_P2P_DISABLE: Should be set to "1" to disable peer-to-peer CUDA operations.
    - NCCL_IB_DISABLE: Should be set to "1" to disable InfiniBand communications.
    - GENIE_IN_THE_BOX_ROOT: Should point to the root directory of the application.
    - GIB_CONFIG_MGR_CLI_ARGS: Should contain configuration arguments for the application.

    Returns:
    - str: The value of GENIE_IN_THE_BOX_ROOT if all checks pass.

    Raises:
    - SystemExit: If any required environment variables are missing.
    """
    required_vars = [
        ("NCCL_P2P_DISABLE", "1"),
        ("NCCL_IB_DISABLE", "1"),
        ("GENIE_IN_THE_BOX_ROOT", "/some/foo/path"),
        ("GIB_CONFIG_MGR_CLI_ARGS", "")
    ]
    
    missing_vars = False
    
    for name, val in required_vars:
        if not os.getenv( name ):
            print( f"Please set env variable {name}={val}" )
            missing_vars = True
    
    if missing_vars:
        print( "Exiting due to missing environment variables" )
        sys.exit( 1 )
    
    return os.getenv( "GENIE_IN_THE_BOX_ROOT" )
    
def parse_arguments():
    """
    Parses command line arguments for the PEFT trainer application.

    Preconditions:
    - The script must be run with proper command line arguments.

    Postconditions:
    - Returns a Namespace object containing the parsed arguments.

    Required Arguments:
    - model: The Hugging Face model ID.
    - model_name: The name of the model (must be a supported model).
    - test_train_path: Path to the directory containing test/train data.
    - lora_dir: Directory for storing LoRA adapter files.

    Optional Arguments:
    - --debug: Flag to enable debug mode.
    - --verbose: Flag to enable verbose mode.

    Returns:
    - argparse.Namespace: Object containing the parsed command line arguments.
    """
    
    parser = argparse.ArgumentParser( description="PEFT trainer for language models" )
    
    # Required arguments
    parser.add_argument( "--model",           type=str, help="Model HuggingFace ID" )
    parser.add_argument( "--model-name",      type=str, help="Model name" )
    parser.add_argument( "--test-train-path", type=str, help="Path to test/train data" )
    parser.add_argument( "--lora-dir",        type=str, help="Directory for LORA files" )
    
    # Optional arguments
    parser.add_argument( "--debug",               action="store_true", help="Enable debug mode",              default=False )
    parser.add_argument( "--verbose",             action="store_true", help="Enable verbose mode",            default=False )
    parser.add_argument( "--pre-training-stats",  action="store_true", help="Run validation before training", default=False )
    parser.add_argument( "--post-training-stats", action="store_true", help="Run validation after training",  default=False )
    
    return parser.parse_args()

# and just like that, we no longer need this after transformers gets an update
# class MyKludgySFTTrainer( SFTTrainer ):
#     """
#     A custom extension of the SFTTrainer class that handles tokenizer padding side switching.
#
#     This class overrides the evaluation_loop method to ensure proper padding side configuration
#     during evaluation and training phases. It temporarily switches padding_side to 'left' for
#     evaluation and then back to 'right' for training.
#
#     Attributes:
#         Inherits all attributes from SFTTrainer.
#     """
#
#     def evaluation_loop( self, *args, **kwargs ):
#         """
#         Overrides the evaluation_loop method to handle tokenizer padding_side switching.
#
#         Preconditions:
#         - self.tokenizer must be initialized and have a padding_side attribute.
#
#         Postconditions:
#         - Tokenizer padding_side is set to 'left' during evaluation.
#         - Tokenizer padding_side is restored to 'right' after evaluation completes.
#         - The result from the parent class evaluation_loop is returned.
#
#         Parameters:
#         - *args: Positional arguments to pass to the parent class's evaluation_loop method.
#         - **kwargs: Keyword arguments to pass to the parent class's evaluation_loop method.
#
#         Returns:
#         - The result returned by the parent class's evaluation_loop method.
#         """
#         # Set padding_side to 'left' for evaluation
#         self.tokenizer.padding_side = 'left'
#         result = super().evaluation_loop( *args, **kwargs )
#         # Revert padding_side to 'right' after evaluation
#         self.tokenizer.padding_side = 'right'
#         return result
#
# def validate_model_name_arg( model_name ):
#     """
#     Validates that a given model name is in the list of supported models.
#
#     Preconditions:
#     - model_name must be a string.
#
#     Postconditions:
#     - If model_name is valid, the function completes without error.
#     - If model_name is not valid, a ValueError is raised.
#
#     Parameters:
#     - model_name (str): The model name to validate.
#
#     Raises:
#     - ValueError: If model_name is not one of the supported models.
#
#     Supported Models:
#     - "Mistral-7B-Instruct-v0.2"
#     - "Ministral-8B-Instruct-2410"
#     - "Llama-3.2-3B-Instruct"
#     - "Phi-4-mini-instruct"
#     """
#     supported_model_names = ["Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct"]
#     if model_name not in supported_model_names:
#         raise ValueError(f"Unsupported model_name: '{model_name}'. Must be one of: {', '.join(supported_model_names)}")
#
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
    gib_root = check_env()
    args     = parse_arguments()
    
    timer    = Stopwatch( msg=None )
    trainer  = PeftTrainer( args.model, args.model_name, args.test_train_path, lora_dir=args.lora_dir, debug=args.debug, verbose=args.verbose )
    
    trainer.login_to_hf()
    
    trainer.do_all_the_things( pre_training_stats=args.pre_training_stats, post_training_stats=args.post_training_stats )
    
    