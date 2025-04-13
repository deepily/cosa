"""
CoSA LLM Client Module (v1)

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
    from cosa.agents.v1.llm_client_factory import LlmClientFactory
    from cosa.agents.v1.llm_client import LlmClient
    
    # Use factory (recommended)
    factory = LlmClientFactory()
    client = factory.get_client(LlmClient.GROQ_LLAMA_3_1_8B)
    
    # Or create directly
    client = LlmClient(model_name="groq:llama-3.1-8b-instant")
    
    # Run a prompt
    response = client.run("What is the capital of France?")
"""

from .llm_client import LlmClient
from .llm_client_factory import LlmClientFactory
from .token_counter import TokenCounter
from .llm_completion import LlmCompletion

__all__ = [
    'LlmClient',
    'LlmClientFactory',
    'TokenCounter',
    'LlmCompletion',
]