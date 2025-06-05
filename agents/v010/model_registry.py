from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List
from enum import Enum

class LlmProvider( Enum ):
    """Enumeration of supported LLM providers."""
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    GROQ      = "groq"
    GOOGLE    = "google"
    DEEPILY   = "deepily"

@dataclass
class ModelConfig:
    """
    Configuration for a specific model.
    
    Requires:
        - name is unique model identifier
        - provider is valid LlmProvider enum value
        - client_class is fully qualified class name
        - max_tokens is positive integer
        
    Ensures:
        - model configuration is complete and valid
        - supported_parameters contains standard parameter set
    """
    name                      : str
    provider                  : LlmProvider
    client_class              : str  # Fully qualified class name
    max_tokens                : int
    supports_streaming        : bool = True
    supports_system_messages  : bool = True
    cost_per_1k_tokens_input  : Optional[float] = None
    cost_per_1k_tokens_output : Optional[float] = None
    supported_parameters      : Set[str] = field( default_factory=lambda: {
        'temperature', 'max_tokens', 'top_p', 'frequency_penalty', 
        'presence_penalty', 'stop'
    } )
    
    def __post_init__( self ):
        """
        Validate model configuration after initialization.
        
        Ensures:
            - max_tokens is positive
            - cost values are non-negative if provided
        """
        if self.max_tokens <= 0:
            raise ValueError( "max_tokens must be positive" )
        if self.cost_per_1k_tokens_input is not None and self.cost_per_1k_tokens_input < 0:
            raise ValueError( "cost_per_1k_tokens_input must be non-negative" )
        if self.cost_per_1k_tokens_output is not None and self.cost_per_1k_tokens_output < 0:
            raise ValueError( "cost_per_1k_tokens_output must be non-negative" )

class ModelRegistry:
    """
    Registry of available models and their configurations.
    
    Requires:
        - registry is initialized with default models
        
    Ensures:
        - provides access to model configurations
        - supports registration of new models
        - validates model configurations
    """
    
    def __init__( self ):
        """
        Initialize model registry.
        
        Ensures:
            - registry is initialized with empty model dictionary
            - default models are loaded
        """
        self._models: Dict[str, ModelConfig] = {}
        self._initialize_default_models()
    
    def register_model( self, config: ModelConfig ):
        """
        Register a new model configuration.
        
        Requires:
            - config is valid ModelConfig object
            - config.name is unique within registry
            
        Ensures:
            - model is added to registry
            - existing model with same name is replaced
        """
        self._models[config.name] = config
        if self._verbose_logging:
            print( f"Registered model: {config.name} ({config.provider.value})" )
    
    def get_model_config( self, model_name: str ) -> ModelConfig:
        """
        Get configuration for a specific model.
        
        Requires:
            - model_name is registered in the registry
            
        Ensures:
            - returns ModelConfig for the specified model
            
        Raises:
            - LlmConfigError if model is not found
        """
        from .llm_exceptions import LlmConfigError
        
        if model_name not in self._models:
            available_models = list( self._models.keys() )
            raise LlmConfigError( 
                f"Unknown model: {model_name}. Available models: {available_models}" 
            )
        return self._models[model_name]
    
    def get_models_by_provider( self, provider: LlmProvider ) -> List[ModelConfig]:
        """
        Get all models for a specific provider.
        
        Requires:
            - provider is valid LlmProvider enum value
            
        Ensures:
            - returns list of ModelConfig objects for the provider
            - list may be empty if no models found
        """
        return [ config for config in self._models.values() if config.provider == provider ]
    
    def list_all_models( self ) -> List[str]:
        """
        Get list of all registered model names.
        
        Ensures:
            - returns sorted list of model names
        """
        return sorted( self._models.keys() )
    
    def get_providers( self ) -> Set[LlmProvider]:
        """
        Get set of all providers with registered models.
        
        Ensures:
            - returns set of LlmProvider enum values
        """
        return { config.provider for config in self._models.values() }
    
    @property
    def _verbose_logging( self ) -> bool:
        """Enable verbose logging for registry operations."""
        return False  # Can be made configurable later
    
    def _initialize_default_models( self ):
        """
        Initialize registry with default model configurations.
        
        Ensures:
            - common models for each provider are registered
            - configuration includes cost and capability information
        """
        # OpenAI models
        self.register_model( ModelConfig(
            name                      = "gpt-4",
            provider                  = LlmProvider.OPENAI,
            client_class              = "cosa.agents.v010.openai_client.OpenAIClient",
            max_tokens                = 8192,
            cost_per_1k_tokens_input  = 0.03,
            cost_per_1k_tokens_output = 0.06
        ) )
        
        self.register_model( ModelConfig(
            name                      = "gpt-4-turbo",
            provider                  = LlmProvider.OPENAI,
            client_class              = "cosa.agents.v010.openai_client.OpenAIClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.01,
            cost_per_1k_tokens_output = 0.03
        ) )
        
        self.register_model( ModelConfig(
            name                      = "gpt-3.5-turbo",
            provider                  = LlmProvider.OPENAI,
            client_class              = "cosa.agents.v010.openai_client.OpenAIClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.0005,
            cost_per_1k_tokens_output = 0.0015
        ) )
        
        # Anthropic models
        self.register_model( ModelConfig(
            name                      = "claude-3-sonnet-20240229",
            provider                  = LlmProvider.ANTHROPIC,
            client_class              = "cosa.agents.v010.anthropic_client.AnthropicClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.003,
            cost_per_1k_tokens_output = 0.015
        ) )
        
        self.register_model( ModelConfig(
            name                      = "claude-3-haiku-20240307",
            provider                  = LlmProvider.ANTHROPIC,
            client_class              = "cosa.agents.v010.anthropic_client.AnthropicClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.00025,
            cost_per_1k_tokens_output = 0.00125
        ) )
        
        # Groq models
        self.register_model( ModelConfig(
            name                      = "mixtral-8x7b-32768",
            provider                  = LlmProvider.GROQ,
            client_class              = "cosa.agents.v010.groq_client.GroqClient",
            max_tokens                = 32768,
            cost_per_1k_tokens_input  = 0.00027,
            cost_per_1k_tokens_output = 0.00027
        ) )
        
        self.register_model( ModelConfig(
            name                      = "llama2-70b-4096",
            provider                  = LlmProvider.GROQ,
            client_class              = "cosa.agents.v010.groq_client.GroqClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.00070,
            cost_per_1k_tokens_output = 0.00080
        ) )
        
        # Google models
        self.register_model( ModelConfig(
            name                      = "gemini-1.5-pro",
            provider                  = LlmProvider.GOOGLE,
            client_class              = "cosa.agents.v010.google_client.GoogleClient",
            max_tokens                = 2048,
            cost_per_1k_tokens_input  = 0.0035,
            cost_per_1k_tokens_output = 0.0105
        ) )
        
        # Deepily models (local inference)
        self.register_model( ModelConfig(
            name                      = "deepily-llama-7b",
            provider                  = LlmProvider.DEEPILY,
            client_class              = "cosa.agents.v010.deepily_client.DeepilyClient",
            max_tokens                = 4096,
            cost_per_1k_tokens_input  = 0.0,  # Local inference
            cost_per_1k_tokens_output = 0.0
        ) )