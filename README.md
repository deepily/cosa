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
- **Hybrid TTS Streaming**: Fast, reliable text-to-speech with no word truncation
- And more...

### Hybrid TTS Implementation

The system includes a clean, high-performance TTS solution that combines the speed benefits of streaming with the reliability of complete file playback:

**Architecture**: `OpenAI TTS → FastAPI → WebSocket → Client`

**Benefits**:
- ✅ **50% faster** than complete file approach (streaming transfer)
- ✅ **Zero truncation** (complete audio before playback)
- ✅ **Ultra-simple code** (no format complexity)
- ✅ **Universal compatibility** (standard HTML5 audio)

**Implementation**: 
- Server: `stream_tts_hybrid()` - immediately forwards OpenAI chunks via WebSocket
- Client: Collects all chunks, then plays complete audio file
- Endpoint: `/api/get-audio` uses the hybrid approach for optimal performance

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

## COSA Framework Code Flow Diagram

Based on analysis of the codebase, here's how the COSA (Collection of Small Agents) framework works:

### 1. Entry Points (Flask/FastAPI)

```
Flask Server (app.py) - DEPRECATED          FastAPI Server (fastapi_app/main.py) - NEW
     |                                              |
     ├── /push endpoint                             ├── WebSocket endpoints
     ├── /api/upload-and-transcribe-*               ├── REST API endpoints
     └── Socket.IO connections                      └── Async handlers
```

### 2. Request Flow Architecture

```
User Request (voice/text)
     |
     v
MultiModalMunger (preprocessing)
     |
     v
TodoFifoQueue.push_job()
     ├── Check for similar snapshots
     ├── Parse salutations
     ├── Get question gist (via Gister)
     └── Route to agent via LLM
          |
          v
     Agent Router (LLM-based)
          ├── "agent router go to calendar" → CalendaringAgent
          ├── "agent router go to math" → MathAgent
          ├── "agent router go to todo list" → TodoListAgent
          ├── "agent router go to date and time" → DateAndTimeAgent
          ├── "agent router go to weather" → WeatherAgent
          └── "agent router go to receptionist" → ReceptionistAgent
```

### 3. Queue Management System

```
TodoFifoQueue (pending jobs)
     |
     v
RunningFifoQueue.enter_running_loop()
     ├── Pop from TodoQueue
     ├── Execute job (Agent or SolutionSnapshot)
     └── Route to appropriate queue:
          ├── DoneQueue (successful)
          └── DeadQueue (errors)
```

### 4. Agent Execution Flow

```
AgentBase (abstract)
     |
     ├── run_prompt() → LlmClient → LLM Service
     ├── run_code() → RunnableCode → Python exec()
     └── run_formatter() → RawOutputFormatter
          |
          v
     do_all() orchestrates the complete flow
```

### 5. Core Components

**ConfigurationManager**
- Singleton pattern
- Manages `gib-app.ini` settings
- Environment variable overrides

**LlmClient/LlmClientFactory**
- Unified interface for multiple LLM providers
- Supports OpenAI, Groq, Google, Anthropic
- Handles streaming/non-streaming modes

**SolutionSnapshot**
- Serializes successful agent runs
- Stores code, prompts, responses
- Enables solution reuse

**Memory Components**
- `InputAndOutputTable`: Logs all I/O
- `EmbeddingManager`: Manages embeddings (singleton)
- `GistNormalizer`: Text preprocessing (singleton)
- `SolutionSnapshotManager`: Manages saved solutions

### 6. Data Flow Example

```
1. User: "What's the weather today?"
2. Flask/FastAPI receives request
3. MultiModalMunger processes input
4. TodoFifoQueue:
   - Checks for similar snapshots
   - No match found
   - Routes to weather agent via LLM
5. WeatherAgent created and queued
6. RunningFifoQueue executes:
   - Calls agent.do_all()
   - Agent queries weather API
   - Formats response
7. Results sent to DoneQueue
8. Audio response generated via TTS
9. Response sent to user
```

### Key Design Patterns

- **Singleton**: ConfigurationManager, EmbeddingManager, GistNormalizer
- **Abstract Factory**: LlmClientFactory
- **Template Method**: AgentBase.do_all()
- **Queue-based Architecture**: Async job processing
- **Serialization**: SolutionSnapshot for persistence

The framework elegantly handles voice/text input, routes to specialized agents, executes code dynamically, and maintains a memory of successful solutions for reuse.

## Development Guidelines

Please refer to [CLAUDE.md](./CLAUDE.md) for detailed code style and development guidelines.

## Research and Development

For current research and planning documents, see the [RND directory](./rnd/), which includes:

### Architecture and Refactoring
- [LLM Client Architecture Refactoring Plan](./rnd/2025.06.04-llm-client-architecture-refactoring-plan.md): Comprehensive plan for improving the v010 LLM client architecture
- [LLM Client Refactoring Progress](./rnd/2025.06.04-llm-client-refactoring-progress.md): Progress tracker for the LLM client refactoring project
- [LLM Refactoring Analysis](./rnd/2025-04-14_llm_refactoring_analysis.md): Analysis of LLM component refactoring needs
- [Agent Migration v000 to v010 Plan](./rnd/2025-05-13_agent_migration_v000_to_v010_plan.md): Migration strategy for agent architecture

### Implementation Plans
- [Screen Reader Agent Implementation Plan](./rnd/2025-04-14_screen_reader_agent_implementation_plan.md): Plan for screen reader accessibility agent
- [Agent Factory Testing Plan](./rnd/2025-05-15_agent_factory_testing_plan.md): Testing strategy for agent factory components
- [CI Testing Implementation Plan](./rnd/2025-05-19_ci_testing_implementation_plan.md): Continuous integration testing setup

### Analysis and Strategy
- [LLM Prompt Format Analysis](./rnd/2025-04-16_llm_prompt_format_analysis.md): Analysis of prompt formatting approaches
- [Prompt Templating Strategies](./rnd/2025-04-16_prompt_templating_strategies.md): Strategies for prompt template management
- [Python Package Distribution Plan](./rnd/2025-05-16_python_package_distribution_plan.md): Plan for package distribution strategy
- [Versioning and CI/CD Strategy](./rnd/2025-05-28_versioning_and_cicd_strategy.md): Version management and deployment strategy

## Recent and Upcoming Work

### Current Version
- **Version 0.0.2**: We are currently working on version 0.0.2, which includes refactoring and cleanup efforts.

### Recently Completed
- **Standardized Smoke Testing (December 2025)**: Comprehensive refactoring of all modules to use consistent `quick_smoke_test()` patterns
  - All 21 core modules now include standardized smoke tests
  - Tests validate complete workflow execution, not just object creation
  - Consistent error handling and status reporting across all components
  - Professional formatting with clear ✓/✗ indicators

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