from collections import OrderedDict
from typing import Any, Optional


class FifoQueue:
    """
    First-In-First-Out queue implementation with dictionary lookup.
    
    This class provides a FIFO queue with additional features for tracking
    blocking objects, focus mode, and job acceptance states. Items are
    stored in both a list (for ordering) and dictionary (for O(1) lookup).
    """
    
    def __init__( self ) -> None:
        """
        Initialize an empty FIFO queue.
        
        Requires:
            - None
            
        Ensures:
            - Creates empty queue_list and queue_dict
            - Initializes push_counter to 0
            - Sets accepting_jobs to True
            - Sets focus_mode to True
            - Sets blocking_object to None
            
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
            return self.queue_list.pop( 0 )
    
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
    
    def delete_by_id_hash( self, id_hash: str ) -> None:
        """
        Delete an item by its ID hash.
        
        Requires:
            - id_hash is a string
            
        Ensures:
            - Item is removed from queue_dict
            - queue_list is rebuilt from remaining items
            - Prints status message about deletion
            
        Raises:
            - KeyError if id_hash not found
        """
        
        del self.queue_dict[ id_hash ]
        size_before = self.size()
        self.queue_list = list( self.queue_dict.values() )
        size_after = self.size()
        
        if size_after < size_before:
            print( f"Deleted {size_before - size_after} items from queue" )
        else:
            print( "ERROR: Could not delete by id_hash" )
        
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
