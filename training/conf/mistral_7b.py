"""
Configuration for fine-tuning Mistral-7B-Instruct-v0.2 model.
"""

fine_tune_config = {
    "sample_size": 1.0,
    "batch_size": 4,
    "gradient_accumulation_steps": 6,
    "logging_steps": 0.10,
    "eval_steps": 0.10,
    "device_map": "auto"
}

lora_config = {
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "r": 4,
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
    "max_seq_length": 779,
    "prompt_template": """### Instruction:
            Use the Task below and the Input given to write a Response that can solve the following Task:
    
            ### Task:
            {instruction}
    
            ### Input:
            {input}
    
            ### Response:
            {output}
            """
}
