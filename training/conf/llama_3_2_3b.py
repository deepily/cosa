"""
Configuration for fine-tuning Llama-3.2-3B-Instruct model.

This configuration module defines the parameters required by the PEFT Trainer to fine-tune
Meta's Llama-3.2-3B-Instruct model. The configuration is structured into four dictionaries
that specify different aspects of the training process optimized for this model's unique
architecture and requirements:

1. fine_tune_config: Training parameters customized for Llama-3.2-3B:
   - sample_size: Uses 100% of the training data (1.0)
   - batch_size: Moderate batch size (6) balancing throughput and memory usage
   - gradient_accumulation_steps: Medium value (4) for stable optimization
   - logging/eval_steps: Regular progress tracking at 10% epoch intervals
   - device_map: Automatic GPU memory allocation and management

2. lora_config: Low-Rank Adaptation settings specific to Llama's architecture:
   - lora_alpha: Scaling factor (16) for LoRA parameter updates
   - lora_dropout: Standard 5% dropout for regularization
   - r: Higher rank (64) allowing more expressive fine-tuning for this model
   - target_modules: Llama-specific attention and MLP components for adaptation

3. tokenizer_config: Llama-specific tokenization settings:
   - pad_token: Uses a specific padding token (128004) with custom identifier
   - padding_side: Right padding for training batches, left padding for inference

4. model_config: Llama-specific parameters:
   - max_seq_length: Context window size (683 tokens)
   - prompt_template: Instruction format using standard [INST]/[/INST] tags
   - last_tag_func: Ensures proper sequence termination with </s> token

The PEFT Trainer uses this configuration through the load_model_config() function to
properly initialize and fine-tune the Llama model with settings optimized for its
architecture. This configuration accounts for Llama 3.2's specific tokenization approach,
memory requirements, and architectural characteristics that differ from other models in
the collection.
"""

from typing import Union, Callable

fine_tune_config: dict[str, Union[float, int, str]] = {
    "sample_size": 1.0,
    "batch_size": 6,
    "gradient_accumulation_steps": 4,
    "logging_steps": 0.10,
    "eval_steps": 0.10,
    "device_map": "auto"
}

lora_config: dict[str, Union[int, float, str, list[str]]] = {
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "r": 64,
    "bias": "none",
    "task_type": "CAUSAL_LM",
    "target_modules": ["k_proj", "q_proj", "v_proj", "o_proj", "gate_proj", "down_proj", "up_proj"]
}

tokenizer_config: dict[str, Union[str, int, dict[str, str]]] = {
    "pad_token": "<|finetune_right_pad_id|>",
    "pad_token_id": 128004,
    "padding_side": {
        "training": "right",
        "inference": "left"
    }
}

model_config: dict[str, Union[int, str, Callable[[str], str]]] = {
    "max_seq_length": 683,
    "prompt_template": """<s>[INST]{instruction}

            {input}
            [/INST]
            {output}
            {last_tag}""",
    "last_tag_func": lambda output: "</s>" if output else ""
}
