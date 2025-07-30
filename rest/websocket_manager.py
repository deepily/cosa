from fastapi import WebSocket
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
from cosa.config.configuration_manager import ConfigurationManager


class WebSocketManager:
    """
    Manages WebSocket connections and provides Socket.IO-like emit functionality.
    
    This class acts as an adapter between the COSA queue system (which expects
    Socket.IO) and FastAPI's native WebSocket implementation.
    """
    
    def __init__( self ):
        """Initialize the WebSocket manager with empty connections dict."""
        self.active_connections: Dict[str, WebSocket] = {}
        # Map session_id to user_id for routing
        self.session_to_user: Dict[str, str] = {}
        # Map user_id to list of their session_ids
        self.user_sessions: Dict[str, list] = {}
        # Store reference to main event loop for thread-safe operations
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        # Session management configuration
        self.config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        self.single_session_per_user = self.config_mgr.get( "websocket enforce single session per user", default=False, return_type="boolean" )
        self.session_timestamps: Dict[str, datetime] = {}  # Track when sessions connected
        
        # Event subscription system
        self.session_subscriptions: Dict[str, List[str]] = {}  # Map session_id to list of subscribed events
        
        # Load available events from configuration
        event_list = self.config_mgr.get( "websocket available events", default=[], return_type="list-string" )
        if not event_list:
            raise ValueError( "websocket available events configuration is missing or empty! Please check lupin-app.ini" )
        
        self.available_events = set( event_list )
        print( f"[WS] Loaded {len(self.available_events)} available event types from configuration" )
        
        print( f"[WS] WebSocketManager initialized with single_session_per_user = {self.single_session_per_user}" )
    
    def set_event_loop( self, loop: asyncio.AbstractEventLoop ):
        """
        Store reference to the main event loop for thread-safe operations.
        
        This should be called during application startup to enable safe
        WebSocket emissions from background threads.
        
        Args:
            loop: The main asyncio event loop from FastAPI
        """
        self.main_loop = loop
        print( "[WS] Event loop reference stored for thread-safe operations" )
    
    def connect( self, websocket: WebSocket, session_id: str, user_id: str = None, subscribed_events: List[str] = None ):
        """
        Add a new WebSocket connection with optional user association.
        
        Implements optional single-session policy: if enabled, closes old sessions
        when a user connects with a new session.
        
        Args:
            websocket: The WebSocket connection
            session_id: Unique session identifier
            user_id: Optional user ID to associate with this session
        """
        # Check for single-session policy
        if user_id and self.single_session_per_user and user_id in self.user_sessions:
            existing_sessions = self.user_sessions[user_id][:]
            if len( existing_sessions ) > 0:
                print( f"[WS] User {user_id} already connected with {len(existing_sessions)} session(s), closing old ones" )
                for old_session_id in existing_sessions:
                    if old_session_id != session_id and old_session_id in self.active_connections:
                        # Close the old WebSocket connection
                        old_ws = self.active_connections[old_session_id]
                        try:
                            # Schedule close on the event loop if we have one
                            if self.main_loop and self.main_loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    old_ws.close( code=1000, reason="New session opened" ),
                                    self.main_loop
                                )
                            print( f"[WS] Closed old session {old_session_id} for user {user_id}" )
                        except Exception as e:
                            print( f"[WS] Error closing old session {old_session_id}: {e}" )
                        # Clean up the connection
                        self.disconnect( old_session_id )
        
        # Add the new connection
        self.active_connections[session_id] = websocket
        self.session_timestamps[session_id] = datetime.now()
        
        if user_id:
            self.session_to_user[session_id] = user_id
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_id)
        
        # Store event subscriptions
        if subscribed_events:
            # Validate events
            valid_events = [e for e in subscribed_events if e == "*" or e in self.available_events]
            self.session_subscriptions[session_id] = valid_events
            print( f"[WS] Session {session_id} subscribed to: {valid_events}" )
        else:
            # Default: subscribe to all events
            self.session_subscriptions[session_id] = ["*"]
            print( f"[WS] Session {session_id} subscribed to: all events (*)" )
    
    def disconnect( self, session_id: str ):
        """Remove a WebSocket connection and clean up user associations."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            
        # Clean up session timestamp
        if session_id in self.session_timestamps:
            del self.session_timestamps[session_id]
            
        # Clean up event subscriptions
        if session_id in self.session_subscriptions:
            del self.session_subscriptions[session_id]
            
        # Clean up user association
        if session_id in self.session_to_user:
            user_id = self.session_to_user[session_id]
            del self.session_to_user[session_id]
            
            if user_id in self.user_sessions:
                self.user_sessions[user_id].remove(session_id)
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
    
    def register_session_user( self, session_id: str, user_id: str ):
        """
        Register a session-to-user association without a WebSocket connection.
        
        This is used when a TTS request comes in with authentication, allowing
        us to associate the session with a user before the audio WebSocket connects.
        
        Args:
            session_id: The session ID to register
            user_id: The user ID to associate with the session
        """
        # Store the association even if WebSocket hasn't connected yet
        self.session_to_user[session_id] = user_id
        
        # Track user sessions
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        if session_id not in self.user_sessions[user_id]:
            self.user_sessions[user_id].append( session_id )
        
        print( f"[WS] Registered session {session_id} for user {user_id} (pre-WebSocket)" )
    
    async def async_emit( self, event: str, data: dict ):
        """
        Emit an event to all connected WebSocket clients.
        
        Mimics Socket.IO's emit functionality for COSA queue compatibility.
        
        Args:
            event: The event type (e.g., 'queue_todo_update', 'queue_done_update')
            data: The data to send with the event
        """
        # Build message in format expected by queue.js
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        # Send to all connected clients that are subscribed to this event
        disconnected = []
        for session_id, websocket in self.active_connections.items():
            # Check if this session is subscribed to this event
            subscriptions = self.session_subscriptions.get( session_id, ["*"] )
            
            if "*" in subscriptions or event in subscriptions:
                try:
                    await websocket.send_json( message )
                except:
                    # Mark for removal if send fails
                    disconnected.append( session_id )
        
        # Clean up disconnected clients
        for session_id in disconnected:
            self.disconnect( session_id )
    
    def get_connection_count( self ) -> int:
        """Return the number of active connections."""
        return len( self.active_connections )
    
    def is_connected( self, session_id: str ) -> bool:
        """Check if a specific session is connected."""
        return session_id in self.active_connections
    
    async def emit_to_user( self, user_id: str, event: str, data: dict ):
        """
        Emit an event to all sessions belonging to a specific user.
        
        Args:
            user_id: The user ID to send to
            event: The event type
            data: The data to send
        """
        if user_id not in self.user_sessions:
            return
            
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        disconnected = []
        for session_id in self.user_sessions[user_id]:
            if session_id in self.active_connections:
                try:
                    websocket = self.active_connections[session_id]
                    await websocket.send_json( message )
                except:
                    disconnected.append( session_id )
        
        # Clean up disconnected sessions
        for session_id in disconnected:
            self.disconnect( session_id )
    
    async def emit_to_session( self, session_id: str, event: str, data: dict ):
        """
        Emit an event to a specific session.
        
        Args:
            session_id: The session ID to send to
            event: The event type
            data: The data to send
        """
        if session_id not in self.active_connections:
            return
            
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        try:
            websocket = self.active_connections[session_id]
            await websocket.send_json( message )
        except:
            self.disconnect( session_id )
    
    def emit( self, event: str, data: dict ):
        """
        Thread-safe synchronous wrapper for emit functionality.
        
        This method is called by COSA queues which expect synchronous Socket.IO-style emit.
        Uses asyncio.run_coroutine_threadsafe to safely schedule the coroutine
        on the main event loop from any thread.
        
        Args:
            event: The event type (e.g., 'queue_todo_update', 'queue_done_update')
            data: The data to send with the event
        """
        if not self.main_loop:
            print( f"[ERROR] No event loop reference - cannot emit {event}" )
            return
        
        if not self.main_loop.is_running():
            print( f"[ERROR] Event loop not running - cannot emit {event}" )
            return
        
        try:
            # Schedule coroutine on main event loop from any thread
            future = asyncio.run_coroutine_threadsafe(
                self._async_emit( event, data ),
                self.main_loop
            )
            # Don't wait for result to avoid blocking
            if hasattr( self, 'debug' ) and self.debug:
                print( f"[WS] Scheduled emission of {event}" )
        except Exception as e:
            print( f"[ERROR] Failed to schedule emission: {e}" )
    
    async def _async_emit( self, event: str, data: dict ):
        """
        Internal async method to emit events.
        
        This is the actual implementation that sends to WebSocket clients.
        """
        await self.async_emit( event, data )
    
    def emit_to_user_sync( self, user_id: str, event: str, data: dict ):
        """
        Thread-safe synchronous wrapper for emit_to_user.
        
        This method is called by COSA queues which expect synchronous emit.
        Uses asyncio.run_coroutine_threadsafe to safely schedule the coroutine
        on the main event loop from any thread.
        
        Args:
            user_id: The user ID to send to
            event: The event type
            data: The data to send
        """
        if not self.main_loop:
            print( f"[ERROR] No event loop reference - cannot emit {event} to user {user_id}" )
            return
        
        if not self.main_loop.is_running():
            print( f"[ERROR] Event loop not running - cannot emit {event} to user {user_id}" )
            return
        
        try:
            # Schedule coroutine on main event loop from any thread
            future = asyncio.run_coroutine_threadsafe(
                self.emit_to_user( user_id, event, data ),
                self.main_loop
            )
            # Don't wait for result to avoid blocking the COSA thread
            print( f"[WS] Scheduled emission of {event} to user {user_id}" )
        except Exception as e:
            print( f"[ERROR] Failed to schedule emission to user {user_id}: {e}" )
    
    def is_user_connected( self, user_id: str ) -> bool:
        """
        Check if a specific user has any active WebSocket connections.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            bool: True if user has at least one active connection
        """
        if user_id not in self.user_sessions:
            return False
        
        # Check if any of the user's sessions are still active
        active_sessions = [
            session_id for session_id in self.user_sessions[user_id]
            if session_id in self.active_connections
        ]
        
        return len( active_sessions ) > 0
    
    def get_user_connection_count( self, user_id: str ) -> int:
        """
        Get the number of active connections for a specific user.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            int: Number of active connections for this user
        """
        if user_id not in self.user_sessions:
            return 0
        
        active_sessions = [
            session_id for session_id in self.user_sessions[user_id]
            if session_id in self.active_connections
        ]
        
        return len( active_sessions )
    
    async def emit_to_user( self, user_id: str, event: str, data: dict ) -> bool:
        """
        Emit an event to all sessions belonging to a specific user.
        
        Args:
            user_id: The user ID to send to
            event: The event type
            data: The data to send
            
        Returns:
            bool: True if message was sent to at least one connection, False if user not available
        """
        if user_id not in self.user_sessions:
            return False
            
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        sent_count = 0
        disconnected = []
        
        for session_id in self.user_sessions[user_id]:
            if session_id in self.active_connections:
                # Check if this session is subscribed to this event
                subscriptions = self.session_subscriptions.get( session_id, ["*"] )
                
                if "*" in subscriptions or event in subscriptions:
                    try:
                        websocket = self.active_connections[session_id]
                        await websocket.send_json( message )
                        sent_count += 1
                    except:
                        disconnected.append( session_id )
        
        # Clean up disconnected sessions
        for session_id in disconnected:
            self.disconnect( session_id )
        
        return sent_count > 0
    
    async def emit_to_all( self, event: str, data: dict ):
        """
        Emit an event to all connected WebSocket clients.
        
        Alias for async_emit to match expected API naming.
        
        Args:
            event: The event type
            data: The data to send
        """
        await self.async_emit( event, data )
    
    def set_single_session_policy( self, enabled: bool ):
        """
        Enable or disable single-session-per-user policy.
        
        When enabled, new connections from a user will close their old sessions.
        
        Args:
            enabled: True to enable single-session policy, False to allow multiple sessions
        """
        self.single_session_per_user = enabled
        print( f"[WS] Single-session policy {'enabled' if enabled else 'disabled'}" )
    
    def get_session_info( self, session_id: str ) -> Optional[dict]:
        """
        Get information about a specific session.
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            dict with session info or None if session not found
        """
        if session_id not in self.active_connections:
            return None
            
        info = {
            "session_id": session_id,
            "connected": True,
            "user_id": self.session_to_user.get( session_id ),
            "connected_at": self.session_timestamps.get( session_id ).isoformat() if session_id in self.session_timestamps else None
        }
        
        # Calculate connection duration
        if session_id in self.session_timestamps:
            duration = datetime.now() - self.session_timestamps[session_id]
            info["duration_seconds"] = duration.total_seconds()
        
        return info
    
    def get_all_sessions_info( self ) -> list:
        """
        Get information about all active sessions.
        
        Returns:
            List of session info dictionaries
        """
        sessions = []
        for session_id in self.active_connections:
            info = self.get_session_info( session_id )
            if info:
                sessions.append( info )
        return sessions
    
    def cleanup_stale_sessions( self, max_age_hours: int = 24 ) -> int:
        """
        Remove sessions older than specified age.
        
        Args:
            max_age_hours: Maximum age in hours before a session is considered stale
            
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now()
        stale_sessions = []
        
        for session_id, timestamp in self.session_timestamps.items():
            age = now - timestamp
            if age.total_seconds() > (max_age_hours * 3600):
                stale_sessions.append( session_id )
        
        for session_id in stale_sessions:
            print( f"[WS] Cleaning up stale session {session_id} (age > {max_age_hours} hours)" )
            self.disconnect( session_id )
        
        return len( stale_sessions )
    
    async def heartbeat_check( self ) -> int:
        """
        Send ping messages to all connections and remove dead ones.
        
        This method is called periodically by the heartbeat background task
        to proactively detect and clean up dead WebSocket connections.
        
        Returns:
            int: Number of dead connections removed
        """
        if not self.config_mgr.get( "websocket heartbeat enabled", default=True, return_type="boolean" ):
            return 0
        
        dead_sessions = []
        
        # Send ping to each connection
        for session_id, websocket in list( self.active_connections.items() ):
            try:
                # Attempt to send a ping message
                await websocket.send_json( {
                    "type": "sys_ping",
                    "timestamp": datetime.now().isoformat()
                } )
            except:
                # Connection is dead, mark for removal
                dead_sessions.append( session_id )
        
        # Clean up dead connections
        for session_id in dead_sessions:
            print( f"[WS-HEARTBEAT] Detected dead session: {session_id}" )
            self.disconnect( session_id )
        
        if dead_sessions:
            print( f"[WS-HEARTBEAT] Removed {len(dead_sessions)} dead connection(s)" )
        
        return len( dead_sessions )
    
    async def auto_cleanup( self ) -> int:
        """
        Run automatic cleanup of stale sessions.
        
        This method is called periodically by the cleanup background task
        to remove sessions that have been connected for too long.
        
        Returns:
            int: Number of stale sessions cleaned up
        """
        if not self.config_mgr.get( "websocket cleanup enabled", default=True, return_type="boolean" ):
            return 0
        
        max_age_hours = self.config_mgr.get( "websocket session max age hours", default=24, return_type="int" )
        cleaned = self.cleanup_stale_sessions( max_age_hours )
        
        if cleaned > 0:
            print( f"[WS-CLEANUP] Cleaned {cleaned} stale session(s) older than {max_age_hours} hours" )
        
        return cleaned
    
    def update_subscriptions( self, session_id: str, events: List[str], action: str = "replace" ) -> bool:
        """
        Allow clients to update their event subscriptions after connection.
        
        Args:
            session_id: The session ID to update
            events: List of events to subscribe/unsubscribe
            action: "replace" (default), "add", or "remove"
            
        Returns:
            bool: True if successful, False if session not found
        """
        if session_id not in self.session_subscriptions:
            return False
        
        # Validate events
        valid_events = [e for e in events if e == "*" or e in self.available_events]
        
        if action == "replace":
            self.session_subscriptions[session_id] = valid_events
        elif action == "add":
            current = self.session_subscriptions[session_id]
            # Avoid duplicates
            self.session_subscriptions[session_id] = list( set( current + valid_events ) )
        elif action == "remove":
            current = self.session_subscriptions[session_id]
            self.session_subscriptions[session_id] = [e for e in current if e not in valid_events]
        
        print( f"[WS] Updated subscriptions for {session_id}: {self.session_subscriptions[session_id]}" )
        return True
    
    def get_subscription_stats( self ) -> dict:
        """
        Get statistics about event subscriptions.
        
        Returns:
            dict: Statistics including subscription counts and patterns
        """
        stats = {
            "total_connections": len( self.active_connections ),
            "subscription_counts": {},
            "wildcard_subscribers": 0,
            "filtered_connections": 0
        }
        
        for session_id, events in self.session_subscriptions.items():
            if "*" in events:
                stats["wildcard_subscribers"] += 1
            else:
                stats["filtered_connections"] += 1
                for event in events:
                    stats["subscription_counts"][event] = stats["subscription_counts"].get( event, 0 ) + 1
        
        return stats