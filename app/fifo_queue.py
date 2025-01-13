from collections import OrderedDict


class FifoQueue:
    def __init__( self ):
        
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
        
    def pop_blocking_object( self ):
        blocking_object = self._blocking_object
        self._blocking_object = None
        self._accepting_jobs = True
        return blocking_object
    
    def push_blocking_object( self, blocking_object ):
        self._blocking_object = blocking_object
        self._accepting_jobs = False
        
    def is_in_focus_mode( self ):
        return self._focus_mode
    
    def is_accepting_jobs( self ):
        return self._accepting_jobs
    
    # def set_accepting_jobs( self, accepting_jobs ):
    #     self.accepting_jobs = accepting_jobs
    
    def push( self, item ):
        
        self.queue_list.append( item )
        self.queue_dict[ item.id_hash ] = item
        self.push_counter += 1
    
    def get_push_counter( self ):
        return self.push_counter
    
    def pop( self ):
        if not self.is_empty():
            # Remove from ID_hash first
            del self.queue_dict[ self.queue_list[ 0 ].id_hash ]
            return self.queue_list.pop( 0 )
    
    def head( self ):
        if not self.is_empty():
            return self.queue_list[ 0 ]
        else:
            return None
    
    def get_by_id_hash( self, id_hash ):
        
        return self.queue_dict[ id_hash ]
    
    def delete_by_id_hash( self, id_hash ):
        
        del self.queue_dict[ id_hash ]
        size_before = self.size()
        self.queue_list = list( self.queue_dict.values() )
        size_after = self.size()
        
        if size_after < size_before:
            print( f"Deleted {size_before - size_after} items from queue" )
        else:
            print( "ERROR: Could not delete by id_hash" )
        
    def is_empty( self ):
        return len( self.queue_list ) == 0
    
    def size( self ):
        return len( self.queue_list )
    
    def has_changed( self ):
        if self.size() != self.last_queue_size:
            self.last_queue_size = self.size()
            return True
        else:
            return False
