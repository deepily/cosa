"""
File-based solution snapshot manager implementing the swappable interface.

This module wraps the existing SolutionSnapshotManager to implement the
SolutionSnapshotManagerInterface, adding performance monitoring and
standardized contracts while preserving all existing functionality.
"""

import os
import time
from typing import List, Tuple, Optional, Dict, Any

import cosa.utils.util as du
from cosa.memory.snapshot_manager_interface import (
    SolutionSnapshotManagerInterface, 
    PerformanceMetrics, 
    PerformanceMonitor
)
from cosa.memory.solution_snapshot import SolutionSnapshot
from cosa.memory.solution_snapshot_mgr import SolutionSnapshotManager


class FileBasedSolutionManager( SolutionSnapshotManagerInterface ):
    """
    File-based solution snapshot manager with interface compliance.
    
    Wraps the existing SolutionSnapshotManager to implement the swappable
    interface while adding performance monitoring and standardized error handling.
    Maintains 100% backward compatibility with existing functionality.
    """
    
    def __init__( self, config: Dict[str, Any], debug: bool = False, verbose: bool = False ) -> None:
        """
        Initialize file-based solution snapshot manager.
        
        Requires:
            - config["path"] contains valid directory path for JSON files
            - Directory exists or can be created
            
        Ensures:
            - Initializes underlying SolutionSnapshotManager
            - Configures performance monitoring
            - Prepares for storage operations
            
        Args:
            config: Configuration dictionary with "path" key
            debug: Enable debug output
            verbose: Enable verbose output
            
        Raises:
            - KeyError if config["path"] not provided
            - ValueError if path is invalid
        """
        super().__init__( config, debug, verbose )
        
        # Validate required configuration
        if "path" not in config:
            raise KeyError( "FileBasedSolutionManager requires 'path' in configuration" )
        
        self.path = config["path"]
        self._underlying_manager = None
        
        # Validate path exists or can be created
        if not os.path.exists( self.path ):
            try:
                # Try to get project root and construct full path
                full_path = du.get_project_root() + self.path
                if not os.path.exists( full_path ):
                    raise ValueError( f"Path does not exist and cannot be created: {self.path}" )
                self.path = full_path
            except Exception as e:
                raise ValueError( f"Invalid path configuration: {self.path}. Error: {e}" )
        
        if self.debug:
            print( f"FileBasedSolutionManager configured with path: {self.path}" )
    
    def initialize( self ) -> PerformanceMetrics:
        """
        Initialize the underlying file-based storage system.
        
        Requires:
            - Path is valid and accessible
            - JSON files are readable (if any exist)
            
        Ensures:
            - Creates underlying SolutionSnapshotManager
            - Loads all existing snapshots from disk
            - Returns initialization performance metrics
            - Sets _initialized flag to True
            
        Raises:
            - PermissionError if cannot read/write to path
            - IOError if file operations fail
            - JSONDecodeError if snapshot files corrupted
        """
        monitor = PerformanceMonitor( "initialization" )
        monitor.start()
        
        try:
            if self.debug:
                print( f"Initializing file-based solution manager at: {self.path}" )
            
            # Create underlying manager with same debug settings
            self._underlying_manager = SolutionSnapshotManager( 
                path=self.path, 
                debug=self.debug, 
                verbose=self.verbose 
            )
            
            # Load snapshots (this happens automatically in SolutionSnapshotManager.__init__)
            self._initialized = True
            
            if self.debug:
                snapshot_count = len( self._underlying_manager._snapshots_by_question )
                print( f"✓ Loaded {snapshot_count} snapshots from {self.path}" )
            
        except Exception as e:
            self._initialized = False
            if self.debug:
                print( f"✗ Failed to initialize file-based manager: {e}" )
            raise
        finally:
            monitor.stop()
        
        return monitor.get_metrics( 
            result_count=len( self._underlying_manager._snapshots_by_question ) if self._underlying_manager else 0
        )
    
    def add_snapshot( self, snapshot: SolutionSnapshot ) -> bool:
        """
        Add snapshot to file-based storage.
        
        Requires:
            - Manager is initialized
            - snapshot is valid SolutionSnapshot
            - snapshot.question is not empty
            
        Ensures:
            - Snapshot is written to JSON file
            - Snapshot is added to in-memory indexes
            - Returns True if successful
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if snapshot invalid
            - IOError if file write fails
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before adding snapshots" )
        
        if not snapshot or not snapshot.question:
            raise ValueError( "Invalid snapshot: question cannot be empty" )
        
        try:
            self._underlying_manager.add_snapshot( snapshot )
            
            if self.debug:
                print( f"✓ Added snapshot for question: {du.truncate_string( snapshot.question, 50 )}" )
            
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
            - Snapshot removed from memory indexes
            - Optionally removes JSON file if delete_physical=True
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
            success = self._underlying_manager.delete_snapshot( question, delete_file=delete_physical )
            
            if self.debug:
                action = "deleted" if success else "not found"
                print( f"Snapshot for '{du.truncate_string( question, 50 )}' {action}" )
            
            return success
            
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
        Search for snapshots by question similarity.
        
        Requires:
            - Manager is initialized
            - question is non-empty string
            - thresholds are between 0.0 and 100.0
            
        Ensures:
            - Returns list of (similarity_score, snapshot) tuples
            - Results sorted by similarity descending
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
            # Use underlying manager's search method
            similar_snapshots = self._underlying_manager.get_snapshots_by_question(
                question=question,
                question_gist=question_gist,
                threshold_question=threshold_question,
                threshold_gist=threshold_gist,
                limit=limit,
                debug=self.debug
            )
            
            if self.debug:
                print( f"Found {len( similar_snapshots )} similar snapshots for: {du.truncate_string( question, 50 )}" )
            
        except Exception as e:
            if self.debug:
                print( f"✗ Search failed: {e}" )
            raise
        finally:
            monitor.stop()
            
        return similar_snapshots, monitor.get_metrics( result_count=len( similar_snapshots ) )
    
    def find_by_code_similarity( self,
                                exemplar_snapshot: SolutionSnapshot,
                                threshold: float = 85.0,
                                limit: int = -1 ) -> Tuple[List[Tuple[float, SolutionSnapshot]], PerformanceMetrics]:
        """
        Search for snapshots by code similarity.
        
        Requires:
            - Manager is initialized
            - exemplar_snapshot has valid code_embedding
            - threshold is between 0.0 and 100.0
            
        Ensures:
            - Returns list of (similarity_score, snapshot) tuples
            - Results sorted by similarity descending
            - Performance metrics included
            
        Raises:
            - RuntimeError if not initialized
            - ValueError if exemplar_snapshot invalid
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before searching" )
        
        if not exemplar_snapshot or not exemplar_snapshot.code_embedding:
            raise ValueError( "Exemplar snapshot must have valid code_embedding" )
        
        if not (0.0 <= threshold <= 100.0):
            raise ValueError( "Threshold must be between 0.0 and 100.0" )
        
        monitor = PerformanceMonitor( "find_by_code_similarity" )
        monitor.start()
        
        try:
            # Use underlying manager's code similarity search
            similar_snapshots = self._underlying_manager.get_snapshots_by_code_similarity(
                exemplar_snapshot=exemplar_snapshot,
                threshold=threshold,
                limit=limit
            )
            
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
            gists = self._underlying_manager.get_gists()
            
            if self.debug:
                print( f"Retrieved {len( gists )} question gists" )
            
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
            - Includes file count, storage size, etc.
            
        Raises:
            - RuntimeError if not initialized
        """
        if not self.is_initialized():
            raise RuntimeError( "Manager must be initialized before getting stats" )
        
        try:
            snapshot_count = len( self._underlying_manager._snapshots_by_question )
            
            # Calculate storage size
            storage_size_mb = 0.0
            if os.path.exists( self.path ):
                for filename in os.listdir( self.path ):
                    if filename.endswith( ".json" ):
                        file_path = os.path.join( self.path, filename )
                        if os.path.isfile( file_path ):
                            storage_size_mb += os.path.getsize( file_path )
                storage_size_mb = storage_size_mb / 1024 / 1024  # Convert to MB
            
            stats = {
                "total_snapshots": snapshot_count,
                "storage_size_mb": round( storage_size_mb, 2 ),
                "storage_path": self.path,
                "backend_type": "file_based",
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
                "backend_type": "file_based",
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
                "backend_type": "file_based",
                "storage_path": self.path,
                "errors": []
            }
            
            # Check path accessibility
            if not os.path.exists( self.path ):
                health["errors"].append( f"Storage path does not exist: {self.path}" )
                health["status"] = "unhealthy"
            elif not os.access( self.path, os.R_OK ):
                health["errors"].append( f"Cannot read from storage path: {self.path}" )
                health["status"] = "degraded"
            elif not os.access( self.path, os.W_OK ):
                health["errors"].append( f"Cannot write to storage path: {self.path}" )
                health["status"] = "degraded"
            
            # Check if initialized and working
            if self.is_initialized():
                try:
                    snapshot_count = len( self._underlying_manager._snapshots_by_question )
                    health["snapshot_count"] = snapshot_count
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
                "backend_type": "file_based",
                "errors": [f"Health check failed: {e}"]
            }


def quick_smoke_test():
    """Test the file-based manager interface implementation."""
    du.print_banner( "FileBasedSolutionManager Smoke Test", prepend_nl=True )
    
    try:
        # Test configuration validation
        print( "Testing configuration validation..." )
        try:
            manager = FileBasedSolutionManager( {}, debug=False )
            print( "✗ Empty config was accepted" )
        except KeyError:
            print( "✓ Empty config properly rejected" )
        
        # Test with test path
        test_path = du.get_project_root() + "/src/conf/long-term-memory/solutions/"
        config = {"path": test_path}
        
        print( f"\nTesting manager creation with path: {test_path}" )
        manager = FileBasedSolutionManager( config, debug=True, verbose=False )
        print( "✓ FileBasedSolutionManager created successfully" )
        
        # Test health check before initialization
        print( "\nTesting health check (before initialization)..." )
        health = manager.health_check()
        if health["backend_type"] == "file_based" and not health["initialized"]:
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
        
        # Test search (if snapshots exist)
        if stats["total_snapshots"] > 0:
            print( "\nTesting question search..." )
            results, search_metrics = manager.find_by_question( "what day is today" )
            print( f"✓ Search returned {len( results )} results in {search_metrics.search_time_ms:.1f}ms" )
        else:
            print( "\nSkipping search test (no snapshots available)" )
        
        print( "\n✓ FileBasedSolutionManager smoke test completed successfully" )
        
    except Exception as e:
        print( f"✗ Error during smoke test: {e}" )
        du.print_stack_trace( e, explanation="FileBasedSolutionManager smoke test failed", caller="quick_smoke_test()" )


if __name__ == "__main__":
    quick_smoke_test()