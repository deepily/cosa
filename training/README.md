# COSA PEFT Trainer

This directory contains tools for Parameter-Efficient Fine-Tuning (PEFT) of large language models using LoRA (Low-Rank Adaptation).

## Overview

The PEFT Trainer provides a streamlined pipeline for:
1. Fine-tuning models with LoRA adapters
2. Merging adapters with the base model
3. Quantizing models for efficient deployment
4. Validating model performance at various stages

## Requirements

- Python 3.8+
- PyTorch 2.0+
- Hugging Face Transformers
- PEFT library
- vLLM (for serving quantized models)
- DEEPILY_PROJECTS_DIR environment variable set
- Root privileges for GPU memory management

## Usage

### Basic Command

```bash
# IMPORTANT: Must run with sudo for GPU memory management
sudo python peft_trainer.py \
  --model <huggingface_model_id> \
  --model-name <model_config_name> \
  --test-train-path <path_to_training_data> \
  --lora-dir <output_directory_for_lora_adapters>
```

> **Root Privileges Required**: The trainer must be run with `sudo` as it occasionally needs to perform GPU memory cleanup operations (resetting stuck CUDA processes) during long training runs. Without proper permissions, the trainer will exit with an error message if not run with elevated privileges.

### Arguments

- `--model`: Hugging Face model ID (e.g., "mistralai/Mistral-7B-Instruct-v0.2")
- `--model-name`: Model name as defined in conf/ directory (e.g., "Mistral-7B-Instruct-v0.2")
- `--test-train-path`: Path to directory containing training, testing, and validation data
- `--lora-dir`: Directory for saving LoRA adapter files

### Optional Flags

- `--debug`: Enable debug mode with additional logging
- `--verbose`: Enable verbose mode with detailed outputs
- `--pre-training-stats`: Run validation before training
- `--post-training-stats`: Run validation after training and merging
- `--post-quantization-stats`: Run validation after quantization
- `--validation-sample-size`: Number of samples to use for validation (default: 100)

## Data Format

The trainer expects data in the following format and locations:
- Training data: `<test_train_path>/voice-commands-xml-train.jsonl`
- Testing data: `<test_train_path>/voice-commands-xml-test.jsonl`
- Validation data: `<test_train_path>/voice-commands-xml-validate.jsonl`

Each file should contain JSONL entries with:
```json
{
  "instruction": "Task instruction",
  "input": "User input",
  "output": "Expected output",
  "command": "Command category"
}
```

## Model Configuration

Model-specific configurations are defined in the `conf/` directory. To add support for a new model:

1. Create a new Python file in `conf/` (e.g., `new_model.py`)
2. Define configurations for:
   - Fine-tuning parameters
   - LoRA parameters
   - Tokenizer settings
   - Model-specific settings (sequence length, prompt template)
3. Add the model to the `MODEL_CONFIG_MAP` in `conf/__init__.py`

## Pipeline Stages

The full training pipeline consists of:

1. **Pre-training validation** (optional)
   - Tests model performance before training
   
2. **Fine-tuning with LoRA**
   - Applies parameter-efficient fine-tuning
   - Creates adapter checkpoints

3. **Merging LoRA adapter**
   - Combines adapter weights with base model
   - Produces a standalone model with fine-tuning applied

4. **Post-training validation** (optional)
   - Tests model performance after fine-tuning
   - Uses vLLM server for inference

5. **Quantization**
   - Reduces model size and inference requirements
   - Uses AutoRound for high-quality quantization

6. **Post-quantization validation** (optional)
   - Tests model performance after quantization
   - Uses vLLM server for inference

## Example

```bash
sudo python peft_trainer.py \
  --model "mistralai/Ministral-8B-Instruct-2410" \
  --model-name "Ministral-8B-Instruct-2410" \
  --test-train-path "/mnt/DATA01/include/www.deepily.ai/projects/genie-in-the-box/src/ephemera/prompts/data" \
  --lora-dir "/mnt/DATA01/include/www.deepily.ai/projects/models/Ministral-8B-Instruct-2410.lora" \
  --post-training-stats \
  --post-quantization-stats \
  --validation-sample-size 100
```

## Debugging

For development and debugging, you can use the `run_pipeline_adhoc` method by uncommenting it in the main script. This version allows selective enabling/disabling of specific pipeline steps.

## Environment Variables

Required environment variables:
- `NCCL_P2P_DISABLE=1`
- `NCCL_IB_DISABLE=1`
- `GENIE_IN_THE_BOX_ROOT=/path/to/genie-in-the-box`
- `GIB_CONFIG_MGR_CLI_ARGS`
- `DEEPILY_PROJECTS_DIR=/path/to/projects`

## Output Directory Structure

```
<lora_dir>/
├── training-YYYY-MM-DD-at-HH-MM/
│   └── checkpoint-N/
├── merged-on-YYYY-MM-DD-at-HH-MM/
└── merged-on-YYYY-MM-DD-at-HH-MM/autoround-4-bits-sym.gptq/YYYY-MM-DD-at-HH-MM/
```