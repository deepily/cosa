from cosa.rest.fifo_queue import FifoQueue
from cosa.memory.input_and_output_table import InputAndOutputTable
import cosa.utils.util as du
from datetime import datetime
from typing import Optional, Any, Dict
import uuid


class NotificationItem:
    """
    Simple notification item for queue storage.
    Replaces SolutionSnapshot for lightweight notification management.
    """
    
    def __init__( self, message: str, type: str = "task", priority: str = "medium", 
                 source: str = "claude_code", user_id: Optional[str] = None ) -> None:
        """
        Initialize a notification item.
        
        Requires:
            - message is a non-empty string
            - type is a valid notification type
            - priority is a valid priority level
            
        Ensures:
            - Creates unique id_hash for queue compatibility
            - Sets timestamp to current time
            - Initializes tracking fields
            
        Raises:
            - None
        """
        self.id_hash     = str( uuid.uuid4() )
        self.message     = message
        self.type        = type
        self.priority    = priority
        self.source      = source
        self.user_id     = user_id
        self.timestamp   = datetime.now().isoformat()
        self.played      = False
        self.play_count  = 0
        self.last_played = None
        
    def to_dict( self ) -> Dict[str, Any]:
        """Convert notification to dictionary for JSON serialization."""
        return {
            "id_hash"     : self.id_hash,
            "message"     : self.message,
            "type"        : self.type,
            "priority"    : self.priority,
            "source"      : self.source,
            "user_id"     : self.user_id,
            "timestamp"   : self.timestamp,
            "played"      : self.played,
            "play_count"  : self.play_count,
            "last_played" : self.last_played
        }


