"""
Embedding Cache Table for LanceDB storage.

Manages normalized text embedding cache to improve performance and reduce
OpenAI API calls by storing frequently requested embeddings.
"""

import lancedb
from typing import Optional
import cosa.utils.util as du
from cosa.app.configuration_manager import ConfigurationManager
from cosa.utils.util_stopwatch import Stopwatch


class EmbeddingCacheTable:
    """
    Manages normalized text embedding cache in LanceDB.
    
    Caches embeddings for normalized text to avoid regenerating them.
    Supports embedding lookup and storage with singleton pattern.
    """
    def __init__( self, debug: bool=False, verbose: bool=False ) -> None:
        """
        Initialize the embedding cache table.
        
        Requires:
            - GIB_CONFIG_MGR_CLI_ARGS environment variable is set or defaults available
            - Database path is valid in configuration
            
        Ensures:
            - Opens connection to LanceDB
            - Opens embedding_cache_tbl
            - Prints table row count
            
        Raises:
            - FileNotFoundError if database path invalid
            - lancedb errors propagated
        """
        
        self.debug       = debug
        self.verbose     = verbose
        self._config_mgr = ConfigurationManager( env_var_name="GIB_CONFIG_MGR_CLI_ARGS" )
        
        uri = du.get_project_root() + self._config_mgr.get( "database_path_wo_root" )
        
        db = lancedb.connect( uri )
        
        # Check if table exists, create if it doesn't
        if "embedding_cache_tbl" not in db.table_names():
            if self.debug: 
                print( "Table 'embedding_cache_tbl' doesn't exist, creating it..." )
            self._create_table_if_needed( db )
        else:
            self._embedding_cache_tbl = db.open_table( "embedding_cache_tbl" )
        
        print( f"Opened embedding_cache_tbl w/ [{self._embedding_cache_tbl.count_rows()}] rows" )
        
    def _create_table_if_needed( self, db ) -> None:
        """
        Create the embedding cache table with proper schema.
        
        Requires:
            - db is a valid LanceDB connection
            
        Ensures:
            - Creates table with normalized_text and embedding fields
            - Sets up FTS index for search
            - Sets self._embedding_cache_tbl to the new table
            
        Raises:
            - lancedb errors propagated
        """
        import pyarrow as pa
        
        if self.debug: 
            du.print_banner( "Creating embedding_cache_tbl schema..." )
        
        schema = pa.schema( [
            pa.field( "normalized_text", pa.string() ),
            pa.field( "embedding", pa.list_( pa.float32(), 1536 ) )
        ] )
        
        self._embedding_cache_tbl = db.create_table( "embedding_cache_tbl", schema=schema, mode="overwrite" )
        self._embedding_cache_tbl.create_fts_index( "normalized_text", replace=True )
        
        if self.debug:
            print( f"✓ Created embedding_cache_tbl with schema: {schema}" )
            print( f"✓ Created FTS index on normalized_text field" )
        
    def has_cached_embedding( self, normalized_text: str ) -> bool:
        """
        Check if a normalized text has cached embedding.
        
        Requires:
            - normalized_text is a non-empty string
            - Table is initialized
            
        Ensures:
            - Returns True if normalized text exists in table
            - Returns False if normalized text not found
            - Performs exact string match
            
        Raises:
            - None (handles errors gracefully)
        """
        if self.debug: timer = Stopwatch( msg=f"has_cached_embedding( '{normalized_text}' )" )
        
        try:
            # Escape single quotes by doubling them to prevent SQL parsing errors
            escaped_text = normalized_text.replace( "'", "''" )
            results = self._embedding_cache_tbl.search().where( f"normalized_text = '{escaped_text}'" ).limit( 1 ).select( [ "normalized_text" ] ).to_list()
            if self.debug: timer.print( "Done!", use_millis=True )
            return len( results ) > 0
        except Exception as e:
            if self.debug: timer.print( f"Error: {e}", use_millis=True )
            du.print_stack_trace( e, explanation="has_cached_embedding() failed", caller="EmbeddingCacheTable.has_cached_embedding()" )
            return False
    
    def get_cached_embedding( self, normalized_text: str ) -> Optional[ list[ float ] ]:
        """
        Get the cached embedding for the given normalized text.
        
        Requires:
            - normalized_text is a non-empty string
            - Table is initialized
            
        Ensures:
            - Returns embedding from cache if found
            - Returns None if not in cache
            - Returns list of 1536 floats if found
            
        Raises:
            - None (handles exceptions internally)
        """
        if self.debug: timer = Stopwatch( msg=f"get_cached_embedding( '{normalized_text}' )", silent=True )
        
        try:
            # Escape single quotes by doubling them to prevent SQL parsing errors
            escaped_text = normalized_text.replace( "'", "''" )
            rows_returned = self._embedding_cache_tbl.search().where( f"normalized_text = '{escaped_text}'" ).limit( 1 ).select( [ "embedding" ] ).to_list()
            if self.debug: timer.print( f"Done! w/ {len( rows_returned )} rows returned", use_millis=True )
            
            if rows_returned:
                return rows_returned[ 0 ][ "embedding" ]
            else:
                return None
                
        except Exception as e:
            if self.debug: timer.print( f"Error: {e}", use_millis=True )
            du.print_stack_trace( e, explanation="get_cached_embedding() failed", caller="EmbeddingCacheTable.get_cached_embedding()" )
            return None
        
    def cache_embedding( self, normalized_text: str, embedding: list[ float ] ) -> None:
        """
        Add a normalized text and its embedding to the cache.
        
        Requires:
            - normalized_text is a non-empty string
            - embedding is a list of 1536 floats
            - Table is initialized
            
        Ensures:
            - Adds row to table with normalized text and embedding
            - Handles LanceDB errors gracefully
            
        Raises:
            - None (catches and logs errors)
        """
        new_row = [ { "normalized_text": normalized_text, "embedding": embedding } ]
        
        try:
            self._embedding_cache_tbl.add( new_row )
            if self.debug: print( f"Cached embedding for normalized text: '{du.truncate_string( normalized_text )}'" )
        except Exception as e:
            du.print_stack_trace( e, explanation="cache_embedding() failed", caller="EmbeddingCacheTable.cache_embedding()" )
    
    def init_tbl( self ) -> None:
        """
        Initialize the embedding cache table schema.
        
        Requires:
            - Database connection is established
            
        Ensures:
            - Creates table with proper schema
            - Sets up normalized_text and embedding fields
            - Creates FTS index for search
            - Overwrites existing table if present
            
        Raises:
            - lancedb errors propagated
        """
        import pyarrow as pa
        
        uri = du.get_project_root() + self._config_mgr.get( "database_path_wo_root" )
        db = lancedb.connect( uri )
        
        du.print_banner( "Initializing embedding_cache_tbl schema..." )
        
        schema = pa.schema( [
            pa.field( "normalized_text", pa.string() ),
            pa.field( "embedding", pa.list_( pa.float32(), 1536 ) )
        ] )
        
        self._embedding_cache_tbl = db.create_table( "embedding_cache_tbl", schema=schema, mode="overwrite" )
        self._embedding_cache_tbl.create_fts_index( "normalized_text", replace=True )
        
        print( f"✓ Created embedding_cache_tbl with schema: {schema}" )
        print( f"✓ Created FTS index on normalized_text field" )
        print( f"✓ Table initialized with {self._embedding_cache_tbl.count_rows()} rows" )


