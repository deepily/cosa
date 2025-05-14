# Agent Migration v000 to v010

This directory contains the migrated agent implementations from the legacy v000 architecture to the modernized v010 architecture.

## Key Architectural Changes

- LLM Interface: Uses `LlmClientFactory` instead of direct `Llm_v0` instantiation
- Streaming Support: Full streaming with configuration control 
- Import Structure: More organized, version-specific imports
- Output Formatting: Enhanced formatter with `run_formatter()` method (previously `format_output()`)
- Configuration: More centralized configuration management
- Type Annotations: More comprehensive

## Migrated Components

- Core infrastructure (previously migrated):
  - agent_base.py
  - runnable_code.py 
  - raw_output_formatter.py
  - two_word_id_generator.py
  - llm_client.py, llm_client_factory.py (replacements for llm.py, llm_v0.py)
  - llm_completion.py
  - token_counter.py (new)
  - prompt_formatter.py (new)

- Agent implementations (newly migrated):
  - calendaring_agent.py
  - todo_list_agent.py
  - math_agent.py
  - weather_agent.py
  - receptionist_agent.py
  - bug_injector.py

## Required Dependencies

For all agents to function properly, the following external dependencies must be installed:

1. `kagiapi` - Required for weather_agent.py (for GibSearch/KagiSearch functionality)
2. `lancedb` - Required for receptionist_agent.py (for memory/question_embeddings_table.py)

Installation:
```bash
pip install kagiapi lancedb
```

## Special Notes

- The WeatherAgent has been updated to use a new `search_gib_v010.py` file that imports `RawOutputFormatter` from the v010 package.
- IMPORTANT: `tools/search_gib_v010.py` was created as a temporary solution to satisfy dependencies and needs to be kept in mind when making v010 the default agent implementation. This will need to be addressed when migrating the entire codebase to v010.
- The ReceptionistAgent depends on the InputAndOutputTable class, which in turn relies on QuestionEmbeddingsTable and requires the lancedb package.

## Configuration Updates

Each migrated agent requires configuration updates in gib-app.ini:

1. Add LLM specification:
```
llm spec key for agent router go to [agent_name] = kaitchup/phi_4_14b
```

2. Add formatter specification:
```
formatter llm spec for agent router go to [agent_name] = kaitchup/phi_4_14b
```

3. Add template paths (if not already present):
```
prompt template for agent router go to [agent_name] = /src/conf/prompts/agents/[agent_name].txt
formatter template for agent router go to [agent_name] = /src/conf/prompts/formatters/[agent_name].txt
```

4. Add serialization topic:
```
serialization topic for agent router go to [agent_name] = [agent_name]
```