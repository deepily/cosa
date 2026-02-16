"""
CJ Flow background consumer thread for producer-consumer queue pattern.

This module implements the consumer side of the TodoFifoQueue -> RunningFifoQueue
producer-consumer pattern, replacing the old polling-based approach with
event-driven processing using threading.Condition.
"""

import threading
import time
from typing import Any
from datetime import datetime
import cosa.utils.util as du
from cosa.rest.queue_util import emit_job_state_transition


def start_todo_producer_run_consumer_thread( todo_queue: Any, running_queue: Any ) -> threading.Thread:
    """
    Start the background consumer thread for producer-consumer pattern.
    
    Requires:
        - todo_queue is a TodoFifoQueue with condition variable support
        - running_queue is a RunningFifoQueue with _process_job method
        
    Ensures:
        - Consumer thread runs as daemon (dies with main process)
        - Uses condition.wait() instead of polling for efficiency
        - Gracefully handles shutdown via consumer_running flag
        
    Args:
        todo_queue: TodoFifoQueue instance (producer)
        running_queue: RunningFifoQueue instance (consumer processor)
        
    Returns:
        threading.Thread: The started consumer thread
        
    Raises:
        None (exceptions handled within thread)
    """
    
    def consumer_worker():
        """Main consumer worker function that processes jobs"""
        print( "[CONSUMER] Starting queue consumer thread..." )
        todo_queue.consumer_running = True
        
        while todo_queue.consumer_running:
            try:
                # Wait for jobs using condition variable (no polling!)
                with todo_queue.condition:
                    while todo_queue.is_empty() and todo_queue.consumer_running:
                        if todo_queue.debug:
                            print( "[CONSUMER] Waiting for jobs..." )
                        todo_queue.condition.wait()  # Sleep until notified
                    
                    if not todo_queue.consumer_running:
                        break
                    
                    # Get job while holding the lock
                    job = todo_queue.pop()  # Auto-emits 'todo_update'
                
                if job:
                    if todo_queue.debug:
                        # Phase 2: Direct attribute access - Protocol guarantees this exists
                        print( f"[CONSUMER] Processing job: {job.last_question_asked}" )

                    # Emit job state transition (todo -> run) before moving to running queue
                    # Phase 2: Direct attribute access - Protocol guarantees these exist
                    job_id = job.id_hash
                    if hasattr( running_queue, 'websocket_mgr' ):
                        user_id = running_queue.user_job_tracker.get_user_for_job( job_id ) if hasattr( running_queue, 'user_job_tracker' ) else None
                        # Phase 6.1: Include card-rendering metadata for client-side card creation
                        metadata = {
                            'question_text' : job.last_question_asked,
                            'agent_type'    : job.job_type,
                            'timestamp'     : job.created_date,
                            'started_at'    : datetime.now().isoformat()
                        }
                        emit_job_state_transition( running_queue.websocket_mgr, job_id, 'todo', 'run', user_id, metadata )

                    # Move to running queue
                    running_queue.push( job )  # Auto-emits 'run_update'

                    # Process the job (new method we'll add to RunningFifoQueue)
                    if hasattr( running_queue, '_process_job' ):
                        running_queue._process_job( job )
                    else:
                        print( "[CONSUMER] Warning: RunningFifoQueue missing _process_job method" )
                        # Fallback: just leave it in running queue for now
                        time.sleep( 0.1 )
                    
            except Exception as e:
                print( f"[CONSUMER] Error in consumer thread: {e}" )
                if todo_queue.debug:
                    import traceback
                    traceback.print_exc()
                # Continue running even after errors
                time.sleep( 1.0 )
        
        print( "[CONSUMER] Consumer thread shutting down..." )
    
    # Start as daemon thread (dies when main process exits)
    consumer_thread = threading.Thread( target=consumer_worker, daemon=True, name="TodoConsumerThread" )
    consumer_thread.start()
    
    print( f"[CONSUMER] Consumer thread started: {consumer_thread.name}" )
    return consumer_thread


def quick_smoke_test():
    """Quick smoke test for consumer thread functionality"""
    from unittest.mock import Mock
    import time
    
    du.print_banner( "Queue Consumer Thread Smoke Test" )
    
    try:
        # Create mock queues
        mock_todo_queue = Mock()
        mock_todo_queue.debug = True
        mock_todo_queue.consumer_running = True  # Start as True
        mock_todo_queue.condition = threading.Condition()
        mock_todo_queue.is_empty.return_value = True
        
        mock_running_queue = Mock()
        
        print( "✓ Testing consumer thread startup..." )
        
        # Start thread
        thread = start_todo_producer_run_consumer_thread( mock_todo_queue, mock_running_queue )
        
        # Give thread time to start
        time.sleep( 0.1 )
        assert thread.is_alive() == True, "Thread should be running"
        
        # Now stop it
        with mock_todo_queue.condition:
            mock_todo_queue.consumer_running = False
            mock_todo_queue.condition.notify()
        
        # Give thread time to exit
        thread.join( timeout=1.0 )
        assert thread.is_alive() == False, "Thread should have exited after consumer_running=False"
        print( "✓ Consumer thread lifecycle working!" )
        
        print( "✓ Consumer thread smoke test passed!" )
        
    except Exception as e:
        print( f"✗ Consumer thread smoke test failed: {e}" )
        raise


if __name__ == "__main__":
    quick_smoke_test()