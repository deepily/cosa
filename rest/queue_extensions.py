"""
Queue Extensions for User-Specific Functionality

This module provides extensions to the COSA queue system to support
user-specific job tracking and filtering.
"""

from typing import Dict, List, Optional
from threading import Lock


class UserJobTracker:
    """
    Singleton tracker for job-to-user associations.
    
    This class maintains mappings between jobs and users using a thread-safe
    singleton pattern, consistent with other COSA singletons like GistNormalizer
    and EmbeddingManager.
    
    Note: This is a temporary solution until user_id is added to SolutionSnapshot.
    In production, this information should be stored in the job objects themselves.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__( cls ):
        """
        Create or return singleton instance.
        
        Requires:
            - Nothing
            
        Ensures:
            - Returns the single instance of UserJobTracker
            - Thread-safe initialization
            - Instance created only once
            
        Raises:
            - None
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__( cls )
                    # Initialize instance attributes
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__( self ):
        """
        Initialize the tracker if not already initialized.
        
        Requires:
            - Instance created via __new__
            
        Ensures:
            - Attributes initialized only once
            - Thread-safe initialization
            
        Raises:
            - None
        """
        # Prevent re-initialization of singleton
        if self._initialized:
            return
            
        with self._lock:
            if not self._initialized:
                # Map job_id to user_id
                self.job_to_user: Dict[str, str] = {}
                # Map user_id to list of job_ids
                self.user_jobs: Dict[str, List[str]] = {}
                # Map session_id to list of job_ids (for job-notification correlation)
                self.session_to_jobs: Dict[str, List[str]] = {}
                # Map job_id to session_id (reverse lookup)
                self.job_to_session: Dict[str, str] = {}
                self._initialized = True
                print( "[UserJobTracker] Singleton instance initialized" )

    def associate_job_with_user( self, job_id: str, user_id: str ) -> None:
        """
        Associate a job with a user.
        
        Requires:
            - job_id is a valid job identifier
            - user_id is a valid user identifier
            
        Ensures:
            - Job is mapped to user
            - User's job list is updated
            - Thread-safe operation
            
        Raises:
            - None
        """
        with self._lock:
            self.job_to_user[job_id] = user_id

            if user_id not in self.user_jobs:
                self.user_jobs[user_id] = []
            self.user_jobs[user_id].append( job_id )

    def get_user_for_job( self, job_id: str ) -> Optional[str]:
        """
        Get the user ID associated with a job.
        
        Requires:
            - job_id is a string
            
        Ensures:
            - Returns user_id if job exists
            - Returns None if job not found
            - Thread-safe read operation
            
        Raises:
            - None
        """
        with self._lock:
            return self.job_to_user.get( job_id )

    def get_jobs_for_user( self, user_id: str ) -> List[str]:
        """
        Get all job IDs for a user.
        
        Requires:
            - user_id is a string
            
        Ensures:
            - Returns list of job IDs for user
            - Returns empty list if user not found
            - Returns copy to prevent external modification
            - Thread-safe read operation
            
        Raises:
            - None
        """
        with self._lock:
            return self.user_jobs.get( user_id, [] ).copy()

    def generate_user_scoped_hash( self, base_hash: str, user_id: str ) -> str:
        """
        Generate a compound hash unique to question + user.

        Single source of truth for user-scoped job identification.

        Requires:
            - base_hash is the original question/snapshot hash
            - user_id is the authenticated user's ID

        Ensures:
            - Returns compound hash in format "{base_hash}::{user_id}"
            - Same inputs always produce same output (idempotent)
            - Different users get different hashes (no collision)

        Raises:
            - None
        """
        # Strip any existing user scope to prevent double-scoping on cache replay
        clean_hash = self.extract_base_hash( base_hash )
        return f"{clean_hash}::{user_id}"

    def extract_base_hash( self, compound_hash: str ) -> str:
        """
        Extract the base question hash from a compound hash.

        Requires:
            - compound_hash may be compound or simple format

        Ensures:
            - Returns base hash (before :: separator)
            - Returns unchanged if no separator found

        Raises:
            - None
        """
        return compound_hash.split( '::' )[0] if '::' in compound_hash else compound_hash

    def remove_job( self, job_id: str ) -> None:
        """
        Remove a job from tracking.
        
        Requires:
            - job_id is a string
            
        Ensures:
            - Job removed from job_to_user mapping
            - Job removed from user's job list
            - Empty user job lists are cleaned up
            - Thread-safe operation
            
        Raises:
            - None
        """
        with self._lock:
            if job_id in self.job_to_user:
                user_id = self.job_to_user[job_id]
                del self.job_to_user[job_id]

                if user_id in self.user_jobs:
                    self.user_jobs[user_id].remove( job_id )
                    if not self.user_jobs[user_id]:
                        del self.user_jobs[user_id]


    def associate_job_with_session( self, job_id: str, session_id: str ) -> None:
        """
        Associate a job with a WebSocket session for notification correlation.

        Requires:
            - job_id is a valid job identifier
            - session_id is a valid WebSocket session identifier

        Ensures:
            - Job is mapped to session
            - Session's job list is updated
            - Thread-safe operation

        Raises:
            - None
        """
        if not session_id:  # Skip empty session IDs
            return

        with self._lock:
            self.job_to_session[job_id] = session_id

            if session_id not in self.session_to_jobs:
                self.session_to_jobs[session_id] = []
            self.session_to_jobs[session_id].append( job_id )

    def get_session_for_job( self, job_id: str ) -> Optional[str]:
        """
        Get the session ID associated with a job.

        Requires:
            - job_id is a string

        Ensures:
            - Returns session_id if job exists
            - Returns None if job not found
            - Thread-safe read operation

        Raises:
            - None
        """
        with self._lock:
            return self.job_to_session.get( job_id )

    def get_jobs_for_session( self, session_id: str ) -> List[str]:
        """
        Get all job IDs for a session.

        Requires:
            - session_id is a string

        Ensures:
            - Returns list of job IDs for session
            - Returns empty list if session not found
            - Returns copy to prevent external modification
            - Thread-safe read operation

        Raises:
            - None
        """
        with self._lock:
            return self.session_to_jobs.get( session_id, [] ).copy()


# Global instance for tracking user jobs
user_job_tracker = UserJobTracker()
