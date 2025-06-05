"""
CoSA LLM Client Module (v010)

This package provides a modernized implementation of LLM clients and utilities,
designed to work with various LLM providers and model types.

Components:
- LlmClient: Main client interface for LLM interactions
- LlmClientFactory: Factory for creating appropriate LLM clients
- TokenCounter: Utility for counting tokens across different models
- LlmCompletion: Client for completion-style APIs

Design Principles:
- Modularity: Each component has a clear, focused responsibility
- Compatibility: Support for multiple LLM providers (OpenAI, Groq, Anthropic, etc.)
- Observability: Built-in performance metrics and diagnostics
- Resilience: Graceful fallbacks and error handling

Usage:
    from cosa.agents.v010.llm_client_factory import LlmClientFactory
    from cosa.agents.v010.llm_client import LlmClient
    
    # Use factory (recommended)
    factory = LlmClientFactory()
    client = factory.get_client(LlmClient.GROQ_LLAMA_3_1_8B)
    
    # Or create directly
    client = LlmClient(model_name="groq:llama-3.1-8b-instant")
    
    # Run a prompt
    response = client.run("What is the capital of France?")
"""

# Existing components
from .llm_client import LlmClient
from .llm_client_factory import LlmClientFactory
from .token_counter import TokenCounter
from .llm_completion import LlmCompletion

# New base abstractions for refactored architecture
from .base_llm_client import BaseLlmClient
from .llm_data_types import (
    MessageRole,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    LlmStreamChunk
)
from .llm_exceptions import (
    LlmError,
    LlmConfigError,
    LlmAPIError,
    LlmTimeoutError,
    LlmAuthenticationError,
    LlmRateLimitError,
    LlmModelError,
    LlmStreamingError,
    LlmValidationError
)
from .model_registry import (
    LlmProvider,
    ModelConfig,
    ModelRegistry
)

__all__ = [
    # Existing components
    'LlmClient',
    'LlmClientFactory',
    'TokenCounter',
    'LlmCompletion',
    
    # New base abstractions
    'BaseLlmClient',
    
    # Data types
    'MessageRole',
    'LlmMessage', 
    'LlmRequest',
    'LlmResponse',
    'LlmStreamChunk',
    
    # Exceptions
    'LlmError',
    'LlmConfigError',
    'LlmAPIError',
    'LlmTimeoutError',
    'LlmAuthenticationError',
    'LlmRateLimitError',
    'LlmModelError',
    'LlmStreamingError',
    'LlmValidationError',
    
    # Registry
    'LlmProvider',
    'ModelConfig',
    'ModelRegistry'
]