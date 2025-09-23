"""
CoSA Agents Package

This package contains modernized agent implementations providing:
- Better modularity and separation of concerns
- Improved LLM client abstractions
- More consistent error handling
- Support for multiple LLM providers

Previously organized under v010/, now consolidated in the main agents directory.
"""

# Agent implementations
from .agent_base import AgentBase
from .calendaring_agent import CalendaringAgent
from .date_and_time_agent import DateAndTimeAgent
from .math_agent import MathAgent
from .receptionist_agent import ReceptionistAgent
from .todo_list_agent import TodoListAgent
from .weather_agent import WeatherAgent
from .bug_injector import BugInjector
from .iterative_debugging_agent import IterativeDebuggingAgent

# Dialog utilities
from .confirmation_dialog import ConfirmationDialogue

# LLM client infrastructure
from .llm_client import LlmClient
from .llm_client_factory import LlmClientFactory
from .token_counter import TokenCounter
from .llm_completion import LlmCompletion
from .chat_client import ChatClient
from .completion_client import CompletionClient

# Base abstractions for refactored architecture
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

# Utilities
from .prompt_formatter import PromptFormatter
from .raw_output_formatter import RawOutputFormatter
from .runnable_code import RunnableCode
from .two_word_id_generator import TwoWordIdGenerator

__all__ = [
    # Agent implementations
    'AgentBase',
    'CalendaringAgent',
    'DateAndTimeAgent',
    'MathAgent',
    'ReceptionistAgent',
    'TodoListAgent',
    'WeatherAgent',
    'BugInjector',
    'IterativeDebuggingAgent',

    # Dialog utilities
    'ConfirmationDialogue',

    # LLM client infrastructure
    'LlmClient',
    'LlmClientFactory',
    'TokenCounter',
    'LlmCompletion',
    'ChatClient',
    'CompletionClient',

    # Base abstractions
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
    'ModelRegistry',

    # Utilities
    'PromptFormatter',
    'RawOutputFormatter',
    'RunnableCode',
    'TwoWordIdGenerator'
]