"""
Configuration for fine-tuning Ministral-8B-Instruct-2410 model.
"""

fine_tune_config = {
    "sample_size": 1.0,
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
