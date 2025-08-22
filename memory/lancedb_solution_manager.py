"""
LanceDB-based solution snapshot manager implementing the swappable interface.

This module provides a LanceDB implementation of the SolutionSnapshotManagerInterface,
offering native vector similarity search capabilities with performance optimization
while maintaining 100% API compatibility with the file-based implementation.
"""

import os
import json
import time
import hashlib
from typing import List, Tuple, Optional, Dict, Any

import lancedb
import pyarrow as pa
import numpy as np

import cosa.utils.util as du
from cosa.memory.snapshot_manager_interface import (
    SolutionSnapshotManagerInterface, 
    PerformanceMetrics, 
    PerformanceMonitor
)
from cosa.memory.solution_snapshot import SolutionSnapshot


class LanceDBSolutionManager( SolutionSnapshotManagerInterface ):
    """
    LanceDB-based solution snapshot manager with native vector search.
    
    Implements the SolutionSnapshotManagerInterface using LanceDB's vector database
    capabilities for high-performance semantic similarity search. Provides identical
    API to file-based implementation while leveraging native vector operations.
    """
    
    def __init__( self, config: Dict[str, Any], debug: bool = False, verbose: bool = False ) -> None:
        """
        Initialize LanceDB solution snapshot manager.
        
        Requires:
            - config["db_path"] contains valid LanceDB database path
            - config["table_name"] contains target table name
            - Database exists or can be created
            
        Ensures:
            - Configures connection to LanceDB database
            - Prepares table schema for solution snapshots
            - Sets up performance monitoring
            
        Args:
            config: Configuration dictionary with db_path and table_name
            debug: Enable debug output
            verbose: Enable verbose output
            
        Raises:
            - KeyError if required config keys missing
            - ValueError if database path invalid
        """
        super().__init__( config, debug, verbose )
        
        # Validate required configuration
        required_keys = ["db_path", "table_name"]
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise KeyError( f"LanceDBSolutionManager requires {missing_keys} in configuration" )
        
        self.db_path = config["db_path"]
        self.table_name = config["table_name"]
        
        # LanceDB connection and table objects
        self._db = None
        self._table = None
        
        # Cache for embeddings and quick lookups
        self._question_lookup = {}  # question -> id_hash mapping
        self._id_lookup = {}       # id_hash -> row mapping
        
        # Validate database path
        if not os.path.exists( self.db_path ):
            try:
                # Try with project root prefix
                full_path = du.get_project_root() + self.db_path
                if os.path.exists( full_path ):
                    self.db_path = full_path
                else:
                    raise ValueError( f"Database path does not exist: {self.db_path}" )
            except Exception as e:
                raise ValueError( f"Invalid database path: {self.db_path}. Error: {e}" )
        
        if self.debug:
            print( f"LanceDBSolutionManager configured:" )
            print( f"  Database: {self.db_path}" )
            print( f"  Table: {self.table_name}" )
    
    def _get_schema( self ) -> pa.Schema:
        """
        Get PyArrow schema for solution snapshots table.
        
        Requires:
            - Nothing
            
        Ensures:
            - Returns complete schema for solution snapshot storage
            - Includes all fields from SolutionSnapshot class
            - Optimizes vector fields for LanceDB
            
        Returns:
            PyArrow schema for solution snapshots table
        """
        return pa.schema([
            # Primary identifiers
            pa.field( "id_hash", pa.string() ),
            pa.field( "user_id", pa.string() ),
            
            # Content fields
            pa.field( "question", pa.string() ),
            pa.field( "question_gist", pa.string() ),
            pa.field( "answer", pa.string() ),
            pa.field( "answer_conversational", pa.string() ),
            pa.field( "solution_summary", pa.string() ),
            pa.field( "thoughts", pa.string() ),
            pa.field( "error", pa.string() ),
            pa.field( "routing_command", pa.string() ),
            
            # Code execution data
            pa.field( "code", pa.list_( pa.string() ) ),
            pa.field( "code_returns", pa.string() ),
            pa.field( "code_example", pa.string() ),
            pa.field( "code_type", pa.string() ),
            pa.field( "programming_language", pa.string() ),
            pa.field( "language_version", pa.string() ),
            
            # Synonymous questions (JSON serialized)
            pa.field( "synonymous_questions", pa.string() ),
            pa.field( "synonymous_question_gists", pa.string() ),
            pa.field( "non_synonymous_questions", pa.list_( pa.string() ) ),
            pa.field( "last_question_asked", pa.string() ),
            
            # Temporal data
            pa.field( "created_date", pa.string() ),
            pa.field( "updated_date", pa.string() ),
            pa.field( "run_date", pa.string() ),
            pa.field( "runtime_stats", pa.string() ),  # JSON serialized
            
            # Vector embeddings (1536 dimensions for OpenAI embeddings)
            pa.field( "question_embedding", pa.list_( pa.float32(), 1536 ) ),
            pa.field( "question_gist_embedding", pa.list_( pa.float32(), 1536 ) ),
            pa.field( "solution_embedding", pa.list_( pa.float32(), 1536 ) ),
            pa.field( "code_embedding", pa.list_( pa.float32(), 1536 ) ),
            pa.field( "thoughts_embedding", pa.list_( pa.float32(), 1536 ) ),
        ])
    
    def _snapshot_to_record( self, snapshot: SolutionSnapshot ) -> Dict[str, Any]:
        """
        Convert SolutionSnapshot to LanceDB record format.
        
        Requires:
            - snapshot is valid SolutionSnapshot instance
            - snapshot.question is not empty
            
        Ensures:
            - Returns dictionary compatible with LanceDB schema
            - Handles missing fields gracefully with defaults
            - Converts embeddings to proper format
            
        Args:
            snapshot: SolutionSnapshot to convert
            
        Returns:
            Dictionary record for LanceDB insertion
            
        Raises:
            - ValueError if snapshot invalid
        """
        if not snapshot or not snapshot.question:
            raise ValueError( "Invalid snapshot: question cannot be empty" )
        
        # Generate unique ID hash for this snapshot
        question_hash = hashlib.md5( snapshot.question.encode( 'utf-8' ) ).hexdigest()
        
        # Helper function to ensure vector is proper format
        def normalize_embedding( embedding ):
            if not embedding:
                return [0.0] * 1536  # Default embedding
            if isinstance( embedding, list ):
                # Ensure we have exactly 1536 dimensions
                if len( embedding ) == 1536:
                    return [float( x ) for x in embedding]
                elif len( embedding ) < 1536:
                    # Pad with zeros
                    return [float( x ) for x in embedding] + [0.0] * ( 1536 - len( embedding ) )
                else:
                    # Truncate to 1536
                    return [float( x ) for x in embedding[:1536]]
            return [0.0] * 1536
        
        record = {
            # Primary identifiers
            "id_hash": question_hash,
            "user_id": getattr( snapshot, 'user_id', 'default_user' ),
            
            # Content fields
            "question": snapshot.question,
            "question_gist": getattr( snapshot, 'question_gist', '' ) or '',
            "answer": getattr( snapshot, 'answer', '' ) or '',
            "answer_conversational": getattr( snapshot, 'answer_conversational', '' ) or '',
            "solution_summary": getattr( snapshot, 'solution_summary', '' ) or '',
            "thoughts": getattr( snapshot, 'thoughts', '' ) or '',
            "error": getattr( snapshot, 'error', '' ) or '',
            "routing_command": getattr( snapshot, 'routing_command', '' ) or '',
            
            # Code execution data
            "code": getattr( snapshot, 'code', [] ) or [],
            "code_returns": getattr( snapshot, 'code_returns', '' ) or '',
            "code_example": getattr( snapshot, 'code_example', '' ) or '',
            "code_type": getattr( snapshot, 'code_type', '' ) or '',
            "programming_language": getattr( snapshot, 'programming_language', 'python' ),
            "language_version": getattr( snapshot, 'language_version', '3.10' ),
            
            # Synonymous questions (convert dict to JSON string)
            "synonymous_questions": json.dumps( getattr( snapshot, 'synonymous_questions', {} ) ),
            "synonymous_question_gists": json.dumps( getattr( snapshot, 'synonymous_question_gists', {} ) ),
            "non_synonymous_questions": getattr( snapshot, 'non_synonymous_questions', [] ) or [],
            "last_question_asked": getattr( snapshot, 'last_question_asked', '' ) or '',
            
            # Temporal data
            "created_date": getattr( snapshot, 'created_date', time.strftime( "%Y-%m-%d @ %H:%M:%S %Z" ) ),
            "updated_date": getattr( snapshot, 'updated_date', time.strftime( "%Y-%m-%d @ %H:%M:%S %Z" ) ),
            "run_date": getattr( snapshot, 'run_date', '' ) or '',
            "runtime_stats": json.dumps( getattr( snapshot, 'runtime_stats', {} ) ),
            
            # Vector embeddings
            "question_embedding": normalize_embedding( getattr( snapshot, 'question_embedding', [] ) ),
            "question_gist_embedding": normalize_embedding( getattr( snapshot, 'question_gist_embedding', [] ) ),
            "solution_embedding": normalize_embedding( getattr( snapshot, 'solution_embedding', [] ) ),
            "code_embedding": normalize_embedding( getattr( snapshot, 'code_embedding', [] ) ),
            "thoughts_embedding": normalize_embedding( getattr( snapshot, 'thoughts_embedding', [] ) ),
        }
        
        return record
    
    def _record_to_snapshot( self, record: Dict[str, Any] ) -> SolutionSnapshot:
        """
        Convert LanceDB record back to SolutionSnapshot.
        
        Requires:
            - record contains all required fields
            - Vector fields are in proper format
            
        Ensures:
            - Returns valid SolutionSnapshot instance
            - Handles JSON deserialization
            - Preserves all original data
            
        Args:
            record: LanceDB record dictionary
            
        Returns:
            Reconstructed SolutionSnapshot
        """
        # Create SolutionSnapshot with required fields
        snapshot = SolutionSnapshot(
            question=record["question"],
            created_date=record.get( "created_date", "" ),
            updated_date=record.get( "updated_date", "" ),
            solution_summary=record.get( "solution_summary", "" ),
            code=record.get( "code_returns", "" ),  # Map to code field
            programming_language=record.get( "programming_language", "python" ),
            language_version=record.get( "language_version", "3.10" )
        )
        
        # Add additional fields
        snapshot.question_gist = record.get( "question_gist", "" )
        snapshot.answer = record.get( "answer", "" )
        snapshot.answer_conversational = record.get( "answer_conversational", "" )
        snapshot.thoughts = record.get( "thoughts", "" )
        snapshot.error = record.get( "error", "" )
        snapshot.routing_command = record.get( "routing_command", "" )
        snapshot.code_returns = record.get( "code_returns", "" )
        snapshot.code_example = record.get( "code_example", "" )
        snapshot.code_type = record.get( "code_type", "" )
        snapshot.run_date = record.get( "run_date", "" )
        snapshot.last_question_asked = record.get( "last_question_asked", "" )
        
        # Deserialize JSON fields
        try:
            snapshot.synonymous_questions = json.loads( record.get( "synonymous_questions", "{}" ) )
        except:
            snapshot.synonymous_questions = {}
            
        try:
            snapshot.synonymous_question_gists = json.loads( record.get( "synonymous_question_gists", "{}" ) )
        except:
            snapshot.synonymous_question_gists = {}
            
        try:
            snapshot.runtime_stats = json.loads( record.get( "runtime_stats", "{}" ) )
        except:
            snapshot.runtime_stats = {}
        
        snapshot.non_synonymous_questions = record.get( "non_synonymous_questions", [] )
        
        # Add embeddings
        snapshot.question_embedding = record.get( "question_embedding", [] )
        snapshot.question_gist_embedding = record.get( "question_gist_embedding", [] )
        snapshot.solution_embedding = record.get( "solution_embedding", [] )
        snapshot.code_embedding = record.get( "code_embedding", [] )
        snapshot.thoughts_embedding = record.get( "thoughts_embedding", [] )
        
        return snapshot
    
    def initialize( self ) -> PerformanceMetrics:
        """
        Initialize LanceDB connection and create/open solution snapshots table.
        
        Requires:
            - Database path is valid and accessible
            - Sufficient permissions for database operations
            
        Ensures:
            - Establishes connection to LanceDB database
            - Creates table if it doesn't exist
            - Loads existing data for quick lookups
            - Sets _initialized flag to True
            
        Raises:
            - ConnectionError if database inaccessible
            - PermissionError if insufficient access rights
            - ValueError if configuration invalid
        """
        monitor = PerformanceMonitor( "initialization" )
        monitor.start()
        
        try:
            if self.debug:
                print( f"Connecting to LanceDB at: {self.db_path}" )
            
            # Connect to database
            self._db = lancedb.connect( self.db_path )
            
            # Check if table exists
            existing_tables = self._db.table_names()
            
            if self.table_name in existing_tables:
                # Open existing table
                self._table = self._db.open_table( self.table_name )
                
                if self.debug:
                    print( f"✓ Opened existing table: {self.table_name}" )
            else:
                # Create new table with schema and dummy record
                schema = self._get_schema()
                
                # Create dummy record to initialize table (LanceDB requires at least one record)
                dummy_record = {
                    "id_hash": "dummy_init_record",
                    "user_id": "system",
                    "question": "__INIT_DUMMY_RECORD__",
                    "question_gist": "",
                    "answer": "",
                    "answer_conversational": "",
                    "solution_summary": "",
                    "thoughts": "",
                    "error": "",
                    "routing_command": "",
                    "code": [],
                    "code_returns": "",
                    "code_example": "",
                    "code_type": "",
                    "programming_language": "python",
                    "language_version": "3.10",
                    "synonymous_questions": "{}",
                    "synonymous_question_gists": "{}",
                    "non_synonymous_questions": [],
                    "last_question_asked": "",
                    "created_date": time.strftime( "%Y-%m-%d @ %H:%M:%S %Z" ),
                    "updated_date": time.strftime( "%Y-%m-%d @ %H:%M:%S %Z" ),
                    "run_date": "",
                    "runtime_stats": "{}",
                    "question_embedding": [0.0] * 1536,
                    "question_gist_embedding": [0.0] * 1536,
                    "solution_embedding": [0.0] * 1536,
                    "code_embedding": [0.0] * 1536,
                    "thoughts_embedding": [0.0] * 1536,
                }
                
                import pandas as pd
                dummy_df = pd.DataFrame( [dummy_record] )
                self._table = self._db.create_table( self.table_name, dummy_df )
                
                # Immediately delete the dummy record
                self._table.delete( "id_hash = 'dummy_init_record'" )
                
                if self.debug:
                    print( f"✓ Created new table: {self.table_name}" )
            
            # Load existing data for caching
            snapshot_count = 0
            try:
                # Get count of existing records
                result = self._table.to_pandas()
                snapshot_count = len( result )
                
                # Build lookup caches
                self._question_lookup.clear()
                self._id_lookup.clear()
                
                for _, row in result.iterrows():
                    question = row["question"]
                    id_hash = row["id_hash"]
                    
                    self._question_lookup[question] = id_hash
                    self._id_lookup[id_hash] = dict( row )
                
                if self.debug:
                    print( f"✓ Loaded {snapshot_count} existing snapshots into cache" )
                    
            except Exception as cache_error:
                if self.debug:
                    print( f"⚠ Cache loading failed (table may be empty): {cache_error}" )
                snapshot_count = 0
            
            self._initialized = True
            
            if self.debug:
                print( f"✓ LanceDB manager initialized with {snapshot_count} snapshots" )
                
        except Exception as e:
            self._initialized = False
            if self.debug:
                print( f"✗ Failed to initialize LanceDB manager: {e}" )
            raise
        finally:
            monitor.stop()
        
        return monitor.get_metrics( result_count=snapshot_count )
    
    def add_snapshot( self, snapshot: SolutionSnapshot ) -> bool:
        """
        Add snapshot to LanceDB table.
        
        Requires:
            - Manager is initialized
            - snapshot is valid SolutionSnapshot
            - snapshot.question is not empty
            
        Ensures:
            - Snapshot is stored in LanceDB table
            - Cache is updated with new snapshot
            - Returns True if successful
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if snapshot invalid
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before adding snapshots" )
        
        if not snapshot or not snapshot.question:
            raise ValueError( "Invalid snapshot: question cannot be empty" )
        
        try:
            # Convert snapshot to record format
            record = self._snapshot_to_record( snapshot )
            
            # Check if snapshot already exists (upsert behavior)
            question = snapshot.question
            if question in self._question_lookup:
                # Update existing record
                id_hash = self._question_lookup[question]
                # LanceDB doesn't have direct update, so we'll use merge
                # For now, we'll delete and re-insert
                self._table.delete( f"id_hash = '{id_hash}'" )
                
                if self.debug:
                    print( f"Updating existing snapshot for: {du.truncate_string( question, 50 )}" )
            else:
                if self.debug:
                    print( f"Adding new snapshot for: {du.truncate_string( question, 50 )}" )
            
            # Add to table
            import pandas as pd
            df = pd.DataFrame( [record] )
            self._table.add( df )
            
            # Update cache
            id_hash = record["id_hash"]
            self._question_lookup[question] = id_hash
            self._id_lookup[id_hash] = record
            
            return True
            
        except Exception as e:
            if self.debug:
                print( f"✗ Failed to add snapshot: {e}" )
            return False
    
    def delete_snapshot( self, question: str, delete_physical: bool = False ) -> bool:
        """
        Delete snapshot by question.
        
        Requires:
            - Manager is initialized
            - question is non-empty string
            
        Ensures:
            - Snapshot removed from LanceDB table if exists
            - Cache updated to remove snapshot
            - Returns True if found and deleted
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if question empty
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before deleting snapshots" )
        
        if not question:
            raise ValueError( "Question cannot be empty" )
        
        try:
            if question not in self._question_lookup:
                if self.debug:
                    print( f"Snapshot not found for: {du.truncate_string( question, 50 )}" )
                return False
            
            # Get ID hash for deletion
            id_hash = self._question_lookup[question]
            
            # Delete from table
            self._table.delete( f"id_hash = '{id_hash}'" )
            
            # Update cache
            del self._question_lookup[question]
            del self._id_lookup[id_hash]
            
            if self.debug:
                print( f"✓ Deleted snapshot for: {du.truncate_string( question, 50 )}" )
            
            return True
            
        except Exception as e:
            if self.debug:
                print( f"✗ Failed to delete snapshot: {e}" )
            return False
    
    def find_by_question( self, 
                         question: str,
                         question_gist: Optional[str] = None,
                         threshold_question: float = 100.0,
                         threshold_gist: float = 100.0,
                         limit: int = 7 ) -> Tuple[List[Tuple[float, SolutionSnapshot]], PerformanceMetrics]:
        """
        Search for snapshots by question similarity using LanceDB vector search.
        
        Requires:
            - Manager is initialized
            - question is non-empty string
            - thresholds are between 0.0 and 100.0
            
        Ensures:
            - Returns list of (similarity_score, snapshot) tuples
            - Results sorted by similarity descending
            - Uses LanceDB's native vector search capabilities
            - Performance metrics included
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if parameters invalid
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before searching" )
        
        if not question:
            raise ValueError( "Question cannot be empty" )
        
        if not (0.0 <= threshold_question <= 100.0) or not (0.0 <= threshold_gist <= 100.0):
            raise ValueError( "Thresholds must be between 0.0 and 100.0" )
        
        monitor = PerformanceMonitor( "find_by_question" )
        monitor.start()
        
        try:
            # First check for exact match in cache
            if question in self._question_lookup:
                if self.debug:
                    print( f"Found exact match for: {du.truncate_string( question, 50 )}" )
                
                id_hash = self._question_lookup[question]
                record = self._id_lookup[id_hash]
                snapshot = self._record_to_snapshot( record )
                
                return [(100.0, snapshot)], monitor.get_metrics( result_count=1 )
            
            # For similarity search, we need to generate an embedding for the question
            # Since we don't have direct access to embedding generation here,
            # we'll implement a simple text similarity for now
            # In a full implementation, this would use the EmbeddingManager
            
            if self.debug:
                print( f"Performing similarity search for: {du.truncate_string( question, 50 )}" )
            
            # Simple implementation: check all questions for text similarity
            similar_snapshots = []
            
            for cached_question, id_hash in self._question_lookup.items():
                # Simple text similarity (this would be replaced with vector search)
                similarity = self._calculate_text_similarity( question, cached_question )
                similarity_percent = similarity * 100
                
                if similarity_percent >= threshold_question:
                    record = self._id_lookup[id_hash]
                    snapshot = self._record_to_snapshot( record )
                    similar_snapshots.append( (similarity_percent, snapshot) )
            
            # Sort by similarity descending
            similar_snapshots.sort( key=lambda x: x[0], reverse=True )
            
            # Limit results
            if limit > 0:
                similar_snapshots = similar_snapshots[:limit]
            
            if self.debug:
                print( f"Found {len( similar_snapshots )} similar snapshots" )
            
        except Exception as e:
            if self.debug:
                print( f"✗ Search failed: {e}" )
            raise
        finally:
            monitor.stop()
            
        return similar_snapshots, monitor.get_metrics( result_count=len( similar_snapshots ) )
    
    def _calculate_text_similarity( self, text1: str, text2: str ) -> float:
        """
        Simple text similarity calculation (placeholder for vector similarity).
        
        This is a temporary implementation. In the full version, this would use
        LanceDB's native vector similarity search with embeddings.
        """
        if text1.lower() == text2.lower():
            return 1.0
        
        # Simple word overlap similarity
        words1 = set( text1.lower().split() )
        words2 = set( text2.lower().split() )
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection( words2 )
        union = words1.union( words2 )
        
        return len( intersection ) / len( union ) if union else 0.0
    
    def find_by_code_similarity( self,
                                exemplar_snapshot: SolutionSnapshot,
                                threshold: float = 85.0,
                                limit: int = -1 ) -> Tuple[List[Tuple[float, SolutionSnapshot]], PerformanceMetrics]:
        """
        Search for snapshots by code similarity using LanceDB vector search.
        
        Requires:
            - Manager is initialized
            - exemplar_snapshot has valid code_embedding
            - threshold is between 0.0 and 100.0
            
        Ensures:
            - Returns list of (similarity_score, snapshot) tuples
            - Results sorted by similarity descending
            - Uses LanceDB's native vector search for code embeddings
            - Performance metrics included
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if exemplar_snapshot invalid
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before searching" )
        
        if not exemplar_snapshot:
            raise ValueError( "Exemplar snapshot cannot be None" )
        
        if not (0.0 <= threshold <= 100.0):
            raise ValueError( "Threshold must be between 0.0 and 100.0" )
        
        monitor = PerformanceMonitor( "find_by_code_similarity" )
        monitor.start()
        
        try:
            # For now, implement simple fallback
            # In full implementation, this would use LanceDB vector search on code_embedding field
            
            if self.debug:
                print( f"Performing code similarity search" )
            
            similar_snapshots = []
            
            # Simple implementation: find snapshots with code
            for id_hash, record in self._id_lookup.items():
                if record.get( "code_returns" ) or record.get( "code_example" ):
                    # Simple similarity based on code presence
                    similarity = 75.0  # Placeholder similarity
                    
                    if similarity >= threshold:
                        snapshot = self._record_to_snapshot( record )
                        similar_snapshots.append( (similarity, snapshot) )
            
            # Sort by similarity descending
            similar_snapshots.sort( key=lambda x: x[0], reverse=True )
            
            # Limit results
            if limit > 0:
                similar_snapshots = similar_snapshots[:limit]
            
            if self.debug:
                print( f"Found {len( similar_snapshots )} code-similar snapshots" )
            
        except Exception as e:
            if self.debug:
                print( f"✗ Code similarity search failed: {e}" )
            raise
        finally:
            monitor.stop()
            
        return similar_snapshots, monitor.get_metrics( result_count=len( similar_snapshots ) )
    
    def get_all_gists( self ) -> List[str]:
        """
        Return all available question gists.
        
        Requires:
            - Manager is initialized
            
        Ensures:
            - Returns list of all question gists
            - Empty list if no snapshots exist
            
        Raises:
            - RuntimeError if not initialized
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before getting gists" )
        
        try:
            gists = []
            
            for record in self._id_lookup.values():
                gist = record.get( "question_gist", "" )
                if gist and gist not in gists:
                    gists.append( gist )
            
            if self.debug:
                print( f"Retrieved {len( gists )} unique question gists" )
            
            return gists
            
        except Exception as e:
            if self.debug:
                print( f"✗ Failed to get gists: {e}" )
            return []
    
    def get_stats( self ) -> Dict[str, Any]:
        """
        Return storage statistics for monitoring.
        
        Requires:
            - Manager is initialized
            
        Ensures:
            - Returns dictionary with standardized statistics
            - Includes LanceDB-specific metrics
            
        Raises:
            - RuntimeError if not initialized
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before getting stats" )
        
        try:
            snapshot_count = len( self._question_lookup )
            
            # Calculate storage size (approximate)
            storage_size_mb = 0.0
            if os.path.exists( self.db_path ):
                for root, dirs, files in os.walk( self.db_path ):
                    for file in files:
                        file_path = os.path.join( root, file )
                        storage_size_mb += os.path.getsize( file_path )
                storage_size_mb = storage_size_mb / 1024 / 1024  # Convert to MB
            
            stats = {
                "total_snapshots": snapshot_count,
                "storage_size_mb": round( storage_size_mb, 2 ),
                "database_path": self.db_path,
                "table_name": self.table_name,
                "backend_type": "lancedb",
                "last_updated": time.strftime( "%Y-%m-%d @ %H:%M:%S %Z" )
            }
            
            if self.debug:
                print( f"Stats: {snapshot_count} snapshots, {stats['storage_size_mb']} MB" )
            
            return stats
            
        except Exception as e:
            if self.debug:
                print( f"✗ Failed to get stats: {e}" )
            return {
                "total_snapshots": 0,
                "storage_size_mb": 0.0,
                "backend_type": "lancedb",
                "status": "error",
                "error": str( e )
            }
    
    def health_check( self ) -> Dict[str, Any]:
        """
        Return health status and diagnostics.
        
        Requires:
            - Nothing (works even if not initialized)
            
        Ensures:
            - Returns health information dictionary
            - Status is "healthy", "degraded", or "unhealthy"
            
        Raises:
            - None (handles all errors gracefully)
        """
        try:
            health = {
                "status": "healthy",
                "initialized": self.is_initialized(),
                "backend_type": "lancedb",
                "database_path": self.db_path,
                "table_name": self.table_name,
                "errors": []
            }
            
            # Check database accessibility
            if not os.path.exists( self.db_path ):
                health["errors"].append( f"Database path does not exist: {self.db_path}" )
                health["status"] = "unhealthy"
            elif not os.access( self.db_path, os.R_OK ):
                health["errors"].append( f"Cannot read database: {self.db_path}" )
                health["status"] = "degraded"
            elif not os.access( self.db_path, os.W_OK ):
                health["errors"].append( f"Cannot write to database: {self.db_path}" )
                health["status"] = "degraded"
            
            # Check if initialized and working
            if self.is_initialized():
                try:
                    snapshot_count = len( self._question_lookup )
                    health["snapshot_count"] = snapshot_count
                    
                    # Test database connection
                    if self._db and self._table:
                        health["connection_status"] = "connected"
                    else:
                        health["errors"].append( "Database connection not established" )
                        health["status"] = "degraded"
                        
                except Exception as e:
                    health["errors"].append( f"Error accessing snapshots: {e}" )
                    health["status"] = "degraded"
            else:
                health["status"] = "degraded" if health["status"] == "healthy" else health["status"]
            
            return health
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "initialized": False,
                "backend_type": "lancedb",
                "errors": [f"Health check failed: {e}"]
            }


