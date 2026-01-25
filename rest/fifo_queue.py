from collections import OrderedDict
from typing import Any, Optional
import re
from cosa.rest.queue_extensions import user_job_tracker

# Notification service imports for TTS migration (Session 97)
from cosa.cli.notify_user_async import notify_user_async
from cosa.cli.notification_models import (
    AsyncNotificationRequest,
    NotificationPriority
)


class FifoQueue:
    """
    First-In-First-Out queue implementation with dictionary lookup.
    
    This class provides a FIFO queue with additional features for tracking
    blocking objects, focus mode, and job acceptance states. Items are
    stored in both a list (for ordering) and dictionary (for O(1) lookup).
    """
    
    def __init__( self, websocket_mgr: Optional[Any] = None, queue_name: Optional[str] = None, emit_enabled: bool = True ) -> None:
        """
        Initialize an empty FIFO queue with optional auto-emission capabilities.
        
        Requires:
            - websocket_mgr is a valid WebSocketManager instance or None
            - queue_name is a valid string for emission events or None
            - emit_enabled is a boolean to control auto-emission
            
        Ensures:
            - Creates empty queue_list and queue_dict
            - Initializes push_counter to 0
            - Sets accepting_jobs to True
            - Sets focus_mode to True
            - Sets blocking_object to None
            - Configures auto-emission if websocket_mgr and queue_name provided
            
        Raises:
            - None
        """
        
        self.queue_list      = [ ]
        self.queue_dict      = OrderedDict()
        self.push_counter    = 0
        self.last_queue_size = 0
        # used to track if the queue is accepting jobs or not, especially important when we're running in focus versus multi tasking mode
        self._accepting_jobs  = True
        # used to track if the queue is in focus mode or not, in the future. We're going to have to tackle multitasking mode.
        self._focus_mode      = True
        # used to track if this queue contains a blocking object
        self._blocking_object = None
        
        # Auto-emission configuration for client-server state synchronization
        self.websocket_mgr   = websocket_mgr
        self.queue_name      = queue_name
        self.emit_enabled    = emit_enabled
        
        # User job tracking singleton for user-based routing
        self.user_job_tracker = user_job_tracker
        
    def pop_blocking_object( self ) -> Optional[Any]:
        """
        Remove and return the blocking object.
        
        Requires:
            - None
            
        Ensures:
            - Returns the blocking object (may be None)
            - Sets _blocking_object to None
            - Sets _accepting_jobs to True
            
        Raises:
            - None
        """
        blocking_object = self._blocking_object
        self._blocking_object = None
        self._accepting_jobs = True
        return blocking_object
    
    def push_blocking_object( self, blocking_object: Any ) -> None:
        """
        Set a blocking object and stop accepting new jobs.
        
        Requires:
            - blocking_object can be any object
            
        Ensures:
            - Sets _blocking_object to the provided object
            - Sets _accepting_jobs to False
            
        Raises:
            - None
        """
        self._blocking_object = blocking_object
        self._accepting_jobs = False
        
    def is_in_focus_mode( self ) -> bool:
        """
        Check if the queue is in focus mode.
        
        Requires:
            - None
            
        Ensures:
            - Returns current focus mode state
            
        Raises:
            - None
        """
        return self._focus_mode
    
    def is_accepting_jobs( self ) -> bool:
        """
        Check if the queue is accepting new jobs.
        
        Requires:
            - None
            
        Ensures:
            - Returns current job acceptance state
            
        Raises:
            - None
        """
        return self._accepting_jobs
    
    # def set_accepting_jobs( self, accepting_jobs ):
    #     self.accepting_jobs = accepting_jobs
    
    def push( self, item: Any ) -> None:
        """
        Add an item to the end of the queue.
        
        Requires:
            - item must have an 'id_hash' attribute
            
        Ensures:
            - Item is added to end of queue_list
            - Item is added to queue_dict with id_hash as key
            - push_counter is incremented
            
        Raises:
            - AttributeError if item doesn't have id_hash
        """
        
        self.queue_list.append( item )
        self.queue_dict[ item.id_hash ] = item
        self.push_counter += 1
        self._emit_queue_update()
    
    def get_push_counter( self ) -> int:
        """
        Get the total number of items pushed to the queue.
        
        Requires:
            - None
            
        Ensures:
            - Returns current push counter value
            
        Raises:
            - None
        """
        return self.push_counter
    
    def pop( self ) -> Optional[Any]:
        """
        Remove and return the first item from the queue.
        
        Requires:
            - None
            
        Ensures:
            - Returns first item if queue not empty
            - Removes item from both queue_list and queue_dict
            - Returns None if queue is empty
            
        Raises:
            - None
        """
        if not self.is_empty():
            # Remove from ID_hash first
            del self.queue_dict[ self.queue_list[ 0 ].id_hash ]
            result = self.queue_list.pop( 0 )
            self._emit_queue_update()
            return result
    
    def head( self ) -> Optional[Any]:
        """
        Get the first item without removing it.
        
        Requires:
            - None
            
        Ensures:
            - Returns first item if queue not empty
            - Queue remains unchanged
            - Returns None if queue is empty
            
        Raises:
            - None
        """
        if not self.is_empty():
            return self.queue_list[ 0 ]
        else:
            return None
    
    def get_by_id_hash( self, id_hash: str ) -> Any:
        """
        Get an item by its ID hash.
        
        Requires:
            - id_hash exists in queue_dict
            
        Ensures:
            - Returns the item with matching id_hash
            
        Raises:
            - KeyError if id_hash not found
        """
        
        return self.queue_dict[ id_hash ]
    
    def delete_by_id_hash( self, id_hash: str ) -> bool:
        """
        Delete an item by its ID hash.
        
        Requires:
            - id_hash is a string
            
        Ensures:
            - Item is removed from queue_dict if found
            - queue_list is rebuilt from remaining items
            - Prints status message about deletion
            - Returns True if deletion successful, False otherwise
            
        Returns:
            - bool: True if item was found and deleted, False if not found
        """
        try:
            # Check if item exists before attempting deletion
            if id_hash not in self.queue_dict:
                print( f"ERROR: Could not delete by id_hash - item {id_hash} not found" )
                return False
            
            size_before = self.size()
            del self.queue_dict[ id_hash ]
            self.queue_list = list( self.queue_dict.values() )
            size_after = self.size()
            
            if size_after < size_before:
                print( f"Deleted {size_before - size_after} items from queue" )
                self._emit_queue_update()
                return True
            else:
                print( "ERROR: Could not delete by id_hash - size didn't change" )
                return False
                
        except Exception as e:
            print( f"ERROR: Exception during delete_by_id_hash: {e}" )
            return False
        
    def is_empty( self ) -> bool:
        """
        Check if the queue is empty.
        
        Requires:
            - None
            
        Ensures:
            - Returns True if queue has no items
            - Returns False if queue has items
            
        Raises:
            - None
        """
        return len( self.queue_list ) == 0
    
    def size( self ) -> int:
        """
        Get the number of items in the queue.
        
        Requires:
            - None
            
        Ensures:
            - Returns count of items in queue
            
        Raises:
            - None
        """
        return len( self.queue_list )
    
    def has_changed( self ) -> bool:
        """
        Check if the queue size has changed since last check.
        
        Requires:
            - None
            
        Ensures:
            - Returns True if size differs from last_queue_size
            - Updates last_queue_size to current size
            - Returns False if size unchanged
            
        Raises:
            - None
        """
        if self.size() != self.last_queue_size:
            self.last_queue_size = self.size()
            return True
        else:
            return False
    
    def clear( self ) -> None:
        """
        Clear all items from the queue and emit update.
        
        Requires:
            - None
            
        Ensures:
            - Empties both queue_list and queue_dict
            - Resets push_counter to 0
            - Clears blocking_object to None
            - Resets accepting_jobs to True
            - Emits queue update via WebSocket if configured
            
        Raises:
            - None
        """
        self.queue_list.clear()
        self.queue_dict.clear()
        self.push_counter = 0
        self._blocking_object = None
        self._accepting_jobs = True
        self._emit_queue_update()
    
    def get_html_list( self, descending: bool = False ) -> list[str]:
        """
        Generate HTML list from queue items.
        
        Requires:
            - Each item in queue_list has get_html() method
            
        Ensures:
            - Returns list of HTML strings from queue items
            - Reverses order if descending=True
            
        Args:
            descending: Whether to reverse the list order
            
        Returns:
            list[str]: HTML representations of queue items
            
        Raises:
            - AttributeError if items don't have get_html() method
        """
        html_list = []
        for job in self.queue_list:
            html_list.append( job.get_html() )
        
        if descending:
            html_list.reverse()
        
        return html_list

    def get_jobs_for_user( self, user_id: str ) -> list[Any]:
        """
        Get raw job objects for specific user (NO authorization, NO formatting).

        Pure data access method - performs NO authorization checks.
        Authorization should be handled by calling code.

        Requires:
            - user_id is a valid user identifier string
            - UserJobTracker singleton is initialized

        Ensures:
            - Returns list of job objects matching user's job IDs
            - Returns empty list if user has no jobs
            - Returns raw job objects (NOT HTML formatted)
            - NO authorization checks performed

        Args:
            user_id: The user identifier to filter jobs by

        Returns:
            list[Any]: List of job objects belonging to the user

        Raises:
            - None (returns empty list for nonexistent users)
        """
        # Get job IDs associated with this user
        user_job_ids = self.user_job_tracker.get_jobs_for_user( user_id )

        # Filter queue_list to only include jobs matching user's job IDs
        filtered_jobs = [
            job for job in self.queue_list
            if hasattr( job, 'id_hash' ) and job.id_hash in user_job_ids
        ]

        return filtered_jobs

    def get_all_jobs( self ) -> list[Any]:
        """
        Get ALL raw job objects (NO authorization, NO formatting).

        Pure data access method - performs NO authorization checks.
        Authorization should be handled by calling code.

        Requires:
            - Queue is initialized

        Ensures:
            - Returns complete copy of queue_list
            - NO filtering by user
            - Returns raw job objects (NOT HTML formatted)
            - NO authorization checks performed

        Returns:
            list[Any]: Complete list of all job objects in queue

        Raises:
            - None
        """
        return self.queue_list.copy()

    # ========================================================================
    # NOTIFICATION SERVICE METHODS (Session 97 - TTS Migration)
    # Replacement for legacy _emit_speech WebSocket-based TTS
    # ========================================================================

    def _get_notification_job_id( self, job: Any ) -> Optional[str]:
        """
        Extract notification-compatible job_id from job object.

        Notification service expects job_id pattern ^[a-z]+-[a-f0-9]{8}$
        (e.g., 'dr-a1b2c3d4', 'mock-12345678').

        Requires:
            - job may have id_hash attribute

        Ensures:
            - Returns job_id if it matches notification service format
            - Returns None if no compatible format (falls back to sender routing)

        Args:
            job: Job object that may have id_hash attribute

        Returns:
            Optional[str]: Notification-compatible job_id or None
        """
        if not job:
            return None

        if hasattr( job, 'id_hash' ):
            id_hash = job.id_hash
            # Check if format matches notification service pattern
            if id_hash and re.match( r'^[a-z]+-[a-f0-9]{8}$', id_hash ):
                return id_hash

        return None

    def _get_target_user_email( self, job: Any ) -> str:
        """
        Get target user email from job metadata for notification routing.

        Requires:
            - job (if provided) may have user_email attribute or metadata dict

        Ensures:
            - Returns user email if available in job metadata
            - Falls back to default email if not found

        Args:
            job: Job object that may have user_email attribute

        Returns:
            str: Target user email for notification routing
        """
        if job:
            # Check for email stored directly on job (set during push)
            if hasattr( job, 'user_email' ) and job.user_email:
                return job.user_email

            # Check for email in metadata dict
            if hasattr( job, 'metadata' ) and isinstance( job.metadata, dict ):
                if 'user_email' in job.metadata:
                    return job.metadata[ 'user_email' ]

            # Try to resolve from user_job_tracker (legacy path)
            if hasattr( job, 'id_hash' ):
                user_id = self.user_job_tracker.get_user_for_job( job.id_hash )
                if user_id:
                    # For now, return user_id as fallback (may not be email)
                    return user_id

        # Fallback to default email
        return "ricardo.felipe.ruiz@gmail.com"

    def _notify(
        self,
        msg: str,
        job: Any = None,
        priority: str = "high",
        notification_type: str = "task"
    ) -> None:
        """
        Send notification via notification service (replaces _emit_speech).

        Queue notifications default to:
        - priority="high" → message is spoken via TTS
        - suppress_ding=True → no notification sound (conversational flow)

        Requires:
            - msg is a non-empty string
            - job (if provided) has id_hash attribute

        Ensures:
            - Notification is sent to target user
            - If job_id available, routes to job card in UI
            - Message is spoken (high priority) without ding
            - Handles exceptions gracefully

        Args:
            msg: The message to send (will be spoken via TTS)
            job: Job object for context-based routing (optional)
            priority: Notification priority ('urgent', 'high', 'medium', 'low')
            notification_type: Type of notification ('task', 'progress', 'alert', 'custom')

        Raises:
            - None (exceptions handled internally)
        """
        try:
            request = AsyncNotificationRequest(
                message           = msg,
                notification_type = notification_type,
                priority          = priority,
                suppress_ding     = True,  # Queue notifications = TTS only, no ding
                target_user       = self._get_target_user_email( job ),
                job_id            = self._get_notification_job_id( job ),
                sender_id         = f"queue.{self.queue_name or 'unknown'}@lupin.deepily.ai"
            )
            notify_user_async( request )

            if hasattr( self, 'debug' ) and self.debug:
                print( f"[NOTIFY] Sent notification: {priority}/{notification_type} - {msg[:50]}..." )

        except Exception as e:
            print( f"[ERROR] _notify() failed: {e}" )

    # ============================================================================
    # DEPRECATED: Legacy _emit_speech implementation (Session 97)
    # Replaced by _notify() method using notification service
    # Keeping commented for reference during migration verification
    # TODO: Remove after migration verified stable (target: Session 100+)
    # ============================================================================
    # def _emit_speech( self, msg: str, user_id: str = None, websocket_id: str = None, job: Any = None ) -> None:
    #     """
    #     [DEPRECATED] Unified speech emission with smart routing.
    #
    #     Replaced by: _notify() method
    #     Reason: Migration to notification service for job_id routing, blocking queries, and suppress_ding
    #
    #     Priority: job context → user_id → websocket_id → broadcast
    #
    #     Requires:
    #         - Subclass has self.emit_speech_callback attribute
    #         - job parameter (if provided) has id_hash attribute
    #
    #     Ensures:
    #         - Determines user_id from job if available
    #         - Calls emit_speech_callback with proper parameters
    #         - Handles exceptions gracefully
    #
    #     Args:
    #         msg: The message to convert to speech
    #         user_id: Explicit user ID for routing (optional)
    #         websocket_id: WebSocket session ID for routing (optional)
    #         job: Job object containing id_hash for user lookup (optional)
    #
    #     Raises:
    #         - None (exceptions handled internally)
    #     """
    #     # Determine user_id from job context if available
    #     if job and hasattr( job, 'id_hash' ) and not user_id:
    #         user_id = self.user_job_tracker.get_user_for_job( job.id_hash )
    #         if user_id:
    #             print( f"[FIFO] Resolved user_id {user_id} from job {job.id_hash}" )
    #
    #     if hasattr( self, 'emit_speech_callback' ) and self.emit_speech_callback:
    #         try:
    #             # Use named parameters to ensure correct routing
    #             self.emit_speech_callback( msg, user_id=user_id, websocket_id=websocket_id )
    #         except Exception as e:
    #             print( f"[ERROR] emit_speech_callback failed: {e}" )

    def _emit_queue_update( self ) -> None:
        """
        Automatically emit queue state update via WebSocket.
        
        This method enables automatic client-server state synchronization
        by emitting queue size updates whenever the queue changes.
        
        Requires:
            - websocket_mgr, queue_name, and emit_enabled are configured
            
        Ensures:
            - Emits "<queue_name>_update" event with current queue size
            - Handles exceptions gracefully
            - Only emits if all requirements are met
            
        Raises:
            - None (exceptions handled internally)
        """
        if self.emit_enabled and self.websocket_mgr and self.queue_name:
            try:
                event_name = f"queue_{self.queue_name}_update"  # Fixed: Add "queue_" prefix
                data = { 'value': self.size() }
                self.websocket_mgr.emit( event_name, data )
                if hasattr( self, 'debug' ) and self.debug:
                    print( f"[QUEUE] Auto-emitted {event_name}: {data}" )
            except Exception as e:
                print( f"[ERROR] _emit_queue_update failed: {e}" )


