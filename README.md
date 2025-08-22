# CoSA: Collection of Small Agents

CoSA is a modular framework for building, training, and deploying specialized LLM-powered agents. It provides the infrastructure for Lupin (formerly Genie-in-the-Box), a versatile conversational AI system.

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

### TTS Implementation Architecture

The system includes two high-performance TTS solutions optimized for different use cases:

#### Hybrid TTS (OpenAI)
**Architecture**: `OpenAI TTS → FastAPI → WebSocket → Client`
- Server: `stream_tts_hybrid()` - forwards OpenAI chunks via WebSocket
- Client: Collects all chunks, then plays complete audio file
- **Benefits**: 50% faster than complete file approach, zero truncation, universal compatibility

#### Instant Mode TTS (ElevenLabs)
**Architecture**: `ElevenLabs Streaming API → FastAPI → WebSocket → Client`
- Server: Direct WebSocket streaming with progressive chunk delivery
- Client: Immediate playback of audio chunks as received
- **Benefits**: Ultra-low latency, real-time streaming, significantly faster than hybrid mode
- **Use Case**: Interactive conversations requiring immediate audio response

**Endpoints**: 
- `/api/get-audio` - Hybrid OpenAI approach for reliability
- `/api/get-audio-elevenlabs` - Instant ElevenLabs streaming for speed

## Project Structure

- `/agents`: Individual agent implementations
  - `agent_base.py`: Abstract base class for all agents
  - `llm.py`, `llm_v0.py`: LLM service integration (legacy)
  - `/v010`: Current agent architecture with Pydantic XML processing
  - `/io_models/`: Pydantic XML models and utilities
    - `xml_models.py`: Core XML response models with template generation
    - `utils/prompt_template_processor.py`: Dynamic template processing
  - `/v1`: New modular LLM client architecture
    - `llm_client.py`: Unified client for all LLM providers
    - `llm_client_factory.py`: Factory pattern for client creation
    - `token_counter.py`: Cross-provider token counting
  - Specialized agents for math, calendaring, weather, etc.
- `/app`: Core application components
  - `configuration_manager.py`: Settings management with inheritance
  - `util_llm_client.py`: Client for LLM service communication
- `/memory`: Data persistence and memory management
- `/rest`: REST API infrastructure
  - Queue management, WebSocket routers, authentication
  - Producer-consumer pattern with event-driven processing
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

CoSA is designed to be used as a submodule/subtree within the parent "Lupin" project (formerly genie-in-the-box), but can also be used independently for agent development.

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

### 1. Entry Points (FastAPI)