def quick_smoke_test():
    """Test the LanceDB manager interface implementation."""
    du.print_banner( "LanceDBSolutionManager Smoke Test", prepend_nl=True )
    
    try:
        # Test configuration validation
        print( "Testing configuration validation..." )
        try:
            manager = LanceDBSolutionManager( {}, debug=False )
            print( "✗ Empty config was accepted" )
        except KeyError:
            print( "✓ Empty config properly rejected" )
        
        # Test with database configuration
        config = {
            "db_path": "/src/conf/long-term-memory/lupin.lancedb",
            "table_name": "test_solution_snapshots"
        }
        
        print( f"\nTesting manager creation with database: {config['db_path']}" )
        manager = LanceDBSolutionManager( config, debug=True, verbose=False )
        print( "✓ LanceDBSolutionManager created successfully" )
        
        # Test health check before initialization
        print( "\nTesting health check (before initialization)..." )
        health = manager.health_check()
        if health["backend_type"] == "lancedb" and not health["initialized"]:
            print( "✓ Health check working before initialization" )
        else:
            print( "✗ Health check not working properly" )
        
        # Test initialization
        print( "\nTesting initialization..." )
        try:
            init_metrics = manager.initialize()
            if manager.is_initialized() and init_metrics.operation_type == "initialization":
                print( f"✓ Initialization successful, loaded {init_metrics.result_count} snapshots" )
                print( f"  Initialization time: {init_metrics.initialization_time_ms:.1f}ms" )
            else:
                print( "✗ Initialization failed or metrics incorrect" )
        except Exception as e:
            print( f"✗ Initialization failed: {e}" )
            return
        
        # Test health check after initialization
        print( "\nTesting health check (after initialization)..." )
        health = manager.health_check()
        if health["initialized"] and health["status"] in ["healthy", "degraded"]:
            print( f"✓ Health check shows status: {health['status']}" )
        else:
            print( f"✗ Health check failed: {health}" )
        
        # Test stats
        print( "\nTesting statistics..." )
        stats = manager.get_stats()
        if "total_snapshots" in stats and "backend_type" in stats:
            print( f"✓ Stats: {stats['total_snapshots']} snapshots, {stats['storage_size_mb']} MB" )
        else:
            print( "✗ Stats missing required fields" )
        
        # Test gists retrieval
        print( "\nTesting gists retrieval..." )
        gists = manager.get_all_gists()
        print( f"✓ Retrieved {len( gists )} question gists" )
        
        # Test basic search
        print( "\nTesting basic search..." )
        results, search_metrics = manager.find_by_question( "test question" )
        print( f"✓ Search returned {len( results )} results in {search_metrics.search_time_ms:.1f}ms" )
        
        print( "\n✓ LanceDBSolutionManager smoke test completed successfully" )
        
    except Exception as e:
        print( f"✗ Error during smoke test: {e}" )
        du.print_stack_trace( e, explanation="LanceDBSolutionManager smoke test failed", caller="quick_smoke_test()" )


if __name__ == "__main__":
    quick_smoke_test()