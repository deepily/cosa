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

import cosa.utils.util as du
import cosa.utils.util_pytorch as dupt

from cosa.agents.v000.llm_v0 import Llm_v0
from cosa.training.quantizer import Quantizer
from cosa.utils.util_stopwatch import Stopwatch

from cosa.training.xml_coordinator import XmlCoordinator

set_seed( 42 )

@staticmethod
def is_root() -> bool:
    return os.geteuid() == 0

@staticmethod
def invoked_with_sudo() -> bool:
    return "SUDO_UID" in os.environ

@staticmethod
def print_gpu_memory():
    """
    Prints the current GPU memory usage and allocation for all available GPUs.
    
    Preconditions:
    - The function requires the torch library to be imported.
    - At least one CUDA-capable GPU should be available.
    
    Postconditions:
    - Current GPU memory usage statistics are printed to the console for each GPU.
    - If no GPU is available, a message indicating that is printed.
    
    Parameters:
    - None
    
    Notes:
    - This function is useful for monitoring GPU memory usage during model training or inference.
    - Reports total memory, allocated memory, and reserved memory for each GPU.
    """
    
    # Check if CUDA is available
    if not torch.cuda.is_available():
        print( "No CUDA-capable GPU available." )
        return
    
    # Get the number of GPUs
    gpu_count = torch.cuda.device_count()
    print( f"Found {gpu_count} GPU(s):" )
    
    # For each GPU, get and print memory stats
    for gpu_id in range( gpu_count ):
        # Get device properties
        gpu_stats = torch.cuda.get_device_properties( gpu_id )
        
        # Calculate memory metrics (in GB)
        total_memory = round( gpu_stats.total_memory / 1024 / 1024 / 1024, 3 )
        
        # Get per-device memory stats
        with torch.cuda.device( gpu_id ):
            # Get allocated memory (current memory usage)
            allocated_memory = round( torch.cuda.memory_allocated() / 1024 / 1024 / 1024, 3 )
            
            # Get cached/reserved memory (memory reserved by PyTorch allocator)
            reserved_memory = round( torch.cuda.memory_reserved() / 1024 / 1024 / 1024, 3 )
            
            # Get peak memory stats
            max_allocated = round( torch.cuda.max_memory_allocated() / 1024 / 1024 / 1024, 3 )
            max_reserved = round( torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3 )
        
        # Print GPU info and memory stats
        print( f"GPU {gpu_id}: {gpu_stats.name}" )
        print( f"  Total memory:     {total_memory} GB" )
        print( f"  Allocated memory: {allocated_memory} GB (peak: {max_allocated} GB)" )
        print( f"  Reserved memory:  {reserved_memory} GB (peak: {max_reserved} GB)" )
        print( f"  Utilization:      {round(allocated_memory/total_memory * 100, 1)}%" )
    