def quick_smoke_test():
    """Quick smoke test to validate EmbeddingCacheTable functionality."""
    du.print_banner( "EmbeddingCacheTable Smoke Test", prepend_nl=True )
    
    try:
        # Test 1: Initialize table
        print( "Test 1: Initializing EmbeddingCacheTable..." )
        cache_table = EmbeddingCacheTable( debug=False )
        print( "✓ EmbeddingCacheTable initialized successfully" )
        
        # Test 2: Check cache miss
        test_text = "what time is it"
        print( f"\nTest 2: Checking cache for '{test_text}'..." )
        has_cached = cache_table.has_cached_embedding( test_text )
        print( f"✓ Cache check complete: {'HIT' if has_cached else 'MISS'}" )
        
        # Test 3: Cache an embedding (simulate with dummy data)
        print( f"\nTest 3: Caching dummy embedding for '{test_text}'..." )
        dummy_embedding = [ 0.1 ] * 1536  # Create 1536-dimension dummy embedding
        cache_table.cache_embedding( test_text, dummy_embedding )
        print( "✓ Embedding cached successfully" )
        
        # Test 4: Verify cache hit
        print( f"\nTest 4: Verifying cache hit for '{test_text}'..." )
        has_cached_after = cache_table.has_cached_embedding( test_text )
        if has_cached_after:
            print( "✓ Cache HIT verified" )
            
            # Test 5: Retrieve cached embedding
            print( f"\nTest 5: Retrieving cached embedding..." )
            retrieved_embedding = cache_table.get_cached_embedding( test_text )
            if retrieved_embedding and len( retrieved_embedding ) == 1536:
                print( f"✓ Retrieved embedding with {len( retrieved_embedding )} dimensions" )
                print( f"  First 5 values: {retrieved_embedding[ :5 ]}" )
            else:
                print( "✗ Failed to retrieve valid embedding" )
        else:
            print( "✗ Cache miss after caching - unexpected!" )
        
        # Test 6: Test different normalized texts
        print( f"\nTest 6: Testing cache with different texts..." )
        test_texts = [ "hello world", "123 main street", "user@example.com" ]
        for text in test_texts:
            has_cache = cache_table.has_cached_embedding( text )
            print( f"  '{text}': {'HIT' if has_cache else 'MISS'}" )
        
        print( "\n✓ All basic cache operations completed successfully" )
        
    except Exception as e:
        print( f"✗ Error during smoke test: {e}" )
        du.print_stack_trace( e, explanation="Smoke test failed", caller="EmbeddingCacheTable.quick_smoke_test()" )
    
    print( "\n✓ EmbeddingCacheTable smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()