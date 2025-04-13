from typing import Optional, Dict

from pydantic_ai.models.openai import OpenAIModel  # New import


class TokenCounter:
    """
    Utility for counting tokens in prompts and responses.
    """
    
    def __init__( self, model_tokenizer_map: Optional[ Dict[ str, str ] ] = None ):
        """
        Initialize the token counter with a mapping from model names to tokenizer identifiers.

        Args:
            model_tokenizer_map: Optional dictionary mapping model names to tokenizer identifiers.
                                If None, tiktoken's default mapping will be used.
        """
        self.model_tokenizer_map = model_tokenizer_map or { }
        # Import here to avoid requiring tiktoken for all users
        try:
            import tiktoken
            self.tiktoken = tiktoken
        except ImportError:
            print( "Warning: tiktoken not installed. Token counting will be approximate." )
            self.tiktoken = None
    
    def count_tokens( self, model_name: str, text: str ) -> int:
        """
        Count the number of tokens in the given text for the specified model.

        Args:
            model_name: Name of the model to count tokens for
            text: Text to count tokens in

        Returns:
            Number of tokens in the text
        """
        if not self.tiktoken:
            # Fallback if tiktoken not available: estimate 4 chars per token
            return len( text ) // 4
        
        try:
            # Map the model name to a tokenizer if needed
            tokenizer_name = self.model_tokenizer_map.get( model_name, model_name )
            
            try:
                # Try to get the encoding for the model directly
                encoding = self.tiktoken.encoding_for_model( tokenizer_name )
            except KeyError:
                # Fallback to cl100k_base for newer models not in tiktoken
                encoding = self.tiktoken.get_encoding( "cl100k_base" )
            
            # Count the tokens
            return len( encoding.encode( text ) )
        
        except Exception as e:
            print( f"Error counting tokens: {e}" )
            # Fallback to character-based estimation
            return len( text ) // 4