@staticmethod
def release_gpus( models, nuclear_kill_button=False ):
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
    - If nuclear_kill_button is True, GPU processes are forcefully terminated and GPUs are reset.
    
    Parameters:
    - models (Iterable): A collection of model objects to be released from GPU memory.
    - nuclear_kill_button (bool, optional): If True, forcefully terminates GPU processes and resets GPUs. Defaults to False.
    
    Notes:
    - This function handles models that might not have a 'cpu' method safely by checking
      for the attribute's existence and callability before invoking it.
    - This function is particularly useful after fine-tuning or inference to ensure 
      GPU memory is properly released for subsequent operations.
    - The nuclear_kill_button option should be used with caution as it forcefully terminates processes and resets GPUs.
    """
    
    du.print_banner( "Releasing GPU memory... BEFORE", prepend_nl=True )
    print_gpu_memory()
    
    for model in models:
        
        # move it to the CPU before deleting it, but test to make sure the attribute actually exists before you do
        model_name = type(model).__name__
        if hasattr( model, 'cpu' ) and callable( getattr( model, 'cpu' ) ):
            print( f"Moving model {model_name} to CPU before deleting it..." )
            model.cpu()
        else:
            print( f"Model {model_name} does not have a 'cpu' method, skipping..." )
        del model
        gc.collect()
        
    torch.cuda.empty_cache()

    # Force GPU reset if nuclear_kill_button is enabled
    if nuclear_kill_button:
        du.print_banner( "NUCLEAR OPTION: Force resetting GPU memory!", prepend_nl=True )
        
        # Get the number of GPUs available
        gpu_count = torch.cuda.device_count()
        print( f"Detected {gpu_count} GPU(s), forcing reset..." )
        
        try:
            # Launch external GPU cleanup but exclude self
            current_pid = os.getpid()
            
            # if they want to nuke the GPU and they're not running as root, then throw in the `sudo` cmd
            if is_root() and invoked_with_sudo():
                sudo_placeholder = ""
            else:
                sudo_placeholder = "sudo "
            cmd = f"{sudo_placeholder}nvidia-smi | grep -E '[0-9]+ +C ' | awk '{{print $5}}' | grep -v {current_pid} | xargs -r sudo kill -9"
            subprocess.run( cmd, shell=True, check=True )
            
            # Reset each GPU individually
            for gpu_id in range( gpu_count ):
                print( f"Resetting GPU {gpu_id}..." )
                subprocess.run( f"sudo nvidia-smi --gpu-reset -i {gpu_id}", shell=True, check=True )
                
            print( "GPU reset completed successfully" )
        except subprocess.CalledProcessError as e:
            print( f"Error during GPU reset: {e}" )
        except Exception as e:
            print( f"Unexpected error during GPU reset: {e}" )

    du.print_banner( "Releasing GPU memory... AFTER", prepend_nl=True )
    print_gpu_memory()

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
        du.print_banner( f"Initializing PEFT Trainer for {model_name}", prepend_nl=True )
        print( f"Model ID: {model_hf_id}" )
        print( f"Path to test/train data: {test_train_path}" )
        
        self.debug = debug
        self.verbose = verbose
        self.trainer = None
        self.model = None
        self.model_hf_id = model_hf_id
        self.tokenizer = None
        self.output_dir = None
        self.checkpoint_dir = None
        self.model_name = model_name
        self.test_train_dir = test_train_path
        self.lora_dir = lora_dir
        self.merged_adapter_dir = None
        self.quantized_model_dir = None
        
        # stats tracking
        self.start_gpu_memory = -1
        self.max_memory = -1
        
        # models supported by this trainer
        self.supported_model_names = [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410",
            "Llama-3.2-3B-Instruct", "Phi-4-mini-instruct" ]
        
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
            raise ValueError(
                f"Unsupported model_name: '{self.model_name}'. Must be one of: {', '.join( MODEL_CONFIG_MAP.keys() )}"
                )
        
        # Claude snuck another check in on me, don't know why it thought that I wanted backward compatibility
        # # For backward compatibility, also check supported_model_names
        # if hasattr(self, 'supported_model_names') and self.model_name not in self.supported_model_names:
        #     print(f"Warning: Model '{self.model_name}' not in self.supported_model_names. Updating supported_model_names.")
        #     self.supported_model_names = list(MODEL_CONFIG_MAP.keys())
    
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
    
    def get_training_prompt_stats( self, backend="cuda", device_map="auto", device="cuda:1", debug=False,
                                   verbose=False
                                   ):
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
        
        df = pd.read_json( f"/{self.test_train_dir}/voice-commands-xml-train.jsonl", lines=True
                           )  # .sample( 1000, random_state=42 )
        
        token_stats = { "min": -1, "max": -1, "mean": -1 }
        word_stats = { "min": -1, "max": -1, "mean": -1 }
        
        token_counts = [ ]
        word_counts = [ ]
        counter = 0
        for row in df.itertuples():
            
            prompt = self.get_prompt( getattr( row, "instruction" ), getattr( row, "input" ),
                                      output=getattr( row, "output" )
                                      )
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
    
    def fine_tune( self, batch_size=8, gradient_accumulation_steps=1, logging_steps=0.05, eval_steps=0.20,
                   sample_size=1.0, device_map="auto", output_dir="./results"
                   ):
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
        peft_config = self._get_peft_config()
        training_arguments = self._get_training_args( output_dir=output_dir, batch_size=batch_size,
                                                      gradient_accumulation_steps=gradient_accumulation_steps,
                                                      logging_steps=logging_steps, eval_steps=eval_steps
                                                      )
        test_train_data = self._get_test_train_data( sample_size=sample_size )
        
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
        print( f"Run completed @ {du.get_current_time( format='%H:%M' )}" )
        timer.print( msg=None )
        
        print( f"LORA checkpoints stashed here [{training_arguments.output_dir}]" )
        # the output directory contains the original lora_dir + date and time, and also now contains...
        self.output_dir = training_arguments.output_dir
        # ...the last checkpoint directory created by the fine-tuning job
        self.checkpoint_dir = self._get_last_checkpoint_dir( training_arguments.output_dir )
        
        du.print_banner( f"Last checkpoint: {self.checkpoint_dir}" )
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
    
    def run_validation_in_memory( self, banner_prefix="",
                                  switch="in_memory", adapter_path=None, path_prefix=du.get_project_root(),
                                  device_map={ "": 0 },
                                  validation_sample_size=100, debug=None, verbose=None
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
        - banner_prefix (str, optional): Prefix for banner display. Defaults to "".
        - switch (str, optional): Switch parameter for the prompt generator. Defaults to "in_memory".
        - adapter_path (str, optional): Path to the adapter to load. If None, uses the adapter 
          from the most recent fine-tuning run if available. Defaults to None.
        - path_prefix (str, optional): Path prefix for the XML generator. Defaults to project root.
        - device_map (dict, optional): Device mapping for the model. Defaults to {"": 0}.
        - validation_sample_size (int, optional): Number of samples to use for validation. Defaults to 100.
        - debug (bool, optional): Enable debug mode. If None, uses the class default. Defaults to None.
        - verbose (bool, optional): Enable verbose mode. If None, uses the class default. Defaults to None.
        
        Returns:
        - pandas.DataFrame: DataFrame containing the validation results, including original prompts,
                          generated responses, and validation metrics.
        """
        du.print_banner( f"{banner_prefix} Testing {self.model_name} w/ {validation_sample_size} samples in memory...".strip(), prepend_nl=True )
        
        # set debug and verbose to the class defaults if not provided
        if debug is None: debug = self.debug
        if verbose is None: verbose = self.verbose
        
        df = pd.read_json( f"{self.test_train_dir}/voice-commands-xml-validate.jsonl", lines=True ).sample(
            validation_sample_size, random_state=42
            )
        
        # update the prompt field
        # KLUDGE: this is a workaround for the fact that the prompt field is not being created when the validation df is created
        print( f"Updating the prompt field for [{validation_sample_size}] rows..." )
        df[ "prompt" ] = df.apply( lambda row: self.get_prompt( row[ "instruction" ], row[ "input" ], output="" ),
                                   axis=1
                                   )
        print( f"Updating the prompt field for [{validation_sample_size}] rows... Done!" )
        
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
    
    def run_validation_with_server( self, banner_prefix="",
            model=None, switch="", path_prefix="/var/model/genie-in-the-box",
            device_map={ "": 0 }, validation_sample_size=1000, debug=None, verbose=None
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
        - banner_prefix (str, optional): Prefix for banner display. Defaults to "".
        - model (object, optional): Model server instance to use for inference. Must support the generation interface. Defaults to None.
        - switch (str, optional): Switch parameter for the prompt generator. Defaults to "".
        - path_prefix (str, optional): Path prefix for the XML generator. Defaults to "/var/model/genie-in-the-box".
        - device_map (dict, optional): Device mapping for the model. Defaults to {"": 0}.
        - validation_sample_size (int, optional): Number of samples to use for validation. Defaults to 1000.
        - debug (bool, optional): Enable debug mode. If None, uses the class default. Defaults to None.
        - verbose (bool, optional): Enable verbose mode. If None, uses the class default. Defaults to None.
        
        Returns:
        - pandas.DataFrame: DataFrame containing the validation results, including original prompts,
                          generated responses, and validation metrics.
                          
        Raises:
        - ValueError: If model is None.
        """
        # set debug and verbose to the class defaults if not provided
        if debug is None: debug = self.debug
        if verbose is None: verbose = self.verbose
        
        if model is None:
            raise ValueError( "Model must be provided" )
        else:
            self.model = model
        
        du.print_banner( f"{banner_prefix} Testing model [{self.model}]".strip(), prepend_nl=True )
        
        df = pd.read_json(
            f"{self.test_train_dir}/voice-commands-xml-validate.jsonl", lines=True
        ).sample( validation_sample_size, random_state=42 )
        
        # update the prompt field
        # KLUDGE: this is a workaround for the fact that the prompt field is not being created when the validation df is created
        print( f"Updating the prompt field for [{validation_sample_size}] rows..." )
        df[ "prompt" ] = df.apply(
            lambda row: self.get_prompt( row[ "instruction" ], row[ "input" ], output="" ), axis=1
        )
        print( f"Updating the prompt field for [{validation_sample_size}] rows... Done!" )
        
        du.print_banner( f"Testing {self.model_name} w/ {validation_sample_size} samples via vLLM server...", prepend_nl=True )
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
    
    def load_and_merge_adapter( self, checkpoint_dir=None, device_map={ "": 0 } ):
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
        
        du.print_banner( f"Contents of: {self.merged_adapter_dir}" )
        du.print_simple_file_list( self.merged_adapter_dir )
        
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
        
        try:
            # Detect available GPUs
            num_gpus = torch.cuda.device_count()
            if num_gpus == 0:
                raise RuntimeError( "No GPUs available for quantization" )
            
            # Use specific device mapping rather than "auto" to avoid meta device issues
            if num_gpus == 1:
                # Use a specific device (cuda:0) instead of "auto" to prevent meta device placement
                device_map = "cuda:0"
                if self.debug: print( f"Using single GPU with device_map={device_map}" )
            else:
                # For multi-GPU setup, only use first GPU to avoid meta device issues
                device_map = "cuda:0"
                if self.debug: print( f"Multiple GPUs detected but using only first GPU with device_map={device_map}" )
            
            du.print_banner( f"Quantizing merged adapter in {self.merged_adapter_dir}", prepend_nl=True )
            
            # Initialize quantizer with specific device mapping
            quantizer = Quantizer( self.merged_adapter_dir, device_map=device_map, local_files_only=True )
            
            # Quantize with appropriate batch size for the GPU
            batch_size = 1  # Conservative batch size to prevent OOM
            quantizer.quantize_model( batch_size=batch_size )
            
            # Save the quantized model
            self.quantized_model_dir = quantizer.save( self.merged_adapter_dir, include_model_name=False )
            
            return self.quantized_model_dir
        
        except Exception as e:
            error_msg = f"Quantization failed: {str( e )}"
            if self.debug:
                import traceback
                traceback.print_exc()
                print( f"ERROR: {error_msg}" )
            raise RuntimeError( error_msg ) from e
    
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
        - mode (str, optional): Mode of operation, must be either "training" or "inference". Defaults to None.
        
        Raises:
        - ValueError: If HF_HOME is not set in the environment variables.
        - ValueError: If mode is not specified or not one of "training" or "inference".
        """
        # Quick sanity checks
        if "HF_HOME" not in os.environ:
            raise ValueError( "Environment variable HF_HOME must be set, try calling trainer.set_hf_env_vars() first?" )
        
        if mode is None or mode not in [ "training", "inference" ]:
            raise ValueError( "Mode MUST be specified, either 'training' or 'inference'" )
        
        torch_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        attn_implementation = "flash_attention_2"
        cache_dir = os.getenv( "HF_HOME" ) + "/hub"
        original_cwd = os.getcwd()
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
            model_config = load_model_config( self.model_name )
            tokenizer_config = model_config[ "tokenizer" ]
            
            # Apply tokenizer settings from configuration
            pad_token = tokenizer_config[ "pad_token" ]
            
            # Handle different token attribute references
            if pad_token == "eos_token":
                self.tokenizer.pad_token = self.tokenizer.eos_token
            elif pad_token == "unk_token":
                self.tokenizer.pad_token = self.tokenizer.unk_token
                # Convert from unk_token if needed
                if tokenizer_config.get( "pad_token_id" ) == "converted_from_unk_token":
                    self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids( self.tokenizer.pad_token )
            else:
                # Direct string assignment
                self.tokenizer.pad_token = pad_token
                # Set ID if provided
                if "pad_token_id" in tokenizer_config and isinstance( tokenizer_config[ "pad_token_id" ], int ):
                    self.tokenizer.pad_token_id = tokenizer_config[ "pad_token_id" ]
            
            # Set padding side based on mode
            if mode == "training":
                print( f"Setting padding side to '{tokenizer_config[ 'padding_side' ][ 'training' ]}' for training" )
                self.tokenizer.padding_side = tokenizer_config[ 'padding_side' ][ 'training' ]
            elif mode == "inference":
                print( f"Setting padding side to '{tokenizer_config[ 'padding_side' ][ 'inference' ]}' for inference" )
                self.tokenizer.padding_side = tokenizer_config[ 'padding_side' ][ 'inference' ]
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
        model_config = load_model_config( self.model_name )
        lora_params = model_config[ "lora" ]
        
        return LoraConfig(
            lora_alpha=lora_params[ "lora_alpha" ],
            lora_dropout=lora_params[ "lora_dropout" ],
            r=lora_params[ "r" ],
            bias=lora_params[ "bias" ],
            task_type=lora_params[ "task_type" ],
            target_modules=lora_params[ "target_modules" ]
        )
    
    def _get_training_args( self, output_dir="./results", batch_size=8, gradient_accumulation_steps=1,
                            logging_steps=0.05, eval_steps=0.5
                            ):
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
        model_config = load_model_config( self.model_name )
        return model_config[ "model" ][ "max_seq_length" ]
    
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
        if self.model_name in [ "Mistral-7B-Instruct-v0.2", "Ministral-8B-Instruct-2410", "Llama-3.2-3B-Instruct",
            "Phi-4-mini-instruct" ]:
            extract_gpt_message = False
        else:
            self._validate_model_name()
        
        path = f"/{self.test_train_dir}/voice-commands-xml-train.jsonl"
        train_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        path = f"/{self.test_train_dir}/voice-commands-xml-test.jsonl"
        test_dataset = self._get_dataset( path, sample_size=sample_size, extract_gpt_message=extract_gpt_message )
        
        return { 'train': train_dataset, 'test': test_dataset }
    
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
        model_config = load_model_config( self.model_name )
        template = model_config[ "model" ][ "prompt_template" ]
        
        # Format using the template from the configuration
        # Check if last_tag_func exists in the configuration
        if "last_tag_func" in model_config[ "model" ]:
            # Use the lambda function directly from the config
            last_tag_func = model_config[ "model" ][ "last_tag_func" ]
            last_tag = last_tag_func( row[ "output" ] )
        else:
            last_tag = ""
        
        # Format the prompt with the template
        return template.format(
            instruction=row[ "instruction" ],
            input=row[ "input" ],
            output=row[ "output" ],
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
        model_config = load_model_config( self.model_name )
        template = model_config[ "model" ][ "prompt_template" ]
        
        # Check if last_tag_func exists in the configuration
        if "last_tag_func" in model_config[ "model" ]:
            # Use the lambda function directly from the config
            last_tag_func = model_config[ "model" ][ "last_tag_func" ]
            last_tag = last_tag_func( output )
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
        os.environ[ "HF_HOME" ] = hf_home
        os.environ[ "HF_HUB_ETAG_TIMEOUT" ] = hf_hub_etag_timeout
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
        os.environ[ "GENIE_IN_THE_BOX_ROOT" ] = gib_root
        os.environ[
            "GIB_CONFIG_MGR_CLI_ARGS" ] = "config_path=/src/conf/gib-app.ini splainer_path=/src/conf/gib-app-splainer.ini config_block_id=Genie+in+the+Box:+Development"
        os.environ[ "WANDB_DISABLE_SERVICE" ] = wandb_disable_service
    
    def _start_vllm_server( self,
        quantized_model_dir, port=3000, max_model_len=2048, gpu_memory_utilization=0.75, timeout=180
    ):
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
        - If multiple GPUs are available, vLLM will be configured to use all of them.
        
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
        - RuntimeError: If the vLLM server process exits unexpectedly.
        """
        # Check if DEEPILY_PROJECTS_DIR is set
        projects_dir = os.environ.get( "DEEPILY_PROJECTS_DIR" )
        if not projects_dir: raise ValueError( "DEEPILY_PROJECTS_DIR environment variable is not set." )
        
        du.print_banner( "Starting vLLM server..." )
        
        # Check for multiple GPUs
        gpu_count = torch.cuda.device_count()
        gpu_devices = ",".join( str( i ) for i in range( gpu_count ) )
        
        if self.debug:
            print( f"Detected {gpu_count} GPU(s): {gpu_devices}" )
            for i in range( gpu_count ):
                gpu_name = torch.cuda.get_device_name( i )
                gpu_mem = torch.cuda.get_device_properties( i ).total_memory / (1024 ** 3)  # in GB
                print( f"  GPU {i}: {gpu_name} with {gpu_mem:.2f} GB memory" )
        
        # Build the vLLM command with GPU configuration
        if gpu_count > 1:
            # Configure vLLM to use all available GPUs
            tensor_parallel_size = gpu_count
            gpu_config = f"--tensor-parallel-size {tensor_parallel_size} --gpu-memory-utilization {gpu_memory_utilization}"
            if self.debug: print(
                f"Configuring vLLM to use multiple GPUs (tensor_parallel_size={tensor_parallel_size})"
                )
        else:
            # Use the single GPU with specified memory utilization
            gpu_config = f"--gpu-memory-utilization {gpu_memory_utilization}"
            if self.debug: print(
                f"Configuring vLLM to use a single GPU with memory utilization {gpu_memory_utilization}"
                )
        
        # Command to start the vLLM server
        cmd = f"cd {projects_dir}/vllm-pip; source .venv/bin/activate; CUDA_VISIBLE_DEVICES={gpu_devices} vllm serve {quantized_model_dir} --port {port} --max-model-len {max_model_len} {gpu_config}"
        
        if self.debug: print( f"Command to start vLLM server: {cmd}" )
        
        # Create error log capture
        server_log = [ ]
        server_error = None
        
        # Define function to monitor process status
        def check_process_status( process, log ):
            """Monitor subprocess status and capture any error if it exits prematurely"""
            nonlocal server_error
            return_code = process.poll()
            if return_code is not None:
                # Process exited
                stderr_output = process.stderr.read()
                if stderr_output:
                    error_msg = f"vLLM server exited with code {return_code}. Error: {stderr_output}"
                    server_error = RuntimeError( error_msg )
                    print( f"[vLLM Server ERROR] {error_msg}" )
                    # Add to log
                    log.append( f"EXIT CODE {return_code}: {stderr_output}" )
                return False
            return True
        
        # Start the vLLM server in a separate process with its own process group
        process = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    start_new_session=True
                                    )
        
        # Start a thread to read and print server output
        def print_server_output( process, log ):
            for line in process.stdout:
                log.append( line.strip() )
                if self.debug and self.verbose:
                    print( f"[vLLM Server] {line.strip()}" )
                # Check if any known error patterns appear in the output
                if "CUDA out of memory" in line or "CUDA error" in line or "Error:" in line:
                    print( f"[vLLM Server ERROR] Detected error: {line.strip()}" )
        
        output_thread = threading.Thread( target=print_server_output, args=(process, server_log), daemon=True )
        output_thread.start()
        
        # Wait for the server to be available
        print( f"Waiting for vLLM server to be available on port {port}. This could take a couple minutes..." )
        server_url = f"http://localhost:{port}/health"
        start_time = time.time()
        
        # Keep track of how many times we've checked for status to periodically check process health
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # Every 5 checks, verify the process is still running
            if check_count % 5 == 0:
                if not check_process_status( process, server_log ):
                    if server_error:
                        raise server_error
                    else:
                        raise RuntimeError( "vLLM server process terminated unexpectedly" )
            
            try:
                response = requests.get( server_url, timeout=1 )
                if response.status_code == 200:
                    if self.debug or self.verbose:
                        print( f"vLLM server successfully started and is responding on port {port}" )
                        # Get and print server info if in debug mode
                        try:
                            info_response = requests.get( f"http://localhost:{port}/v1/models", timeout=1 )
                            print( f"Server model info: {info_response.json()}" )
                        except Exception as e:
                            print( f"Could not fetch server info: {str( e )}" )
                    else:
                        print( f"vLLM server is now available on port {port}" )
                    return process
            except requests.RequestException:
                # Server not yet available
                time.sleep( 2 )
                elapsed = time.time() - start_time
                if self.debug:
                    print( f"  Waiting... ({elapsed:.1f}s of max {timeout}s)" )
                # Print a progress message every 30 seconds even without debug mode
                elif elapsed % 30 < 2:  # This ensures the message prints only once near each 30s mark
                    print( f"  Still waiting for vLLM server... ({int( elapsed )}s of max {timeout}s)" )
        
        # If we reach here, the server did not start within the timeout
        # if self.debug or self.verbose:
        print( "vLLM server startup timed out. Last log entries:" )
        for entry in server_log[ -10: ]:  # Show last 10 log entries
            print( f"  {entry}" )
        
        self._stop_vllm_server( process )
        
        # Consolidate the logs for the error message
        log_tail = "\n".join( server_log[ -20: ] ) if server_log else "No log output captured"
        raise TimeoutError( f"vLLM server did not start within {timeout} seconds.\nLast log entries:\n{log_tail}" )
    
    def _stop_vllm_server( self, process ):
        """
        Stops the vLLM server process (spawned with start_new_session=True).
        
        Preconditions:
        - process must be a valid subprocess.Popen object representing the vLLM server process.
        - Process should have been created with start_new_session=True.
        
        Postconditions:
        - The vLLM server process is terminated.
        - Any child processes in the same process group are also terminated.
        
        Parameters:
        - process (subprocess.Popen): The process object for the vLLM server.
        
        Returns:
        - bool: True if the server was successfully stopped, False otherwise.
        """
        if not process:
            return False
        
        du.print_banner( "Stopping vLLM server...", prepend_nl=True )
        
        try:
            # Process was started with start_new_session=True, so its PID is the group ID
            # Send SIGTERM to the child's own process group
            if self.debug: print( f"Sending SIGTERM to process group {process.pid}" )
            os.killpg( process.pid, 15 )  # SIGTERM
            
            # Wait for a clean exit, but not too long
            try:
                process.wait( timeout=10 )
                if self.debug: print( "vLLM server exited cleanly" )
            except subprocess.TimeoutExpired:
                if self.debug: print( "vLLM server did not exit after SIGTERM, sending SIGKILL" )
                # If it didn't exit cleanly, force kill
                try:
                    os.killpg( process.pid, 9 )  # SIGKILL
                except ProcessLookupError:
                    # Process is already gone
                    pass
        except (ProcessLookupError, OSError) as e:
            if self.debug: print( f"Error stopping vLLM server: {str( e )}" )
            # Process is already gone or we can't send signal
            # Just ensure we kill the direct process
            try:
                process.terminate()
            except:
                pass
        
        if self.debug: print( "vLLM server has been stopped" )
        return True
    
    def run_pipeline( self,
        pre_training_stats=False, post_training_stats=False, post_quantization_stats=False, nuclear_kill_button=False,
        validation_sample_size=100
    ):
        """
        Executes the full training pipeline from fine-tuning to quantization.
        
        Requires:
            - The trainer instance must be properly initialized with valid model_hf_id, model_name, and test_train_path
            - Hugging Face credentials must be available for login
            - If lora_dir is provided, it must be a valid directory path or creatable
            - GPU resources must be available with sufficient VRAM for the model
            - Required datasets must be available at test_train_path
            - The specified model must be one of the supported models
        
        Ensures:
            - If pre_training_stats is True, validation is performed before training
            - The model is fine-tuned with LoRA adapters
            - The LoRA adapter is merged with the base model
            - A quantized version of the merged model is created
            - If post_training_stats is True, validation is performed after merging the adapter
            - If post_quantization_stats is True, validation is performed after quantizing the model
            - All processes (including vLLM server) are properly cleaned up regardless of success or failure
            - The pipeline steps are executed in the correct sequence
            - GPU memory is properly released between steps
            - The following instance attributes are updated:
              - self.checkpoint_dir: Set to the path of the last training checkpoint
              - self.merged_adapter_dir: Set to the path of the merged adapter
              - self.quantized_model_dir: Set to the path of the quantized model
        
        Raises:
            - ValueError: If required paths or credentials are invalid
            - RuntimeError: If GPU resources are insufficient or if model loading fails
            - TimeoutError: If the vLLM server does not start within the specified timeout
        """
        timer = Stopwatch( msg=None )
        
        self.login_to_hf()
        
        # Run a quick pretest in memory
        if pre_training_stats:
            self.run_validation_in_memory( banner_prefix="PRE-training: ", device_map="auto", validation_sample_size=validation_sample_size )
        else:
            print( f"Skipping pre-training validation for {args.model_name}" )
        
        # Load model-specific fine-tuning configuration
        model_config = load_model_config( self.model_name )
        fine_tune_params = model_config[ "fine_tune" ]
        
        # Fine-tune using the dynamically loaded configuration
        checkpoint_dir = self.fine_tune(
            sample_size=fine_tune_params[ "sample_size" ],
            batch_size=fine_tune_params[ "batch_size" ],
            gradient_accumulation_steps=fine_tune_params[ "gradient_accumulation_steps" ],
            logging_steps=fine_tune_params[ "logging_steps" ],
            eval_steps=fine_tune_params[ "eval_steps" ],
            device_map=fine_tune_params[ "device_map" ],
            output_dir=args.lora_dir
        )
        release_gpus( [ self.model, self.tokenizer ] )
        
        # Load and merge the adapter
        self.load_and_merge_adapter( checkpoint_dir=checkpoint_dir )
        merged_adapter_dir = self.save_merged_adapter( lora_dir=args.lora_dir )
        release_gpus( [ self.model, self.tokenizer ] )
        
        if post_training_stats:
            vllm_server_process = None
            try:
                # Start vLLM server and wait for it to be available
                vllm_server_process = self._start_vllm_server( merged_adapter_dir )
                
                # create a custom model name using as an ID the mount point for the recently quantized model directory
                model = Llm_v0.get_model( merged_adapter_dir )
                self.run_validation_with_server(
                    banner_prefix="POST-training:", model=model, path_prefix=gib_root, switch="deepily", device_map="cuda:0",
                    validation_sample_size=validation_sample_size, debug=self.debug, verbose=self.verbose
                )
            finally:
                # Always clean up the vLLM server process if it was started
                if vllm_server_process: self._stop_vllm_server( vllm_server_process )
                # release GPUs -- with prejudice -- before doing anything else
                release_gpus( [ self.model, self.tokenizer ], nuclear_kill_button=nuclear_kill_button )
        else:
            print( f"Skipping post-training validation for {args.model_name}" )
        
        # Quantize the merged adapter
        quantized_model_dir = self.quantize_merged_adapter( merged_adapter_dir=merged_adapter_dir )
        
        if post_quantization_stats:
            vllm_server_process = None
            try:
                # Start vLLM server and wait for it to be available
                vllm_server_process = self._start_vllm_server( quantized_model_dir )
                
                # create a custom model name using as an ID the mount point for the recently quantized model directory
                model = Llm_v0.get_model( quantized_model_dir )
                self.run_validation_with_server(
                    banner_prefix="POST-quantization:", model=model, path_prefix=gib_root, switch="deepily", device_map="cuda:0",
                    validation_sample_size=validation_sample_size, debug=self.debug, verbose=self.verbose
                )
            finally:
                # Always clean up the vLLM server process if it was started
                if vllm_server_process: self._stop_vllm_server( vllm_server_process )
                # release GPU before doing anything else
                release_gpus( [ self.model, self.tokenizer ] )
        else:
            print( f"Skipping post-quantization validation for {args.model_name}" )
        
        # Print completion information
        print()
        msg = f"Finished fine-tuning, merging and quantizing {args.model_name}"
        timer.print( msg )
        du.print_banner( msg )
        print( f"Quantized model: {quantized_model_dir}" )
        du.print_simple_file_list( quantized_model_dir )
    
    def run_pipeline_adhoc( self, pre_training_stats=False, post_training_stats=False, post_quantization_stats=False, nuclear_kill_button=False,
        validation_sample_size=100
    ):
        """
        Executes a customized version of the training pipeline for debugging and testing purposes.
        
        Requires:
            - The trainer instance must be properly initialized with valid model_hf_id, model_name, and test_train_path
            - Hugging Face credentials must be available for login
            - A valid merged adapter directory must be specified in the hardcoded path or be created during execution
            - GPU resources must be available with sufficient VRAM for the model
            - The specified model must be one of the supported models
        
        Ensures:
            - Various pipeline steps can be enabled/disabled through code modifications for debugging
            - All enabled steps are executed in the correct sequence
            - If pre_training_stats is True and the code is uncommented, validation is performed before training
            - If post_training_stats is True and the code is uncommented, validation is performed after merging the adapter
            - The quantization step is always executed with the hardcoded merged adapter path
            - If post_quantization_stats is True and the code is uncommented, validation is performed after quantization
            - All processes (including vLLM server) are properly cleaned up regardless of success or failure
            - GPU memory is properly released after the quantization step
            - The following instance attributes are updated (for the steps that are executed):
              - self.checkpoint_dir: Set to the path of the last training checkpoint
              - self.merged_adapter_dir: Set to the path of the merged adapter
              - self.quantized_model_dir: Set to the path of the quantized model
        
        Raises:
            - ValueError: If required paths or credentials are invalid
            - RuntimeError: If GPU resources are insufficient or if model loading fails
            - Various exceptions based on which parts of the pipeline are enabled for testing
        
        Notes:
            - This method is intended for development and debugging only
            - Parts of the pipeline are commented out to allow targeted testing of specific components
            - The commented sections should be adjusted based on the specific testing needs
        """
        timer = Stopwatch( msg=None )
        
        self.login_to_hf()
        
        # # Run a quick pretest in memory
        # if pre_training_stats:
        #     # TODO: add runtime configuration for sample size
        #     self.run_validation_in_memory( device_map="auto", validation_sample_size=validation_sample_size )
        # else:
        #     print( f"Skipping pre-training validation for {args.model_name}" )
        #
        # # Load model-specific fine-tuning configuration
        # model_config     = load_model_config( self.model_name )
        # fine_tune_params = model_config[ "fine_tune" ]
        #
        # # Fine-tune using the dynamically loaded configuration
        # checkpoint_dir = self.fine_tune(
        #                     sample_size=fine_tune_params[ "sample_size" ],
        #                      batch_size=fine_tune_params[ "batch_size" ],
        #     gradient_accumulation_steps=fine_tune_params[ "gradient_accumulation_steps" ],
        #                   logging_steps=fine_tune_params[ "logging_steps" ],
        #                      eval_steps=fine_tune_params[ "eval_steps" ],
        #                      device_map=fine_tune_params[ "device_map" ],
        #                      output_dir=args.lora_dir
        # )
        #
        # release_gpus( [ self.model, self.tokenizer ] )
        #
        # # Load and merge the adapter
        # self.load_and_merge_adapter( checkpoint_dir=checkpoint_dir )
        # merged_adapter_dir = self.save_merged_adapter( lora_dir=args.lora_dir )
        release_gpus( [ self.model, self.tokenizer ] )
        
        # merged_adapter_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-04-29-at-12-04"
        merged_adapter_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Mistral-7B-Instruct-v0.2.lora/merged-on-2025-05-01-at-02-10"
        # 
        # if post_training_stats:
        #     du.print_banner( f"Running post-training validation for {args.model_name}", prepend_nl=True )
        #
        #     vllm_server_process = None
        #     try:
        #         # Start vLLM server and wait for it to be available
        #         vllm_server_process = self._start_vllm_server( merged_adapter_dir )
        #
        #         # create a custom model name using as an ID the mount point for the recently quantized model directory
        #         model = Llm_v0.get_model( merged_adapter_dir )
        #         # TODO: add runtime configuration for sample size
        #         self.run_validation_with_server(
        #             model=model, path_prefix=gib_root, switch="deepily", device_map="cuda:0", validation_sample_size=100, debug=False,
        #             verbose=False
        #         )
        #     finally:
        #         # Always clean up the vLLM server process if it was started
        #         if vllm_server_process: self._stop_vllm_server( vllm_server_process )
        #         # release GPU before doing anything else
        #         release_gpus( [ self.model, self.tokenizer ], nuclear_kill_button=nuclear_kill_button )
        # else:
        #     print( f"Skipping post-training validation for {args.model_name}" )
        
        # Quantize the merged adapter
        quantized_model_dir = self.quantize_merged_adapter( merged_adapter_dir=merged_adapter_dir )
        
        # release GPU before doing anything else
        release_gpus( [ self.model, self.tokenizer ] )
        
        # quantized_model_dir = "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora/merged-on-2025-04-08-at-21-26/autoround-4-bits-sym.gptq/2025-04-08-at-21-47"
        if post_quantization_stats:
            
            du.print_banner( f"Running post-training validation for {args.model_name}", prepend_nl=True )
            
            vllm_server_process = None
            try:
                # Start vLLM server and wait for it to be available
                vllm_server_process = self._start_vllm_server( quantized_model_dir )
                
                # create a custom model name using as an ID the mount point for the recently quantized model directory
                model = Llm_v0.get_model( quantized_model_dir )
                # TODO: add runtime configuration for sample size
                self.run_validation_with_server(
                    model=model, path_prefix=gib_root, switch="deepily", device_map="cuda:0",
                    validation_sample_size=validation_sample_size, debug=False,
                    verbose=False
                )
            finally:
                # Always clean up the vLLM server process if it was started
                if vllm_server_process: self._stop_vllm_server( vllm_server_process )
                # release GPU before doing anything else
                release_gpus( [ self.model, self.tokenizer ] )
        else:
            print( f"Skipping post-quantization validation for {args.model_name}" )
        
        # Print completion information
        msg = f"Finished fine-tuning, merging and quantizing {args.model_name}"
        timer.print( msg )
        du.print_banner( msg )
        print( f"Quantized model: {quantized_model_dir}" )
        du.print_simple_file_list( quantized_model_dir )


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
        ( "HF_HOME", "/some/foo/path" ),
        ( "NCCL_P2P_DISABLE", "1" ),
        ( "NCCL_IB_DISABLE", "1" ),
        ( "GENIE_IN_THE_BOX_ROOT", "/some/foo/path" ),
        ( "GIB_CONFIG_MGR_CLI_ARGS", "" ),
        ( "DEEPILY_PROJECTS_DIR", "/mnt/DATA01/include/www.deepily.ai/projects" )
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


@staticmethod
def check_privileges(debug=False):
    """
    Checks if the script is running with root privileges or with sudo.
    
    Preconditions:
    - None
    
    Postconditions:
    - If running with root privileges, prints a confirmation message
    - If running with sudo, prints a confirmation message
    - If not running with elevated privileges, exits the program
    
    Returns:
    - None
    
    Raises:
    - SystemExit: If the script is not running with elevated privileges
    """
    print( "Checking credentials..." )
    if is_root():
        if invoked_with_sudo():
            if debug: print( "✅ Running under sudo (uid 0, SUDO_UID present)" )
        else:
            if debug: print( "⚠️ Running as root but not via sudo (e.g. direct root or setuid)" )
    else:
        du.print_banner( "❌ Wait! You're not running with elevated privileges?!?", prepend_nl=True )
        print( "This is a long running -- up to three or four hours -- process that occasionally needs to hit the nuclear reset button for GPU memory." )
        print( "Because of this you will need to execute this module using `sudo` as a prefix so that we can dislodge the occasional pesky stuck memory" )
        print( "allocations w/o having to wake you up at midnight to present your credentials just so we can finish the last 1/3 of the run." )
        print()
        print( "You'll need to insert the following [bits] *between* 'sudo' and the Python interpreter:" )
        print( 'sudo [--preserve-env=HF_HOME,NCCL_P2P_DISABLE,NCCL_IB_DISABLE,GENIE_IN_THE_BOX_ROOT,GIB_CONFIG_MGR_CLI_ARGS,DEEPILY_PROJECTS_DIR env "PATH=$PATH"] python -m cosa.training.peft_trainer ...' )
        print()
        sys.exit( 1 )


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
    parser.add_argument( "--debug",                   action="store_true", help="Enable debug mode",                          default=False )
    parser.add_argument( "--verbose",                 action="store_true", help="Enable verbose mode",                        default=False )
    parser.add_argument( "--pre-training-stats",      action="store_true", help="Run validation before training",             default=False )
    parser.add_argument( "--post-training-stats",     action="store_true", help="Run validation after training and merging",  default=False )
    parser.add_argument( "--post-quantization-stats", action="store_true", help="Run validation after quantization",          default=False )
    parser.add_argument( "--nuclear-kill-button",     action="store_true", help="Enable nuclear option for GPU memory reset", default=False )
    
    parser.add_argument( "--validation-sample-size",  type=int,            help="Sample size for validation",                 default=100 )
    
    return parser.parse_args()

if __name__ == "__main__":
    
    # Check for required environment variables
    gib_root = check_env()
    
    # Validate command line arguments
    args = parse_arguments()
    
    # Check for nuclear_kill_button + elevated privileges
    if args.nuclear_kill_button:
        if args.debug: print( "Nuclear kill button is enabled..." )
        check_privileges( debug=args.debug )
    else:
        if args.debug: print( "Nuclear kill button is disabled..." )
        
    # instantiate a trainer...
    trainer = PeftTrainer(
        args.model, args.model_name, args.test_train_path, lora_dir=args.lora_dir, debug=args.debug, verbose=args.verbose
    )
    
    # ... And you're off to the races!
    trainer.run_pipeline(
        pre_training_stats=args.pre_training_stats,
        post_training_stats=args.post_training_stats,
        post_quantization_stats=args.post_quantization_stats,
        validation_sample_size=args.validation_sample_size,
        nuclear_kill_button=args.nuclear_kill_button
    )
    # DO NOT REMOVE THIS LINE! Use call below for debugging
    # trainer.run_pipeline_adhoc(
    #     pre_training_stats=args.pre_training_stats,
    #     post_training_stats=args.post_training_stats,
    #     post_quantization_stats=args.post_quantization_stats,
    #     validation_sample_size=args.validation_sample_size,
    #     nuclear_kill_button=args.nuclear_kill_button
    # )
