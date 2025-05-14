# Agent Migration Plan: v000 to v010 Architecture

## Executive Summary

This document outlines a comprehensive plan for migrating remaining agents from the legacy v000 architecture to the modernized v010 architecture. The v010 architecture features improved LLM client handling through a factory pattern, better streaming support, and more consistent interface design. Many core components have already been successfully migrated; this plan focuses on the remaining agent implementations that need to be updated.

## Current State Analysis

### Key Architectural Differences

| Feature | v000 Architecture | v010 Architecture |
|---------|------------------|-------------------|
| LLM Interface | Uses `Llm_v0` directly | Uses `LlmClientFactory` to get appropriate client |
| Streaming Support | Limited | Full streaming with config control |
| Import Structure | Less organized, inconsistent paths | More organized, version-specific imports |
| Output Formatting | Basic formatter | Enhanced formatter with run_formatter method |
| Configuration | Less streamlined | More centralized config management |
| Type Annotations | Minimal | More comprehensive |

### Migration Status

**Already Migrated Components:**
- Core infrastructure:
  - agent_base.py
  - runnable_code.py 
  - raw_output_formatter.py
  - two_word_id_generator.py
  - llm_client.py, llm_client_factory.py (replacements for llm.py, llm_v0.py)
  - llm_completion.py
  - token_counter.py (new)
  - prompt_formatter.py (new)

- Agent implementations:
  - date_and_time_agent.py 
  - iterative_debugging_agent.py

**Remaining Components Requiring Migration:**
- Agent implementations:
  - calendaring_agent.py
  - todo_list_agent.py
  - math_agent.py
  - weather_agent.py
  - agent_refactoring.py
  - bug_injector.py
  - confirmation_dialog.py
  - function_mapping_json.py
  - function_mapping_search.py
  - math_refactoring_agent.py
  - receptionist_agent.py

## Migration Strategy

### Pattern Recognition from Successful Migrations

Examining the successfully migrated `date_and_time_agent.py` highlights the following key patterns:

1. **Import Updates**: Change from v000 to v010 paths
2. **Constructor Compatibility**: Maintain same interface for backward compatibility
3. **LLM Interaction**: Use factory pattern instead of direct LLM instantiation
4. **Output Formatting**: Use the enhanced run_formatter() method

### Revised Copy-and-Modify Approach

After review, we're adopting a more efficient copy-and-modify approach:

1. **Copy File**
   - Copy the original agent file from v000 to v010 directory
   - This preserves all unique agent functionality and specialized methods

2. **Update Imports**
   - Change import paths from v000 to v010 packages
   - Update any deprecated imports with their v010 equivalents

3. **Modify LLM Interaction**
   - Replace direct Llm_v0 usage with LlmClientFactory pattern
   - Update any formatter usage to use run_formatter() method

4. **Test Migration**
   - Verify the agent works with the v010 architecture
   - Test both streaming and non-streaming configurations

This approach minimizes the risk of errors and preserves agent-specific behavior while still modernizing the core architecture.

### Configuration Integration

1. **Update Configuration Entries**
   - Ensure all migrated agents have proper config entries for v010
   - Add streaming parameters where appropriate

## Implementation Plan

### Migration Template

Here's a generalized code template for migrating an agent, based on the date_and_time_agent.py pattern:

```python
# Imports section
from cosa.agents.v010.agent_base import AgentBase

class AgentName(AgentBase):
    
    def __init__(self, question="", question_gist="", last_question_asked="", push_counter=-1, 
                 routing_command="agent router go to agent_name", debug=False, verbose=False, 
                 auto_debug=False, inject_bugs=False):
        
        # Initialize base class
        super().__init__(
            df_path_key=None,  # Use appropriate df_path_key if needed
            question=question,
            question_gist=question_gist,
            last_question_asked=last_question_asked,
            routing_command=routing_command,
            push_counter=push_counter,
            debug=debug,
            verbose=verbose,
            auto_debug=auto_debug,
            inject_bugs=inject_bugs
        )
        
        # Agent-specific initialization
        self.prompt = self.prompt_template.format(question=self.question)
        # Define expected XML response tags (preserve from v000 implementation)
        self.xml_response_tag_names = ["thoughts", "code", "example", "returns", "explanation"]
        
        # Additional agent-specific initialization
        # ...
    
    def restore_from_serialized_state(self, file_path):
        # Implementation of abstract method
        raise NotImplementedError(f"{self.__class__.__name__}.restore_from_serialized_state() not implemented")
    
    # Agent-specific methods
    # ...

if __name__ == "__main__":
    # Test code
    question = "Sample question for testing"
    agent = AgentName(question=question, debug=True, verbose=True)
    agent.run_prompt()
    agent.run_code()
    agent.run_formatter()
    
    print(f"Formatted response: {agent.answer_conversational}")
```

