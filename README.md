# CoSA: Collection of Small Agents

CoSA is a modular framework for building, training, and deploying specialized LLM-powered agents. It provides the infrastructure for Genie-in-the-Box, a versatile conversational AI system.

<a href="docs/images/5-microphone-genie-robots.png" target="_blank">
  <img src="docs/images/5-microphone-genie-robots.png" alt="Genie robots with microphones" width="1024px">
</a>

## Overview

CoSA implements a collection of targeted agents, each specialized for specific tasks:
- Text generation and completion
- Mathematics and calculations
- Calendar management and scheduling
- Weather reporting
- Todo list management
- Code execution and debugging
- And more...

## Project Structure

- `/agents`: Individual agent implementations
  - `agent_base.py`: Abstract base class for all agents
  - `llm.py`, `llm_v0.py`: LLM service integration (legacy)
  - `/v1`: New modular LLM client architecture
    - `llm_client.py`: Unified client for all LLM providers
    - `llm_client_factory.py`: Factory pattern for client creation
    - `token_counter.py`: Cross-provider token counting
  - Specialized agents for math, calendaring, weather, etc.
- `/app`: Core application components
  - `configuration_manager.py`: Settings management with inheritance
  - `util_llm_client.py`: Client for LLM service communication
- `/memory`: Data persistence and memory management
- `/tools`: External integrations and tools
  - `search_gib.py`: Internal search capabilities
  - `search_kagi.py`: Integration with Kagi search API
- `/training`: Model training infrastructure
  - `peft_trainer.py`: PEFT (Parameter-Efficient Fine-Tuning) implementation
  - `quantizer.py`: Model quantization for deployment
  - `xml_coordinator.py`: Structured XML training data generation/validation
- `/utils`: Shared utility functions

## Getting Started

### Prerequisites

- Python 3.9+
- PyTorch
- Transformers library
- Hugging Face account (for model access)

For a complete list of dependencies, see the [requirements.txt](./requirements.txt) file.

### Installation

```bash
# Clone the repository
git clone git@github.com:deepily/cosa.git
cd cosa

# Install dependencies
pip install -r requirements.txt
```

### Usage

CoSA is designed to be used as a submodule/subtree within the parent "genie-in-the-box" project, but can also be used independently for agent development.

**TBD**: Usage examples and API documentation will be provided in future updates.

## LLM Model Training

CoSA includes tools for fine-tuning and deploying LLM models using Parameter-Efficient Fine-Tuning (PEFT):

```bash
# Example: Fine-tune a model using PEFT
python -m cosa.training.peft_trainer \
  --model "mistralai/Mistral-7B-Instruct-v0.2" \
  --model-name "Mistral-7B-Instruct-v0.2" \
  --test-train-path "/path/to/training/data" \
  --lora-dir "/path/to/output/lora" \
  --post-training-stats
```

For detailed instructions on using the PEFT trainer, including all available options, data format requirements, and advanced features like GPU management, please refer to the [PEFT Trainer README](./training/README.md).

## Development Guidelines

Please refer to [CLAUDE.md](./CLAUDE.md) for detailed code style and development guidelines.

## Recent and Upcoming Work

### Current Version
- **Version 0.0.2**: We are currently working on version 0.0.2, which includes refactoring and cleanup efforts.

### Recently Completed
- **Modular LLM Client Architecture (v1)**: MVP implementation of a vendor-agnostic LLM client system
  - Support for multiple providers (OpenAI, Groq, Anthropic/Claude, Google/Gemini)
  - Integration with Deepily's edge servers for local model inference
  - Factory pattern for client creation with configuration-driven setup
  - Comprehensive token counting and performance metrics
  - Design by Contract documentation

### In Progress
- **Enhanced Message Handling**: Improved support for system vs. user messages
- **Better Performance Metrics**: Cost estimation, detailed logging, and monitoring
- **Advanced Token Counting**: More accurate token counting for all providers
- **Streaming Improvements**: Robust handling of streaming responses
- **Generation Parameter Support**: Model-specific parameter validation and handling

### Future Plans
- TBD

## License

This project is licensed under the terms specified in the [LICENSE](./LICENSE) file.