class NotificationFifoQueue( FifoQueue ):
    """
    FIFO queue for Claude Code notifications with priority handling and io_tbl logging.
    
    Inherits auto-emission of WebSocket events from parent FifoQueue.
    Logs all notifications to InputAndOutputTable for persistence and analytics.
    """
    
    def __init__( self, websocket_mgr: Optional[Any] = None, emit_enabled: bool = True, 
                 debug: bool = False, verbose: bool = False ) -> None:
        """
        Initialize notification queue with io_tbl logging.
        
        Requires:
            - websocket_mgr is a valid WebSocketManager instance or None
            - emit_enabled is boolean to control auto-emission
            
        Ensures:
            - Inherits FifoQueue with 'notification' queue name
            - Initializes InputAndOutputTable for logging
            - Sets debug and verbose flags
            
        Raises:
            - Database connection errors propagated from InputAndOutputTable
        """
        super().__init__(
            websocket_mgr=websocket_mgr,
            queue_name="notification",  # Will auto-emit 'notification_update' events
            emit_enabled=emit_enabled
        )
        
        self.debug           = debug
        self.verbose         = verbose
        self._io_tbl         = InputAndOutputTable( debug=debug, verbose=verbose )
        
        if self.debug:
            print( f"NotificationFifoQueue initialized with io_tbl logging" )
    
    def push( self, notification: NotificationItem ) -> None:
        """
        Override parent's push to emit enhanced notification data.
        Prevents double emission while including full notification details.
        
        Requires:
            - notification is a valid NotificationItem instance
            
        Ensures:
            - Adds notification to queue
            - Emits single WebSocket event with full notification data
            - Increments push counter
            
        Raises:
            - None
        """
        # Add to queue data structures
        self.queue_list.append( notification )
        self.queue_dict[ notification.id_hash ] = notification
        self.push_counter += 1
        
        # Emit enhanced notification_update
        if self.websocket_mgr and self.emit_enabled:
            event_data = {
                'queue_name': 'notification',
                'value': self.size(),
                'notification': notification.to_dict()
            }
            
            if notification.user_id:
                # Targeted notification - send only to specific user
                self.websocket_mgr.emit_to_user_sync( notification.user_id, 'notification_update', event_data )
                if self.debug:
                    print( f"Emitted notification to user: {notification.user_id}" )
            else:
                # Broadcast notification - send to all connected clients
                self.websocket_mgr.emit( 'notification_update', event_data )
                if self.debug:
                    print( f"Broadcast notification to all users" )
        
        if self.debug:
            print( f"Pushed notification {notification.id_hash} with enhanced WebSocket emission" )
    
    def push_notification( self, message: str, type: str = "task", priority: str = "medium", 
                         source: str = "claude_code", user_id: Optional[str] = None ) -> NotificationItem:
        """
        Push a notification with priority handling and io_tbl logging.
        
        Requires:
            - message is non-empty string
            - type is valid notification type (task, progress, alert, custom)
            - priority is valid priority level (urgent, high, medium, low)
            
        Ensures:
            - Creates NotificationItem with unique ID
            - Inserts at correct position based on priority
            - Logs to InputAndOutputTable for persistence
            - Auto-emits WebSocket event via parent class
            
        Raises:
            - None (handles errors gracefully)
        """
        # Create notification item
        notification = NotificationItem(
            message=message,
            type=type,
            priority=priority,
            source=source,
            user_id=user_id
        )
        
        # Priority handling - urgent/high go to front, but after other urgent/high
        if priority in [ "urgent", "high" ]:
            # Find insertion point after other urgent/high messages
            insert_idx = 0
            for idx, item in enumerate( self.queue_list ):
                if hasattr( item, 'priority' ) and item.priority not in [ "urgent", "high" ]:
                    break
                insert_idx = idx + 1
            
            # Manual insertion for priority placement
            self.queue_list.insert( insert_idx, notification )
            self.queue_dict[ notification.id_hash ] = notification
            self.push_counter += 1
            
            # Emit enhanced notification_update (same as push method)
            if self.websocket_mgr and self.emit_enabled:
                event_data = {
                    'queue_name': 'notification',
                    'value': self.size(),
                    'notification': notification.to_dict()
                }
                
                if notification.user_id:
                    # Targeted notification - send only to specific user
                    self.websocket_mgr.emit_to_user_sync( notification.user_id, 'notification_update', event_data )
                    if self.debug:
                        print( f"Emitted priority notification to user: {notification.user_id}" )
                else:
                    # Broadcast notification - send to all connected clients
                    self.websocket_mgr.emit( 'notification_update', event_data )
                    if self.debug:
                        print( f"Broadcast priority notification to all users" )
        else:
            # Normal priority goes to end (use our overridden push method)
            self.push( notification )
        
        # Log to io_tbl for persistence and analytics
        self._log_to_io_tbl( notification )
        
        if self.debug:
            print( f"Notification queued: {type}/{priority} - {message[:50]}..." )
        
        return notification
    
    def mark_played( self, notification_id: str ) -> bool:
        """
        Mark a notification as played and update io_tbl.
        
        Requires:
            - notification_id is valid UUID string
            
        Ensures:
            - Updates played status and play count
            - Logs playback event to io_tbl
            - Emits WebSocket update
            
        Raises:
            - None
        """
        # Find notification in queue
        notification = self.queue_dict.get( notification_id )
        if not notification:
            if self.debug:
                print( f"Notification {notification_id} not found for marking as played" )
            return False
        
        # Update playback tracking
        notification.played      = True
        notification.play_count += 1
        notification.last_played = datetime.now().isoformat()
        
        # Log playback event to io_tbl
        self._log_playback_to_io_tbl( notification )
        
        # Emit update to sync client state
        self._emit_queue_update()
        
        if self.debug:
            print( f"Marked notification {notification_id} as played (count: {notification.play_count})" )
        
        return True
    
    def get_next_unplayed( self, user_id: Optional[str] = None ) -> Optional[NotificationItem]:
        """
        Get the next notification that hasn't been played yet.
        
        Requires:
            - user_id is valid string or None for all users
            
        Ensures:
            - Returns first unplayed notification for user
            - Returns None if no unplayed notifications
            
        Raises:
            - None
        """
        for item in self.queue_list:
            # Check user filter
            if user_id and hasattr( item, 'user_id' ) and item.user_id != user_id:
                continue
            
            # Check if unplayed
            if hasattr( item, 'played' ) and not item.played:
                return item
        
        return None
    
    def get_user_notifications( self, user_id: str, include_played: bool = True ) -> list[NotificationItem]:
        """
        Get notifications for a specific user.
        
        Requires:
            - user_id is non-empty string
            - include_played is boolean
            
        Ensures:
            - Returns list of user's notifications
            - Filters by played status if requested
            
        Raises:
            - None
        """
        notifications = []
        for item in self.queue_list:
            if hasattr( item, 'user_id' ) and item.user_id == user_id:
                if include_played or not getattr( item, 'played', False ):
                    notifications.append( item )
        
        return notifications
    
    def _log_to_io_tbl( self, notification: NotificationItem ) -> None:
        """
        Log notification to InputAndOutputTable for persistence.
        
        Requires:
            - notification is valid NotificationItem
            
        Ensures:
            - Inserts row in io_tbl with notification data
            - Uses standardized format for notifications
            
        Raises:
            - None (handles errors gracefully)
        """
        try:
            # Format notification data for io_tbl
            input_data = f"NOTIFICATION: {notification.type}/{notification.priority}"
            output_data = notification.message
            
            # Insert into io_tbl with notification metadata
            self._io_tbl.insert_io_row(
                date=du.get_current_date(),
                time=du.get_current_time( include_timezone=False ),
                input_type="notification",
                input=input_data,
                output_raw=output_data,
                output_final=f"[{notification.source}] {output_data}",
                async_embedding=True  # Generate embeddings async for performance
            )
            
            if self.verbose:
                print( f"Logged notification {notification.id_hash} to io_tbl" )
                
        except Exception as e:
            if self.debug:
                print( f"Failed to log notification to io_tbl: {e}" )
    
    def _log_playback_to_io_tbl( self, notification: NotificationItem ) -> None:
        """
        Log notification playback event to io_tbl.
        
        Requires:
            - notification is valid NotificationItem with playback data
            
        Ensures:
            - Inserts playback event in io_tbl
            - Tracks user interaction with notifications
            
        Raises:
            - None (handles errors gracefully)
        """
        try:
            # Format playback event for io_tbl
            input_data = f"PLAYBACK: {notification.id_hash}"
            output_data = f"Played notification (count: {notification.play_count})"
            
            # Insert playback event
            self._io_tbl.insert_io_row(
                date=du.get_current_date(),
                time=du.get_current_time( include_timezone=False ),
                input_type="notification_playback",
                input=input_data,
                output_raw=output_data,
                output_final=f"User played: {notification.message[:100]}...",
                async_embedding=False  # Playback events don't need embeddings
            )
            
            if self.verbose:
                print( f"Logged playback event for {notification.id_hash} to io_tbl" )
                
        except Exception as e:
            if self.debug:
                print( f"Failed to log playback event to io_tbl: {e}" )


