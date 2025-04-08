"""
Model configuration module for fine-tuning different language models.
"""

from importlib import import_module
import os

# Map model names to their configuration module paths
MODEL_CONFIG_MAP = {
    "Mistral-7B-Instruct-v0.2": "mistral_7b",
    "Ministral-8B-Instruct-2410": "ministral_8b",
    "Llama-3.2-3B-Instruct": "llama_3_2_3b",
    "Phi-4-mini-instruct": "phi_4_mini"
}

def load_model_config(model_name):
    """
    Dynamically load the configuration for a specific model.
    
    Args:
        model_name (str): Name of the model to load configuration for
        
    Returns:
        dict: Combined configuration dictionary with all settings
        
    Raises:
        ValueError: If the model name is not found in the configuration map
    """
    if model_name not in MODEL_CONFIG_MAP:
        raise ValueError(f"Unknown model: {model_name}. Available models: {', '.join(MODEL_CONFIG_MAP.keys())}")
        
    # Import the module from the model configuration map
    config_module = import_module(f".{MODEL_CONFIG_MAP[model_name]}", package="cosa.training.conf")
    
    # Combine all configurations into a single dictionary
    config = {
        "fine_tune": config_module.fine_tune_config,
        "lora": config_module.lora_config,
        "tokenizer": config_module.tokenizer_config,
        "model": config_module.model_config
    }
    
    return config
