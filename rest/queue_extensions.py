"""
Queue Extensions for User-Specific Functionality

This module provides extensions to the COSA queue system to support
user-specific job tracking and filtering.
"""

from typing import Dict, List, Optional


class UserJobTracker:
    """
    Tracks which jobs belong to which users.
    
    This is a temporary solution until user_id is added to SolutionSnapshot.
    In production, this information should be stored in the job objects themselves.
    """
    
    def __init__(self):
        # Map job_id to user_id
        self.job_to_user: Dict[str, str] = {}
        # Map user_id to list of job_ids
        self.user_jobs: Dict[str, List[str]] = {}
    
    def associate_job_with_user(self, job_id: str, user_id: str):
        """Associate a job with a user."""
        self.job_to_user[job_id] = user_id
        
        if user_id not in self.user_jobs:
            self.user_jobs[user_id] = []
        self.user_jobs[user_id].append(job_id)
    
    def get_user_for_job(self, job_id: str) -> Optional[str]:
        """Get the user ID associated with a job."""
        return self.job_to_user.get(job_id)
    
    def get_jobs_for_user(self, user_id: str) -> List[str]:
        """Get all job IDs for a user."""
        return self.user_jobs.get(user_id, [])
    
    def remove_job(self, job_id: str):
        """Remove a job from tracking."""
        if job_id in self.job_to_user:
            user_id = self.job_to_user[job_id]
            del self.job_to_user[job_id]
            
            if user_id in self.user_jobs:
                self.user_jobs[user_id].remove(job_id)
                if not self.user_jobs[user_id]:
                    del self.user_jobs[user_id]


# Global instance for tracking user jobs
user_job_tracker = UserJobTracker()


def push_job_with_user(todo_queue, question: str, websocket_id: str, user_id: str) -> str:
    """
    Push a job to the queue and track the user association.
    
    This wraps the standard push_job method to add user tracking.
    
    Args:
        todo_queue: The TodoFifoQueue instance
        question: The question to process
        websocket_id: The websocket session ID
        user_id: The authenticated user ID
        
    Returns:
        str: Result message from push_job
    """
    # Call the modified push_job method with user_id
    result = todo_queue.push_job(question, websocket_id, user_id)
    
    # Extract job ID from the queue (last pushed item)
    if todo_queue.size() > 0:
        # Get the most recent job
        last_job = todo_queue.queue_list[-1]
        if hasattr(last_job, 'id_hash'):
            user_job_tracker.associate_job_with_user(last_job.id_hash, user_id)
            print(f"[QUEUE] Associated job {last_job.id_hash} with user {user_id}")
    
    return result


def emit_to_job_owner(websocket_manager, job_id: str, event: str, data: dict):
    """
    Emit an event only to the user who owns the job.
    
    Args:
        websocket_manager: The WebSocketManager instance
        job_id: The job ID to look up
        event: The event type to emit
        data: The data to send
    """
    user_id = user_job_tracker.get_user_for_job(job_id)
    if user_id:
        # Use the synchronous emit wrapper which will create an async task
        websocket_manager.emit_to_user_sync(user_id, event, data)
    else:
        print(f"[QUEUE] No user found for job {job_id}, broadcasting to all")
        # Fallback to broadcast if no user association found
        websocket_manager.emit(event, data)