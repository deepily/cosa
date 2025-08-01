from fastapi import WebSocket
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
from cosa.config.configuration_manager import ConfigurationManager


class WebSocketManager:
    """
    Manages WebSocket connections and provides Socket.IO-like emit functionality.
    
    This class acts as an adapter between the COSA queue system (which expects
    Socket.IO-like emit methods) and FastAPI's native WebSocket implementation.
    Supports user session management, event subscriptions, and thread-safe operations.
    
    Requires:
        - ConfigurationManager with LUPIN_CONFIG_MGR_CLI_ARGS environment variable
        - Configuration values for websocket behavior and available events
        - Main asyncio event loop reference for thread-safe operations
        
    Ensures:
        - Thread-safe WebSocket emission from background threads
        - User session management with optional single-session enforcement
        - Event subscription system with validation
        - Automatic cleanup of stale and dead connections
        - Socket.IO-compatible interface for COSA queue system
        
    Usage:
        manager = WebSocketManager()
        manager.set_event_loop(asyncio.get_event_loop())
        manager.connect(websocket, session_id, user_id, events)
        manager.emit("event_type", {"data": "value"})
    """
    
    def __init__( self ):
        """
        Initialize the WebSocket manager with empty connections and configuration.
        
        Requires:
            - ConfigurationManager environment variable LUPIN_CONFIG_MGR_CLI_ARGS is set
            - Configuration contains 'websocket available events' list
            
        Ensures:
            - Initializes all connection tracking dictionaries
            - Loads configuration for session management and events
            - Sets up event subscription system with validation
            - Configures single-session policy based on configuration
            
        Raises:
            - ValueError if websocket available events configuration is missing
            - ConfigException if configuration manager initialization fails
        """
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
        
        Requires:
            - loop is a valid asyncio event loop
            
        Ensures:
            - Stores loop reference for thread-safe coroutine scheduling
            - Enables emit() method to work from any thread
            - Prints confirmation message
            
        Raises:
            - None
        """
        self.main_loop = loop
        print( "[WS] Event loop reference stored for thread-safe operations" )
    
    def connect( self, websocket: WebSocket, session_id: str, user_id: str = None, subscribed_events: List[str] = None ):
        """
        Add a new WebSocket connection with optional user association.
        
        Implements optional single-session policy: if enabled, closes old sessions
        when a user connects with a new session.
        
        Requires:
            - websocket is a valid FastAPI WebSocket instance
            - session_id is a unique string identifier
            - subscribed_events (if provided) contains valid event names or "*"
            
        Ensures:
            - Adds connection to active_connections dictionary
            - Associates session with user if user_id provided
            - Closes old sessions if single-session policy enabled
            - Sets up event subscriptions (defaults to "*" for all events)
            - Records connection timestamp
            - Validates subscribed events against available_events
            
        Raises:
            - Exception if closing old WebSocket connections fails (handled gracefully)
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
        """
        Remove a WebSocket connection and clean up all associated data.
        
        Requires:
            - session_id is a string (may or may not exist in connections)
            
        Ensures:
            - Removes connection from active_connections if present
            - Cleans up session timestamp tracking
            - Removes event subscription mappings
            - Cleans up user-to-session associations
            - Removes empty user session lists
            
        Raises:
            - None (handles missing keys gracefully)
        """
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
        
        Requires:
            - session_id is a non-empty string
            - user_id is a non-empty string
            
        Ensures:
            - Creates session-to-user mapping
            - Adds session to user's session list
            - Initializes user session list if needed
            - Avoids duplicate session entries
            - Prints confirmation message
            
        Raises:
            - None
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
        Emit an event to all connected WebSocket clients asynchronously.
        
        Mimics Socket.IO's emit functionality for COSA queue compatibility.
        Sends messages only to clients subscribed to the event.
        
        Requires:
            - event is a non-empty string event name
            - data is a dictionary containing event data
            
        Ensures:
            - Creates timestamped message in expected format
            - Sends to all clients subscribed to the event or "*"
            - Automatically disconnects failed connections
            - Cleans up disconnected clients from tracking
            
        Raises:
            - None (WebSocket send failures handled gracefully)
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
        """
        Return the number of active WebSocket connections.
        
        Requires:
            - None
            
        Ensures:
            - Returns count of active_connections dictionary
            
        Raises:
            - None
        """
        return len( self.active_connections )
    
    def is_connected( self, session_id: str ) -> bool:
        """
        Check if a specific session has an active WebSocket connection.
        
        Requires:
            - session_id is a string
            
        Ensures:
            - Returns True if session exists in active_connections
            - Returns False otherwise
            
        Raises:
            - None
        """
        return session_id in self.active_connections
    
    async def emit_to_user( self, user_id: str, event: str, data: dict ):
        """
        Emit an event to all sessions belonging to a specific user.
        
        Requires:
            - user_id is a non-empty string
            - event is a non-empty string event name
            - data is a dictionary containing event data
            
        Ensures:
            - Sends timestamped message to all user's active sessions
            - Only sends to sessions subscribed to the event
            - Cleans up disconnected sessions
            - Returns early if user has no sessions
            
        Raises:
            - None (WebSocket send failures handled gracefully)
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
        Emit an event to a specific WebSocket session.
        
        Requires:
            - session_id is a non-empty string
            - event is a non-empty string event name
            - data is a dictionary containing event data
            
        Ensures:
            - Sends timestamped message to specified session if active
            - Disconnects session if send fails
            - Returns early if session not found
            
        Raises:
            - None (WebSocket send failures handled gracefully)
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
        
        Requires:
            - event is a non-empty string event name
            - data is a dictionary containing event data
            - self.main_loop is set and running
            
        Ensures:
            - Schedules async emission on main event loop
            - Does not block calling thread
            - Prints error messages if event loop unavailable
            - Provides debug output when enabled
            
        Raises:
            - None (errors logged but not raised)
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
        Internal async method to emit events to all clients.
        
        This is the actual implementation that sends to WebSocket clients.
        Used by the thread-safe emit() wrapper method.
        
        Requires:
            - event is a non-empty string event name
            - data is a dictionary containing event data
            
        Ensures:
            - Delegates to async_emit for actual message sending
            
        Raises:
            - None (exceptions propagated from async_emit)
        """
        await self.async_emit( event, data )
    
    def emit_to_user_sync( self, user_id: str, event: str, data: dict ):
        """
        Thread-safe synchronous wrapper for emit_to_user.
        
        This method is called by COSA queues which expect synchronous emit.
        Uses asyncio.run_coroutine_threadsafe to safely schedule the coroutine
        on the main event loop from any thread.
        
        Requires:
            - user_id is a non-empty string
            - event is a non-empty string event name
            - data is a dictionary containing event data
            - self.main_loop is set and running
            
        Ensures:
            - Schedules async emission to user on main event loop
            - Does not block calling thread
            - Prints error messages if event loop unavailable
            - Prints confirmation when successfully scheduled
            
        Raises:
            - None (errors logged but not raised)
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
        
        Requires:
            - user_id is a non-empty string
            
        Ensures:
            - Returns True if user has at least one active session
            - Returns False if user has no sessions or all sessions inactive
            - Validates sessions against active_connections
            
        Raises:
            - None
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
        
        Requires:
            - user_id is a string
            
        Ensures:
            - Returns count of active sessions for the user
            - Returns 0 if user has no sessions
            - Only counts sessions present in active_connections
            
        Raises:
            - None
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
        
        Alias for async_emit to match expected API naming conventions.
        
        Requires:
            - event is a non-empty string event name
            - data is a dictionary containing event data
            
        Ensures:
            - Delegates to async_emit for message broadcasting
            
        Raises:
            - None (exceptions propagated from async_emit)
        """
        await self.async_emit( event, data )
    
    def set_single_session_policy( self, enabled: bool ):
        """
        Enable or disable single-session-per-user policy.
        
        When enabled, new connections from a user will close their old sessions.
        
        Requires:
            - enabled is a boolean value
            
        Ensures:
            - Updates single_session_per_user flag
            - Prints confirmation message
            - Policy takes effect on subsequent connections
            
        Raises:
            - None
        """
        self.single_session_per_user = enabled
        print( f"[WS] Single-session policy {'enabled' if enabled else 'disabled'}" )
    
    def get_session_info( self, session_id: str ) -> Optional[dict]:
        """
        Get detailed information about a specific WebSocket session.
        
        Requires:
            - session_id is a string
            
        Ensures:
            - Returns dict with session details if session exists
            - Returns None if session not found in active_connections
            - Includes connection duration and timestamp information
            - Includes associated user_id if available
            
        Raises:
            - None
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
        Get detailed information about all active WebSocket sessions.
        
        Requires:
            - None
            
        Ensures:
            - Returns list of session info dictionaries
            - Each dict contains session details from get_session_info
            - Empty list if no active connections
            
        Raises:
            - None
        """
        sessions = []
        for session_id in self.active_connections:
            info = self.get_session_info( session_id )
            if info:
                sessions.append( info )
        return sessions
    
    def cleanup_stale_sessions( self, max_age_hours: int = 24 ) -> int:
        """
        Remove WebSocket sessions older than specified age.
        
        Requires:
            - max_age_hours is a positive integer
            
        Ensures:
            - Identifies sessions older than max_age_hours
            - Disconnects and cleans up stale sessions
            - Prints cleanup messages for removed sessions
            - Returns count of cleaned up sessions
            
        Raises:
            - None
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
        
        Requires:
            - Method is called from async context
            - Configuration may disable heartbeat checking
            
        Ensures:
            - Sends sys_ping message to all active connections
            - Identifies and removes connections that fail to receive ping
            - Prints summary of removed connections
            - Returns early if heartbeat disabled in configuration
            
        Raises:
            - None (WebSocket failures handled gracefully)
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
        Run automatic cleanup of stale WebSocket sessions.
        
        This method is called periodically by the cleanup background task
        to remove sessions that have been connected for too long.
        
        Requires:
            - Method is called from async context
            - Configuration may disable auto cleanup
            
        Ensures:
            - Gets max age from configuration (default 24 hours)
            - Calls cleanup_stale_sessions with configured max age
            - Prints summary if sessions were cleaned
            - Returns early if cleanup disabled in configuration
            
        Raises:
            - None
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
        
        Requires:
            - session_id exists in session_subscriptions
            - events is a list of strings (may include "*" for all events)
            - action is one of "replace", "add", or "remove"
            
        Ensures:
            - Validates events against available_events list
            - Updates subscriptions according to specified action
            - Prints confirmation of subscription changes
            - Returns True if successful, False if session not found
            - Handles duplicate prevention for "add" action
            
        Raises:
            - None
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
        Get comprehensive statistics about event subscriptions across all sessions.
        
        Requires:
            - None
            
        Ensures:
            - Returns dict with total connection count
            - Includes count of wildcard subscribers ("*")
            - Includes count of filtered (specific event) connections
            - Provides per-event subscription counts
            - Counts only reflect active sessions with subscriptions
            
        Raises:
            - None
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