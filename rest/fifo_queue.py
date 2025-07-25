from collections import OrderedDict
from typing import Any, Optional


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
    
    def _emit_speech( self, msg: str, websocket_id: str = None ) -> None:
        """
        Helper method to emit speech through the callback.
        
        Requires:
            - Subclass has self.emit_speech_callback attribute
            
        Ensures:
            - Calls emit_speech_callback if available
            - Handles exceptions gracefully
            
        Args:
            msg: The message to convert to speech
            websocket_id: The websocket to send to (None means broadcast to all)
            
        Raises:
            - None (exceptions handled internally)
        """
        if hasattr( self, 'emit_speech_callback' ) and self.emit_speech_callback:
            try:
                self.emit_speech_callback( msg, websocket_id )
            except Exception as e:
                print( f"[ERROR] emit_speech_callback failed: {e}" )
    
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
                event_name = f"{self.queue_name}_update"
                data = { 'value': self.size() }
                self.websocket_mgr.emit( event_name, data )
                if hasattr( self, 'debug' ) and self.debug:
                    print( f"[QUEUE] Auto-emitted {event_name}: {data}" )
            except Exception as e:
                print( f"[ERROR] _emit_queue_update failed: {e}" )
