"""
Queue utility functions for state transition events.

These functions are standalone because state transitions happen in disparate
locations (job submission, queue consumer, running queue) - not behaviors
inherently owned by any single queue class.
"""
from datetime import datetime
from typing import Any, Optional


def emit_job_state_transition(
    websocket_mgr: Any,
    job_id: str,
    from_queue: str,
    to_queue: str,
    user_id: str = None,
    metadata: dict = None
) -> None:
    """
    Emit job state transition event with optional completion metadata.

    Requires:
        - websocket_mgr is not None (or function returns early)
        - job_id is a non-empty string
        - from_queue and to_queue are valid queue names (pending, todo, run, done, dead)

    Ensures:
        - Emits 'job_state_transition' event to WebSocket
        - Targets specific user if user_id provided
        - Falls back to broadcast if no user_id
        - Handles exceptions gracefully

    Args:
        websocket_mgr: WebSocket manager instance with emit() and emit_to_user_sync() methods
        job_id: Unique identifier for the job
        from_queue: Source queue name (pending, todo, run, done, dead)
        to_queue: Target queue name (pending, todo, run, done, dead)
        user_id: Optional user ID for targeted emission
        metadata: Optional dict with completion data (response_text, abstract, report_link, cost_summary, error)

    Raises:
        - None (exceptions handled internally)
    """
    if not websocket_mgr:
        return

    data = {
        'job_id'     : job_id,
        'from_queue' : from_queue,
        'to_queue'   : to_queue,
        'timestamp'  : datetime.now().isoformat()
    }

    if metadata:
        data[ 'metadata' ] = metadata

    try:
        if user_id:
            websocket_mgr.emit_to_user_sync( user_id, 'job_state_transition', data )
        else:
            websocket_mgr.emit( 'job_state_transition', data )
    except Exception as e:
        print( f"[ERROR] emit_job_state_transition failed: {e}" )


def quick_smoke_test():
    """
    Quick smoke test for queue_util functions.
    """
    import cosa.utils.util as du

    du.print_banner( "Queue Utility Smoke Test", prepend_nl=True )

    try:
        # Test 1: Import verification
        print( "Testing module import..." )
        from cosa.rest.queue_util import emit_job_state_transition
        print( "✓ emit_job_state_transition imported successfully" )

        # Test 2: Function with None websocket_mgr (should return early)
        print( "Testing with None websocket_mgr..." )
        emit_job_state_transition( None, "test-job-123", "todo", "run" )
        print( "✓ Gracefully handled None websocket_mgr" )

        # Test 3: Mock WebSocket manager
        print( "Testing with mock websocket_mgr..." )

        class MockWebSocketMgr:
            def __init__( self ):
                self.emitted_events = []
                self.user_events = []

            def emit( self, event_name, data ):
                self.emitted_events.append( ( event_name, data ) )

            def emit_to_user_sync( self, user_id, event_name, data ):
                self.user_events.append( ( user_id, event_name, data ) )

        mock_ws = MockWebSocketMgr()

        # Test broadcast emission
        emit_job_state_transition( mock_ws, "job-456", "pending", "todo" )
        assert len( mock_ws.emitted_events ) == 1, "Expected 1 broadcast event"
        event_name, data = mock_ws.emitted_events[ 0 ]
        assert event_name == "job_state_transition", f"Expected 'job_state_transition', got '{event_name}'"
        assert data[ "job_id" ] == "job-456", f"Expected job_id 'job-456', got '{data[ 'job_id' ]}'"
        assert data[ "from_queue" ] == "pending", f"Expected from_queue 'pending', got '{data[ 'from_queue' ]}'"
        assert data[ "to_queue" ] == "todo", f"Expected to_queue 'todo', got '{data[ 'to_queue' ]}'"
        print( "✓ Broadcast emission working" )

        # Test user-targeted emission
        emit_job_state_transition( mock_ws, "job-789", "run", "done", user_id="user-123" )
        assert len( mock_ws.user_events ) == 1, "Expected 1 user-targeted event"
        user_id, event_name, data = mock_ws.user_events[ 0 ]
        assert user_id == "user-123", f"Expected user_id 'user-123', got '{user_id}'"
        assert event_name == "job_state_transition", f"Expected 'job_state_transition', got '{event_name}'"
        print( "✓ User-targeted emission working" )

        # Test with metadata
        mock_ws2 = MockWebSocketMgr()
        metadata = {
            'response_text' : 'Test response',
            'question_text' : 'What is 2+2?',
            'agent_type'    : 'MathAgent'
        }
        emit_job_state_transition( mock_ws2, "job-999", "run", "done", metadata=metadata )
        assert len( mock_ws2.emitted_events ) == 1, "Expected 1 event with metadata"
        _, data = mock_ws2.emitted_events[ 0 ]
        assert "metadata" in data, "Expected metadata in event data"
        assert data[ "metadata" ][ "response_text" ] == "Test response", "Metadata content mismatch"
        print( "✓ Metadata inclusion working" )

        print( "\n✓ Queue utility smoke test completed successfully!" )

    except Exception as e:
        print( f"✗ Error during queue utility testing: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
