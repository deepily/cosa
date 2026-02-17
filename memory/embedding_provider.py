"""
Embedding provider routing layer with performance metrics.

Routes embedding generation to the configured engine:
- "openai" -> existing EmbeddingManager (768 dims via MRL truncation)
- "local"  -> CodeEmbeddingEngine or ProseEmbeddingEngine (768 dims)

Callers specify content_type="prose" or content_type="code" to route
to the appropriate engine when provider is "local".
"""

from threading import Lock
from typing import List, Dict, Any

import cosa.utils.util as du
import cosa.utils.util_stopwatch as sw
from cosa.config.configuration_manager import ConfigurationManager


class EmbeddingProvider:
    """
    Routing layer that delegates embedding generation to the configured engine.

    Provides a unified interface for all embedding operations with
    content-type-aware routing and performance metrics collection.

    Config-driven toggling via 'embedding provider' key:
      - "openai" -> existing EmbeddingManager (1536 dims)
      - "local"  -> CodeEmbeddingEngine or ProseEmbeddingEngine (768 dims)
    """

    _instance = None
    _lock     = Lock()

    def __new__( cls, debug=False, verbose=False ):
        """
        Create or return singleton instance.

        Requires:
            - Nothing

        Ensures:
            - Returns the single instance of EmbeddingProvider
            - Initializes components only once
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__( cls )
                    cls._instance._initialized = False
        return cls._instance

    def __init__( self, debug=False, verbose=False ):
        """
        Initialize the embedding provider routing layer.

        Requires:
            - LUPIN_CONFIG_MGR_CLI_ARGS environment variable is set

        Ensures:
            - Reads 'embedding provider' from config
            - Lazily initializes the appropriate engine(s)
            - Sets up metrics collection

        Raises:
            - ConfigurationManager errors if env var not set
        """
        if self._initialized:
            return

        self.debug   = debug
        self.verbose = verbose

        self._config_mgr    = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        self._provider      = self._config_mgr.get( "embedding provider", default="openai" ).strip().lower()

        # Lazy engine references
        self._openai_engine = None
        self._code_engine   = None
        self._prose_engine  = None

        # Metrics storage: { "openai_prose": { "count": 0, "total_ms": 0, "min_ms": inf, "max_ms": 0 }, ... }
        self._metrics       = {}
        self._metrics_lock  = Lock()

        if self.debug:
            print( f"EmbeddingProvider initialized: provider={self._provider}" )

        self._initialized = True

    def _get_openai_engine( self ):
        """Lazy-load the OpenAI embedding manager."""
        if self._openai_engine is None:
            from cosa.memory.embedding_manager import EmbeddingManager
            self._openai_engine = EmbeddingManager( debug=self.debug, verbose=self.verbose )
        return self._openai_engine

    def _get_code_engine( self ):
        """Lazy-load the local code embedding engine."""
        if self._code_engine is None:
            from cosa.memory.local_embedding_engine import get_code_engine
            self._code_engine = get_code_engine( debug=self.debug, verbose=self.verbose )
        return self._code_engine

    def _get_prose_engine( self ):
        """Lazy-load the local prose embedding engine."""
        if self._prose_engine is None:
            from cosa.memory.local_embedding_engine import get_prose_engine
            self._prose_engine = get_prose_engine( debug=self.debug, verbose=self.verbose )
        return self._prose_engine

    def generate_embedding( self, text, content_type="prose", normalize_for_cache=True ):
        """
        Route to the appropriate engine based on config and content_type.

        Requires:
            - text is a non-empty string
            - content_type is "prose" or "code"
            - normalize_for_cache is boolean (passed through to OpenAI engine only)

        Ensures:
            - Returns list[float] embedding vector
            - Dimensions depend on provider (1536 for openai, 768 for local)
            - Records timing metrics for benchmarking

        Args:
            text: Input text to embed
            content_type: "prose" or "code" - determines which local engine to use
            normalize_for_cache: Passed through to OpenAI engine only

        Returns:
            list[float] - embedding vector

        Raises:
            - None (errors handled by underlying engines)
        """
        timer = sw.Stopwatch( silent=True )

        if self._provider == "openai":
            if content_type == "code":
                print( "WARNING: OpenAI provider does not support code-specific embeddings. "
                       "Using text-embedding-3-small for code content." )
            embedding = self._get_openai_engine().generate_embedding( text, normalize_for_cache=normalize_for_cache )
        elif content_type == "code":
            embedding = self._get_code_engine().encode_code( [ text ] )[ 0 ]
        else:
            # prose - use encode_query for single-text embedding (query context)
            embedding = self._get_prose_engine().encode_query( [ text ] )[ 0 ]

        delta_ms = timer.get_delta_ms()
        self._record_metric( content_type, self._provider, delta_ms, len( embedding ) if embedding else 0 )

        if self.debug and self.verbose:
            print( f"[EmbeddingProvider] {self._provider}/{content_type}: {len( embedding ) if embedding else 0} dims in {delta_ms:.1f} ms" )

        return embedding

    def generate_embeddings_batch( self, texts, content_type="prose" ):
        """
        Generate embeddings for a batch of texts.

        Requires:
            - texts is a list of non-empty strings
            - content_type is "prose" or "code"

        Ensures:
            - Returns list of embedding vectors
            - More efficient than calling generate_embedding() in a loop for local engines

        Args:
            texts: List of input texts to embed
            content_type: "prose" or "code"

        Returns:
            list[list[float]] - list of embedding vectors
        """
        timer = sw.Stopwatch( silent=True )

        if self._provider == "openai":
            if content_type == "code":
                print( "WARNING: OpenAI provider does not support code-specific embeddings. "
                       "Using text-embedding-3-small for code content." )
            # OpenAI engine doesn't support batch - loop
            embeddings = [ self._get_openai_engine().generate_embedding( t ) for t in texts ]
        elif content_type == "code":
            embeddings = self._get_code_engine().encode_code( texts )
        else:
            embeddings = self._get_prose_engine().encode_query( texts )

        delta_ms = timer.get_delta_ms()
        self._record_metric( content_type, self._provider, delta_ms, len( embeddings[ 0 ] ) if embeddings and embeddings[ 0 ] else 0 )

        return embeddings

    @property
    def provider( self ):
        """Return the current provider name."""
        return self._provider

    @property
    def dimensions( self ):
        """
        Return the standardized embedding dimension from config.

        Ensures:
            - Returns the configured embedding dimensions (default 768)
            - Same value for all providers (OpenAI uses MRL truncation)
        """
        return int( self._config_mgr.get( "embedding dimensions", default="768" ) )

    @property
    def code_dimensions( self ):
        """Return the embedding dimension for the code engine."""
        return int( self._config_mgr.get( "embedding dimensions", default="768" ) )

    def _record_metric( self, content_type, provider, delta_ms, dims ):
        """Record timing metric for a provider/content_type pair."""
        key = f"{provider}_{content_type}"
        with self._metrics_lock:
            if key not in self._metrics:
                self._metrics[ key ] = { "count": 0, "total_ms": 0.0, "min_ms": float( "inf" ), "max_ms": 0.0, "dims": dims }
            m = self._metrics[ key ]
            m[ "count" ]    += 1
            m[ "total_ms" ] += delta_ms
            m[ "min_ms" ]    = min( m[ "min_ms" ], delta_ms )
            m[ "max_ms" ]    = max( m[ "max_ms" ], delta_ms )
            m[ "dims" ]      = dims

    def get_metrics_summary( self ):
        """
        Return timing metrics as a dict for benchmarking.

        Ensures:
            - Returns dict keyed by "provider_contenttype"
            - Each value has count, avg_ms, min_ms, max_ms, dims

        Returns:
            Dict of metrics per provider/content_type pair
        """
        summary = {}
        with self._metrics_lock:
            for key, m in self._metrics.items():
                count = m[ "count" ]
                summary[ key ] = {
                    "count"  : count,
                    "avg_ms" : round( m[ "total_ms" ] / count, 1 ) if count > 0 else 0,
                    "min_ms" : round( m[ "min_ms" ], 1 ) if m[ "min_ms" ] != float( "inf" ) else 0,
                    "max_ms" : round( m[ "max_ms" ], 1 ),
                    "dims"   : m[ "dims" ],
                }
        return summary

    def reset_metrics( self ):
        """Reset all collected metrics."""
        with self._metrics_lock:
            self._metrics.clear()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def get_embedding_provider( debug=False, verbose=False ):
    """
    Get singleton instance of EmbeddingProvider.

    Requires:
        - LUPIN_CONFIG_MGR_CLI_ARGS environment variable is set

    Ensures:
        - Returns singleton EmbeddingProvider instance
    """
    return EmbeddingProvider( debug=debug, verbose=verbose )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def quick_smoke_test():
    """Run quick smoke test for EmbeddingProvider routing layer."""
    du.print_banner( "EmbeddingProvider Smoke Test", prepend_nl=True )

    try:
        # Test 1: Initialize provider
        print( "Test 1: EmbeddingProvider initialization..." )
        provider = get_embedding_provider( debug=True, verbose=True )
        print( f"  Provider: {provider.provider}" )
        print( f"  Prose dimensions: {provider.dimensions}" )
        print( f"  Code dimensions: {provider.code_dimensions}" )
        print( "  Initialization OK" )

        # Test 2: Singleton
        print( "\nTest 2: Singleton verification..." )
        provider_2 = get_embedding_provider()
        assert provider is provider_2, "Singleton broken!"
        print( "  Singleton OK" )

        # Test 3: Prose embedding
        print( "\nTest 3: Prose embedding generation..." )
        prose_emb = provider.generate_embedding( "What time is it?", content_type="prose" )
        print( f"  Prose embedding: {len( prose_emb )} dims" )
        assert len( prose_emb ) == provider.dimensions, f"Expected {provider.dimensions}, got {len( prose_emb )}"
        print( "  Prose embedding OK" )

        # Test 4: Code embedding
        print( "\nTest 4: Code embedding generation..." )
        code_emb = provider.generate_embedding( "def hello(): return 'world'", content_type="code" )
        print( f"  Code embedding: {len( code_emb )} dims" )
        assert len( code_emb ) == provider.code_dimensions, f"Expected {provider.code_dimensions}, got {len( code_emb )}"
        print( "  Code embedding OK" )

        # Test 5: Metrics
        print( "\nTest 5: Metrics collection..." )
        # Generate a few more embeddings
        provider.generate_embedding( "Hello world", content_type="prose" )
        provider.generate_embedding( "sorted( my_list )", content_type="code" )

        metrics = provider.get_metrics_summary()
        print( f"  Metrics keys: {list( metrics.keys() )}" )
        for key, m in metrics.items():
            print( f"    {key}: count={m[ 'count' ]}, avg={m[ 'avg_ms' ]:.1f}ms, min={m[ 'min_ms' ]:.1f}ms, max={m[ 'max_ms' ]:.1f}ms, dims={m[ 'dims' ]}" )
        print( "  Metrics OK" )

        # Test 6: Batch encoding
        print( "\nTest 6: Batch encoding..." )
        batch_embs = provider.generate_embeddings_batch(
            [ "first text", "second text", "third text" ],
            content_type="prose"
        )
        print( f"  Batch result: {len( batch_embs )} embeddings, each {len( batch_embs[ 0 ] )} dims" )
        assert len( batch_embs ) == 3, f"Expected 3, got {len( batch_embs )}"
        print( "  Batch OK" )

        print( "\nAll EmbeddingProvider smoke tests PASSED" )

    except Exception as e:
        print( f"  Error during smoke test: {e}" )
        du.print_stack_trace( e, explanation="Smoke test failed", caller="embedding_provider.quick_smoke_test()" )

    print( "\nEmbeddingProvider smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()