### Migration Schedule / Todo List

> **NOTE:** This migration work is scheduled to begin on 2025-05-14. We've adjusted our strategy to use a copy-and-modify approach rather than a template-based approach to preserve agent-specific functionality.

| Agent | Priority | Status | Est. Effort | Notes |
|-------|----------|--------|-------------|-------|
| calendaring_agent.py | High | ⏳ Not Started | 1 hour | First task for 2025-05-14 |
| todo_list_agent.py | High | ⏳ Not Started | 1 hour | |
| math_agent.py | High | ⏳ Not Started | 1 hour | |
| weather_agent.py | High | ⏳ Not Started | 1 hour | |
| receptionist_agent.py | Medium | ⏳ Not Started | 2 hours | |
| bug_injector.py | Medium | ⏳ Not Started | 1 hour | |
| function_mapping_json.py | Medium | ⏳ Not Started | 2 hours | |
| function_mapping_search.py | Medium | ⏳ Not Started | 2 hours | |
| confirmation_dialog.py | Low | ⏳ Not Started | 1 hour | |
| math_refactoring_agent.py | Low | ⏳ Not Started | 2 hours | Depends on math_agent.py |
| agent_refactoring.py | Low | ⏳ Not Started | 2 hours | |

**Legend:**
- ✅ Completed
- 🔄 In Progress
- ⏳ Not Started
- ❌ Blocked

## Special Considerations

### LLM Integration Differences

The most significant change is in how agents interact with LLMs:

```python
# v000 approach
from cosa.agents.llm_v0 import Llm_v0
llm = Llm_v0()
response = llm.prompt(self.prompt)

# v010 approach
from cosa.agents.v010.llm_client_factory import LlmClientFactory
factory = LlmClientFactory()
llm = factory.get_client(self.model_name, debug=self.debug, verbose=self.verbose)
response = llm.run(self.prompt)
```

### Streaming Considerations

The v010 architecture supports streaming through configuration:

```ini
# Example configuration with streaming enabled
agent_name_params = { 
    "prompt_format": "instruction_completion", 
    "model_name": "Model-Name", 
    "temperature": 0.25, 
    "top_k": 10, 
    "top_p": 0.25, 
    "max_tokens": 4096, 
    "stop_sequence": [ "</s>", "</response>" ], 
    "stream": True 
}
```

### Configuration Updates

Each migrated agent will require configuration updates in gib-app.ini:

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

## Testing Strategy

1. **Unit Testing**
   - Test each migrated agent individually
   - Verify core methods work correctly (run_prompt, run_code, run_formatter)
   - Test with both streaming and non-streaming configurations

2. **Integration Testing**
   - Test agent interaction with configuration system
   - Verify error handling and fallback mechanisms

3. **Performance Comparison**
   - Compare response times between v000 and v010 implementations
   - Verify streaming behavior works as expected

## Migration Example: calendaring_agent.py

As a concrete example, here's how the calendaring_agent.py migration would look:

**v000 Implementation (key parts):**
```python
from cosa.agents.agent_base import AgentBase

class CalendaringAgent(AgentBase):
    def __init__(self, ...):
        super().__init__(...)
        ...
        
    # Other methods
```

**v010 Implementation:**
```python
from cosa.agents.v010.agent_base import AgentBase

class CalendaringAgent(AgentBase):
    def __init__(self, question="", question_gist="", last_question_asked="", push_counter=-1, 
                 routing_command="agent router go to calendar", debug=False, verbose=False, 
                 auto_debug=False, inject_bugs=False):
        
        super().__init__(
            df_path_key="path_to_events_df_wo_root",  # Note: Keep the original df_path_key
            question=question,
            question_gist=question_gist,
            last_question_asked=last_question_asked,
            routing_command=routing_command,
            push_counter=push_counter,
            debug=debug,
            verbose=verbose,
            auto_debug=auto_debug,
            inject_bugs=inject_bugs
        )
        
        self.prompt = self.prompt_template.format(question=self.question)
        # Keep original xml_response_tag_names
        self.xml_response_tag_names = ["thoughts", "code", "example", "returns", "explanation"]
        
    def restore_from_serialized_state(self, file_path):
        raise NotImplementedError("CalendaringAgent.restore_from_serialized_state() not implemented")
        
    # Other methods preserved from v000
```

## Conclusion

This migration will complete the modernization of the agent architecture that is already underway. By following the established patterns from the successfully migrated components, we can ensure a smooth transition for the remaining agents.

The key benefits of completing this migration include:
- Consistent LLM client handling across all agents
- Improved streaming support
- Better configuration management
- More maintainable and organized codebase

The migrations can be performed incrementally, working through the todo list with higher-priority agents tackled first, allowing for continuous testing and refinement of the approach.