def quick_smoke_test():
    """
    Quick smoke test for NotificationFifoQueue.
    Tests complete workflow with priority handling and io_tbl logging.
    """
    import cosa.utils.util as du
    
    du.print_banner( "NotificationFifoQueue Smoke Test" )
    
    try:
        # Test queue initialization
        print( "✓ Testing queue initialization..." )
        queue = NotificationFifoQueue( debug=True, verbose=True )
        
        # Test adding notifications with different priorities
        print( "✓ Testing notification addition with priorities..." )
        
        # Add normal priority notification
        notif1 = queue.push_notification(
            message="Normal priority test message",
            type="task",
            priority="medium",
            user_id="test_user"
        )
        
        # Add high priority notification (should go to front)
        notif2 = queue.push_notification(
            message="High priority urgent message",
            type="alert", 
            priority="high",
            user_id="test_user"
        )
        
        # Add another normal priority
        notif3 = queue.push_notification(
            message="Another normal message",
            type="progress",
            priority="medium",
            user_id="test_user"
        )
        
        # Verify queue order (high priority should be first)
        assert queue.size() == 3, f"Expected 3 items, got {queue.size()}"
        
        first_item = queue.head()
        assert first_item.priority == "high", f"Expected high priority first, got {first_item.priority}"
        
        print( f"✓ Queue size: {queue.size()}, first item priority: {first_item.priority}" )
        
        # Test marking as played
        print( "✓ Testing playback tracking..." )
        success = queue.mark_played( notif2.id_hash )
        assert success, "Failed to mark notification as played"
        assert notif2.played == True, "Notification not marked as played"
        assert notif2.play_count == 1, f"Expected play_count 1, got {notif2.play_count}"
        
        # Test getting unplayed notifications
        print( "✓ Testing unplayed notification retrieval..." )
        unplayed = queue.get_next_unplayed( "test_user" )
        assert unplayed is not None, "Should have unplayed notifications"
        assert unplayed.played == False, "Retrieved notification should be unplayed"
        
        # Test user filtering
        print( "✓ Testing user notification filtering..." )
        user_notifs = queue.get_user_notifications( "test_user", include_played=True )
        assert len( user_notifs ) == 3, f"Expected 3 user notifications, got {len(user_notifs)}"
        
        user_unplayed = queue.get_user_notifications( "test_user", include_played=False )
        assert len( user_unplayed ) == 2, f"Expected 2 unplayed notifications, got {len(user_unplayed)}"
        
        print( "✓ All tests passed! NotificationFifoQueue working correctly." )
        
    except Exception as e:
        print( f"✗ Smoke test failed: {e}" )
        raise


if __name__ == "__main__":
    quick_smoke_test()