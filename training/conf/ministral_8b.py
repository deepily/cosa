"""
Configuration for fine-tuning Ministral-8B-Instruct-2410 model.

This configuration module defines the parameters needed by the PEFT Trainer to fine-tune
the Mistral AI's Ministral-8B-Instruct-2410 model, which is a distilled version of the
larger Mistral model. The configuration is organized into four dictionaries that provide
model-specific parameters for the fine-tuning process:

1. fine_tune_config: Training parameters tailored for Ministral-8B:
   - sample_size: Small data fraction (1%) for quick experimentation
   - batch_size: Very small batch size (2) due to the model's large memory requirements
   - gradient_accumulation_steps: High value (8) to compensate for small batch size
   - logging/eval_steps: Regular evaluation at 10% epoch intervals
   - device_map: Automatic GPU memory management for large model

2. lora_config: LoRA parameters customized for Ministral's architecture:
   - lora_alpha: Scaling factor for LoRA updates (16)
   - lora_dropout: 5% dropout for regularization
   - r: Higher rank (32) specifically chosen to address the low trainable parameter 
        percentage in this model (as noted in the comment)
   - target_modules: Specific attention and MLP layers for adaptation

3. tokenizer_config: Ministral-specific tokenization settings:
   - pad_token: Uses end-of-sequence token for padding
   - padding_side: Right padding during training, left padding for inference

4. model_config: Parameters specific to Ministral's usage:
   - max_seq_length: Moderate sequence length capability (683 tokens)
   - prompt_template: Custom instruction format with [INST]/[/INST] tags
   - last_tag_func: Properly closes sequences with </s> token when needed

The PEFT Trainer uses this configuration through load_model_config() to appropriately
initialize and fine-tune the Ministral model with these optimized settings. The configuration
accounts for Ministral's specific characteristics as a distilled model with memory efficiency
and architectural differences from other models in the collection.
"""

fine_tune_config = {
    "sample_size": 0.01,
    "batch_size": 2,
    "gradient_accumulation_steps": 8,
    "logging_steps": 0.10,
    "eval_steps": 0.10,
    "device_map": "auto"
}

lora_config = {
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "r": 32,  # higher value to address low trainable parameter %
    "bias": "none",
    "task_type": "CAUSAL_LM",
    "target_modules": ["k_proj", "q_proj", "v_proj", "o_proj", "gate_proj", "down_proj", "up_proj"]
}

tokenizer_config = {
    "pad_token": "eos_token",
    "padding_side": {
        "training": "right",
        "inference": "left"
    }
}

model_config = {
    "max_seq_length": 683,
    "prompt_template": """<s>[INST]{instruction}

    {input}
    [/INST]
    {output}
    {last_tag}""",
    "last_tag_func": lambda output: "</s>" if output else ""
}