def quick_smoke_test():
    """
    Critical smoke test for FIFO queue implementation - validates base queue functionality.
    
    This test is essential for v000 deprecation as fifo_queue.py is the foundation
    for all queue implementations in the REST system.
    """
    import cosa.utils.util as du
    
    du.print_banner( "FIFO Queue Smoke Test", prepend_nl=True )
    
    try:
        # Test 1: Basic class and method presence
        print( "Testing core FIFO queue components..." )
        expected_methods = [
            "push", "pop", "head", "get_by_id_hash", "delete_by_id_hash",
            "is_empty", "size", "has_changed", "clear", "get_html_list",
            "pop_blocking_object", "push_blocking_object", "is_in_focus_mode", "is_accepting_jobs"
        ]
        
        methods_found = 0
        for method_name in expected_methods:
            if hasattr( FifoQueue, method_name ):
                methods_found += 1
            else:
                print( f"⚠ Missing method: {method_name}" )
        
        if methods_found == len( expected_methods ):
            print( f"✓ All {len( expected_methods )} core FIFO methods present" )
        else:
            print( f"⚠ Only {methods_found}/{len( expected_methods )} FIFO methods present" )
        
        # Test 2: Critical dependency imports
        print( "Testing critical dependency imports..." )
        try:
            from collections import OrderedDict
            from typing import Any, Optional
            print( "✓ Standard library imports successful" )
        except ImportError as e:
            print( f"✗ Standard library imports failed: {e}" )
        
        try:
            from cosa.rest.queue_extensions import UserJobTracker
            print( "✓ Queue extensions import successful" )
        except ImportError as e:
            print( f"⚠ Queue extensions import failed: {e}" )
        
        # Test 3: Basic FIFO queue functionality
        print( "Testing basic FIFO queue functionality..." )
        try:
            # Create a test queue
            queue = FifoQueue()
            
            # Test initial state
            if queue.is_empty() and queue.size() == 0:
                print( "✓ Queue initialization working" )
            else:
                print( "✗ Queue initialization failed" )
            
            # Test state properties
            if queue.is_accepting_jobs() and queue.is_in_focus_mode():
                print( "✓ Initial state properties correct" )
            else:
                print( "⚠ Initial state properties may have issues" )
            
        except Exception as e:
            print( f"⚠ Basic queue functionality issues: {e}" )
        
        # Test 4: Queue operations with mock objects
        print( "Testing queue operations..." )
        try:
            # Create simple mock objects for testing
            class MockItem:
                def __init__( self, id_hash, name ):
                    self.id_hash = id_hash
                    self.name = name
                
                def get_html( self ):
                    return f"<li id='{self.id_hash}'>{self.name}</li>"
            
            queue = FifoQueue()
            
            # Test push operations
            item1 = MockItem( "hash1", "Item 1" )
            item2 = MockItem( "hash2", "Item 2" )
            
            queue.push( item1 )
            queue.push( item2 )
            
            if queue.size() == 2 and not queue.is_empty():
                print( "✓ Push operations working" )
            else:
                print( "✗ Push operations failed" )
            
            # Test head operation
            head_item = queue.head()
            if head_item and head_item.id_hash == "hash1":
                print( "✓ Head operation working" )
            else:
                print( "✗ Head operation failed" )
            
            # Test get_by_id_hash
            retrieved_item = queue.get_by_id_hash( "hash2" )
            if retrieved_item and retrieved_item.name == "Item 2":
                print( "✓ Get by ID hash working" )
            else:
                print( "✗ Get by ID hash failed" )
            
            # Test pop operation
            popped_item = queue.pop()
            if popped_item and popped_item.id_hash == "hash1" and queue.size() == 1:
                print( "✓ Pop operation working" )
            else:
                print( "✗ Pop operation failed" )
            
            # Test delete operation
            if queue.delete_by_id_hash( "hash2" ) and queue.is_empty():
                print( "✓ Delete by ID hash working" )
            else:
                print( "✗ Delete by ID hash failed" )
            
        except Exception as e:
            print( f"⚠ Queue operations testing issues: {e}" )
        
        # Test 5: Blocking object functionality
        print( "Testing blocking object functionality..." )
        try:
            queue = FifoQueue()
            test_blocking_obj = "blocking_test"
            
            # Test push blocking object
            queue.push_blocking_object( test_blocking_obj )
            
            if not queue.is_accepting_jobs():
                print( "✓ Push blocking object working" )
            else:
                print( "✗ Push blocking object failed" )
            
            # Test pop blocking object
            popped_blocking = queue.pop_blocking_object()
            
            if popped_blocking == test_blocking_obj and queue.is_accepting_jobs():
                print( "✓ Pop blocking object working" )
            else:
                print( "✗ Pop blocking object failed" )
            
        except Exception as e:
            print( f"⚠ Blocking object functionality issues: {e}" )
        
        # Test 6: HTML generation functionality
        print( "Testing HTML generation functionality..." )
        try:
            queue = FifoQueue()
            
            # Use mock items that have get_html method
            class MockHtmlItem:
                def __init__( self, id_hash, content ):
                    self.id_hash = id_hash
                    self.content = content
                
                def get_html( self ):
                    return f"<div id='{self.id_hash}'>{self.content}</div>"
            
            queue.push( MockHtmlItem( "html1", "Content 1" ) )
            queue.push( MockHtmlItem( "html2", "Content 2" ) )
            
            html_list = queue.get_html_list()
            
            if len( html_list ) == 2 and all( "<div" in item for item in html_list ):
                print( "✓ HTML generation working" )
            else:
                print( "⚠ HTML generation may have issues" )
            
        except Exception as e:
            print( f"⚠ HTML generation functionality issues: {e}" )
        
        # Test 7: WebSocket integration structure
        print( "Testing WebSocket integration structure..." )
        try:
            # Test queue with WebSocket manager (mock)
            mock_ws_mgr = type( 'MockWS', (), { 'emit': lambda self, event, data: None } )()
            queue = FifoQueue( websocket_mgr=mock_ws_mgr, queue_name="test_queue" )
            
            if hasattr( queue, 'websocket_mgr' ) and hasattr( queue, 'queue_name' ):
                print( "✓ WebSocket integration structure valid" )
            else:
                print( "⚠ WebSocket integration structure issues" )
                
        except Exception as e:
            print( f"⚠ WebSocket integration issues: {e}" )
        
        # Test 8: Critical v000 dependency scanning
        print( "\\n🔍 Scanning for v000 dependencies..." )
        
        # Scan the file for v000 patterns
        import inspect
        source_file = inspect.getfile( FifoQueue )
        
        v000_found = False
        v000_patterns = []
        
        with open( source_file, 'r' ) as f:
            content = f.read()
            
            # Split content and exclude smoke test function
            lines = content.split( '\\n' )
            in_smoke_test = False
            
            for i, line in enumerate( lines ):
                stripped_line = line.strip()
                
                # Track if we're in the smoke test function
                if "def quick_smoke_test" in line:
                    in_smoke_test = True
                    continue
                elif in_smoke_test and line.startswith( "def " ):
                    in_smoke_test = False
                elif in_smoke_test:
                    continue
                
                # Skip comments and docstrings
                if ( stripped_line.startswith( '#' ) or 
                     stripped_line.startswith( '"""' ) or
                     stripped_line.startswith( "'" ) ):
                    continue
                
                # Look for actual v000 code references
                if "v000" in stripped_line and any( pattern in stripped_line for pattern in [
                    "import", "from", "cosa.agents.v000", ".v000."
                ] ):
                    v000_found = True
                    v000_patterns.append( f"Line {i+1}: {stripped_line}" )
        
        if v000_found:
            print( "🚨 CRITICAL: v000 dependencies detected!" )
            print( "   Found v000 references:" )
            for pattern in v000_patterns[ :3 ]:  # Show first 3
                print( f"     • {pattern}" )
            if len( v000_patterns ) > 3:
                print( f"     ... and {len( v000_patterns ) - 3} more v000 references" )
            print( "   ⚠️  These dependencies MUST be resolved before v000 deprecation!" )
        else:
            print( "✅ EXCELLENT: No v000 dependencies found!" )
        
        # Test 9: Queue state consistency validation
        print( "\\nTesting queue state consistency..." )
        try:
            queue = FifoQueue()
            
            # Test state consistency between operations
            class TestItem:
                def __init__( self, id_hash ):
                    self.id_hash = id_hash
                
                def get_html( self ):
                    return f"<item>{self.id_hash}</item>"
            
            # Add multiple items and test consistency
            for i in range( 5 ):
                queue.push( TestItem( f"test_{i}" ) )
            
            # Check list/dict consistency
            list_size = len( queue.queue_list )
            dict_size = len( queue.queue_dict )
            reported_size = queue.size()
            
            if list_size == dict_size == reported_size == 5:
                print( "✓ Queue state consistency validated" )
            else:
                print( f"⚠ State inconsistency: list={list_size}, dict={dict_size}, size={reported_size}" )
            
        except Exception as e:
            print( f"⚠ Queue state consistency issues: {e}" )
    
    except Exception as e:
        print( f"✗ Error during FIFO queue testing: {e}" )
        import traceback
        traceback.print_exc()
    
    # Summary
    print( "\\n" + "="*60 )
    if v000_found:
        print( "🚨 CRITICAL ISSUE: FIFO queue has v000 dependencies!" )
        print( "   Status: NOT READY for v000 deprecation" )
        print( "   Priority: IMMEDIATE ACTION REQUIRED" )
        print( "   Risk Level: CRITICAL - All queue operations will break" )
    else:
        print( "✅ FIFO queue smoke test completed successfully!" )
        print( "   Status: Base queue implementation ready for v000 deprecation" )
        print( "   Risk Level: LOW" )
    
    print( "✓ FIFO queue smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()
