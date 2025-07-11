from fastapi import WebSocket
from datetime import datetime
from typing import Dict
import asyncio


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
    
    def connect( self, websocket: WebSocket, session_id: str, user_id: str = None ):
        """
        Add a new WebSocket connection with optional user association.
        
        Args:
            websocket: The WebSocket connection
            session_id: Unique session identifier
            user_id: Optional user ID to associate with this session
        """
        self.active_connections[session_id] = websocket
        
        if user_id:
            self.session_to_user[session_id] = user_id
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_id)
    
    def disconnect( self, session_id: str ):
        """Remove a WebSocket connection and clean up user associations."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            
        # Clean up user association
        if session_id in self.session_to_user:
            user_id = self.session_to_user[session_id]
            del self.session_to_user[session_id]
            
            if user_id in self.user_sessions:
                self.user_sessions[user_id].remove(session_id)
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
    
    async def async_emit( self, event: str, data: dict ):
        """
        Emit an event to all connected WebSocket clients.
        
        Mimics Socket.IO's emit functionality for COSA queue compatibility.
        
        Args:
            event: The event type (e.g., 'todo_update', 'done_update')
            data: The data to send with the event
        """
        # Build message in format expected by queue.js
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        # Send to all connected clients
        disconnected = []
        for session_id, websocket in self.active_connections.items():
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
        Synchronous wrapper for emit functionality.
        
        This method is called by COSA queues which expect synchronous Socket.IO-style emit.
        It creates an async task to handle the actual WebSocket communication.
        
        Args:
            event: The event type (e.g., 'todo_update', 'done_update')
            data: The data to send with the event
        """
        # Create async task to handle the emission
        try:
            # Get the current event loop or create one if needed
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create a task
                asyncio.create_task( self._async_emit( event, data ) )
            else:
                # If no loop is running, run the coroutine
                loop.run_until_complete( self._async_emit( event, data ) )
        except RuntimeError:
            # If we can't get an event loop, create a new one
            asyncio.run( self._async_emit( event, data ) )
    
    async def _async_emit( self, event: str, data: dict ):
        """
        Internal async method to emit events.
        
        This is the actual implementation that sends to WebSocket clients.
        """
        await self.async_emit( event, data )
    
    def emit_to_user_sync( self, user_id: str, event: str, data: dict ):
        """
        Synchronous wrapper for emit_to_user.
        
        This method is called by COSA queues which expect synchronous emit.
        
        Args:
            user_id: The user ID to send to
            event: The event type
            data: The data to send
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task( self.emit_to_user( user_id, event, data ) )
            else:
                loop.run_until_complete( self.emit_to_user( user_id, event, data ) )
        except RuntimeError:
            asyncio.run( self.emit_to_user( user_id, event, data ) )
    
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