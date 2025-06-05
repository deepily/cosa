from abc import ABC, abstractmethod
from typing import Optional, Any
import asyncio

class BaseLlmClient( ABC ):
    """
    Abstract base class for all LLM clients.
    
    Requires:
        - Subclasses must implement complete() method
        - Client must be configured with valid model and credentials
        
    Ensures:
        - Consistent interface across all LLM providers
        - Both async and sync support
        - Standardized request/response objects
        
    Raises:
        - LlmError for client-specific errors
        - LlmAPIError for API communication errors
    """
    
    def __init__( self, model: str, debug: bool = False, verbose: bool = False ):
        """
        Initialize base LLM client.
        
        Requires:
            - model is a valid model identifier string
            - debug and verbose are boolean values
            
        Ensures:
            - client is initialized with provided parameters
            - _initialized flag is set to False
        """
        self.model        = model
        self.debug        = debug
        self.verbose      = verbose
        self._initialized = False
    
    @abstractmethod
    async def complete( self, request: 'LlmRequest' ) -> 'LlmResponse':
        """
        Generate completion for the given request.
        
        Requires:
            - request is a valid LlmRequest object
            - client is properly configured
            
        Ensures:
            - returns LlmResponse with completion text
            - response includes token counts and metadata
            - handles streaming if requested
            
        Raises:
            - LlmError for client-specific errors
            - LlmAPIError for API communication errors
            - LlmTimeoutError for timeout errors
        """
        pass
    
    def complete_sync( self, request: 'LlmRequest' ) -> 'LlmResponse':
        """
        Synchronous wrapper for complete() method.
        
        Requires:
            - request is a valid LlmRequest object
            
        Ensures:
            - returns same result as complete()
            - handles async-to-sync conversion properly
            
        Raises:
            - Same exceptions as complete()
            - RuntimeError if event loop cannot be created
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop( loop )
        
        return loop.run_until_complete( self.complete( request ) )
    
    @abstractmethod
    async def validate_config( self ) -> bool:
        """
        Validate client configuration.
        
        Requires:
            - client has been initialized
            
        Ensures:
            - returns True if configuration is valid
            - raises LlmConfigError if invalid
            
        Raises:
            - LlmConfigError if configuration is invalid
        """
        pass
    
    @abstractmethod
    def get_supported_parameters( self ) -> set[str]:
        """
        Get list of parameters supported by this client.
        
        Requires:
            - client has been initialized
            
        Ensures:
            - returns set of parameter names
            - includes standard parameters (temperature, max_tokens, etc.)
        """
        pass
    
    def __str__( self ) -> str:
        """String representation of the client."""
        return f"{self.__class__.__name__}(model={self.model})"
    
    def __repr__( self ) -> str:
        """Detailed string representation of the client."""
        return f"{self.__class__.__name__}(model='{self.model}', debug={self.debug}, verbose={self.verbose})"