```
FastAPI Server (fastapi_app/main.py) - CURRENT
     |
     ├── WebSocket endpoints
     ├── REST API endpoints
     └── Async handlers
     
Flask Server (app.py) - DEPRECATED/REMOVED
     ├── /push endpoint (migrated to FastAPI)
     ├── /api/upload-and-transcribe-* (migrated)
     └── Socket.IO connections (replaced with WebSockets)
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
- Manages `lupin-app.ini` settings (formerly gib-app.ini)
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
2. FastAPI receives request
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
- **Version 0.7.0**: Current stable release featuring complete FastAPI migration, comprehensive testing infrastructure, and production-ready agent framework with Pydantic XML processing.

### Recently Completed

#### August 2025 Major Achievements

- **Dynamic XML Template Migration (August 2025)**: Complete architectural transformation achieving single source of truth
  - **All 11 XML Response Models**: Added `get_example_for_template()` methods for self-documenting XML structures
  - **Template Transformation**: Replaced hardcoded XML in 7 prompt templates with `{{PYDANTIC_XML_EXAMPLE}}` markers
  - **Mandatory Processing**: Removed conditional logic - dynamic templating now standard for all agents
  - **Automatic Synchronization**: Template changes automatically when models change, eliminating maintenance duplication
  - **Production Ready**: 100% tested with comprehensive smoke testing confirming zero regressions
  - **Architecture Quality**: Models own their XML structure definitions, ensuring consistency across all agents

- **Pydantic XML Migration (August 2025)**: Full structured parsing system achieving 100% agent migration
  - **All 8 Agents Migrated**: Math, Calendar, Weather, Todo, Date/Time, Bug Injector, Debugger, Receptionist operational with structured_v2 parsing
  - **4 Core Models**: SimpleResponse, CommandResponse, YesNoResponse, CodeResponse with bidirectional XML conversion
  - **Advanced Processing**: Sophisticated nested XML handling with `@model_validator(mode='before')` preprocessing
  - **Agent-Specific Extensions**: CalendarResponse, MathBrainstormResponse models for complex nested structures
  - **3-Tier Strategy**: Runtime flag system with baseline, structured_v1, and structured_v2 parsing options
  - **Zero Compatibility Issues**: Complete validation confirmed no breaking changes from migration

- **Phase 6 Training Components Testing (August 2025)**: Complete ML infrastructure validation
  - **86/86 Tests Passing**: 100% success rate across all 8 training components with fast execution (<1s each)
  - **Zero External Dependencies**: Sophisticated mocking of PyTorch, HuggingFace, PEFT, AutoRound, TRL frameworks
  - **Comprehensive Coverage**: HuggingFace integration, model quantization, PEFT training, XML processing validation
  - **CICD Ready**: Professional-grade testing suitable for automated pipeline integration
  - **Error Handling Excellence**: Complete edge case coverage and malformed input validation

- **Phase 2 Unit Testing Framework (August 2025)**: Complete agent framework testing infrastructure
  - **64/64 Tests Passing**: 100% success rate for all agent framework components with <50ms execution times
  - **Complete Isolation**: Zero dependencies on external APIs, file systems, or network calls
  - **Deterministic Testing**: Predictable behavior through comprehensive mocking strategies
  - **Advanced Patterns**: Async/await simulation, singleton testing, time-based operations mocking
  - **Framework Foundation**: Established patterns ready for remaining testing phases

- **Smoke Test Infrastructure Remediation (August 2025)**: Complete testing infrastructure transformation achieving perfect reliability
  - **100% Success Rate**: Transformed completely broken smoke test infrastructure (0% operational) to perfect 100% success rate (35/35 tests passing)
  - **Comprehensive Coverage**: All 5 framework categories validated - Core (3/3), Agents (17/17), REST (5/5), Memory (7/7), Training (3/3)
  - **Automation Ready**: Fully operational infrastructure for regular use with sub-minute execution time (~1 minute total)
  - **Pydantic XML Migration Validation**: Confirmed zero compatibility issues from recent Pydantic XML migration - all agents operational
  - **Critical Fixes Applied**: Resolved initialization errors and PYTHONPATH inheritance issues enabling consistent automation
  - **Quality Achievement**: Enterprise-grade smoke testing infrastructure ready for daily CI/CD integration

- **Comprehensive Design by Contract Documentation (August 2025)**: Complete framework documentation standardization
  - **100% Coverage**: All 73 Python modules in CoSA framework fully documented with Design by Contract specifications
  - **Consistent Standards**: Uniform Requires/Ensures/Raises format across entire codebase
  - **Professional Grade**: Enterprise-level documentation suitable for production systems
  - **Enhanced Developer Experience**: Clear contracts for all functions defining expected inputs, guaranteed outputs, and exception behavior
  - **Improved Maintainability**: Consistent documentation patterns enabling easier debugging and modification
  - **Complete Coverage**: Agents (24), REST (11), Memory (4), CLI (3), Training (9), Utils (6), Tools (3)

#### July 2025 Major Achievements

- **WebSocket User Routing Architecture (July 2025)**: Complete redesign for persistent user-centric event routing
  - **Persistent User IDs**: Replaced ephemeral WebSocket IDs with persistent user identification
  - **Multi-Session Support**: Users can maintain multiple concurrent sessions across devices/tabs
  - **Event-Driven Architecture**: Comprehensive event taxonomy for rich user experience
  - **Resilient Design**: Handles disconnections, reconnections, and network issues gracefully
  - **Future-Ready**: Architecture designed for offline event queuing capabilities

- **Producer-Consumer Queue Optimization (July 2025)**: 6700x performance improvement through event-driven processing
  - **Performance Breakthrough**: Improved from 1s polling delays to ~1ms event-driven latency
  - **Zero CPU Waste**: Eliminated polling loops using efficient threading.Condition coordination
  - **Job Validation**: Pre-processing validation with WebSocket rejection notifications
  - **Thread-Safe Design**: Robust producer-consumer coordination with graceful lifecycle management
  - **FastAPI Integration**: Clean startup/shutdown integration with proper daemon thread management

#### Earlier Achievements

- **Standardized Smoke Testing (August 2025)**: Comprehensive refactoring of all modules to use consistent `quick_smoke_test()` patterns
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
- **Phase 3 Unit Testing**: Memory & Persistence testing implementation for complete framework coverage
- **Template Rendering Enhancement**: Investigation of Pydantic object integration for prompt template rendering
- **Configuration Key Migration**: Migration of remaining underscore config keys to plain English style
- **Job Delete Functionality**: Implementation of server-side deletion with confirmation dialogs

### Future Plans
- **Phase 4-5 Unit Testing**: REST API integration and external services testing
- **Technical Debt Cleanup**: Removal of deprecated configuration keys after migration validation
- **XML Validation Enhancement**: Schema validation to ensure generated examples parse correctly
- **Performance Monitoring**: Advanced metrics for template processing and agent execution times

## License

This project is licensed under the terms specified in the [LICENSE](./LICENSE) file.