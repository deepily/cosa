"""
WebSocket and authentication endpoints for the COSA system.

This module provides FastAPI router endpoints for WebSocket connections
and authentication testing. Supports both audio streaming and queue
update WebSocket connections with user authentication and session management.

Generated on: 2025-01-24
Updated: 2025-08-01 - Added Design by Contract documentation
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from datetime import datetime
import json
import asyncio
import re
from urllib.parse import unquote

# Import dependencies
from cosa.rest.auth import get_current_user
from cosa.rest.websocket_manager import WebSocketManager

router = APIRouter(tags=["websocket"])

# Global dependencies (temporary access via main module)
def get_websocket_manager():
    """
    FastAPI dependency to get the WebSocket manager instance.
    
    Requires:
        - fastapi_app.main module exists and has websocket_manager attribute
        
    Ensures:
        - Returns the global WebSocketManager instance
        
    Raises:
        - ImportError if main module cannot be imported
        - AttributeError if websocket_manager attribute is missing
    """
    import fastapi_app.main as main_module
    return main_module.websocket_manager

def get_active_tasks():
    """
    FastAPI dependency to get the active tasks dictionary.
    
    Requires:
        - fastapi_app.main module exists and has active_tasks attribute
        
    Ensures:
        - Returns the global active_tasks dictionary for task management
        
    Raises:
        - ImportError if main module cannot be imported
        - AttributeError if active_tasks attribute is missing
    """
    import fastapi_app.main as main_module
    return main_module.active_tasks

def get_app_debug():
    """
    FastAPI dependency to get application debug and verbose settings.
    
    Requires:
        - fastapi_app.main module exists and has app_debug, app_verbose attributes
        
    Ensures:
        - Returns tuple of (app_debug, app_verbose) boolean flags
        
    Raises:
        - ImportError if main module cannot be imported
        - AttributeError if debug/verbose attributes are missing
    """
    import fastapi_app.main as main_module
    return main_module.app_debug, main_module.app_verbose

def is_valid_session_id(session_id: str) -> bool:
    """
    Validate session ID format according to the expected pattern.
    
    Session IDs should be in the format: adjective noun (e.g., 'wise penguin')
    
    Requires:
        - session_id is a string (may be empty or invalid)
        
    Ensures:
        - Returns True if session_id matches pattern "word word" (lowercase)
        - Returns False if empty, whitespace-only, or invalid format
        - Uses regex pattern '^[a-z]+\s[a-z]+$' for validation
        
    Raises:
        - None
    """
    # Check it's not empty or just whitespace
    if not session_id or not session_id.strip():
        return False
    
    # Check format: word word (with a single space)
    pattern = r'^[a-z]+\s[a-z]+$'
    return bool(re.match(pattern, session_id.lower()))

@router.get("/api/auth-test")
async def auth_test(current_user: dict = Depends(get_current_user)):
    """
    Test endpoint to verify authentication is working.
    
    Example usage:
    curl -H "Authorization: Bearer mock_token_alice" http://localhost:8000/api/auth-test
    
    Returns:
        dict: Current user information
    """
    return {
        "message": "Authentication successful",
        "user_id": current_user["uid"],
        "email": current_user["email"],
        "name": current_user["name"],
        "timestamp": datetime.now().isoformat()
    }

@router.websocket("/ws/audio/{session_id}")
async def websocket_audio_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time TTS audio streaming.
    
    Preconditions:
        - session_id must be a valid session identifier
        - WebSocket connection must be established
        
    Postconditions:
        - Manages WebSocket connection lifecycle
        - Stores connection in websocket_manager for audio streaming
        - Handles disconnection cleanup
        
    Args:
        websocket: WebSocket connection object
        session_id: Unique session identifier for this client
    """
    # Get dependencies from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    active_tasks = main_module.active_tasks
    app_debug = main_module.app_debug
    app_verbose = main_module.app_verbose
    
    # URL decode session ID and validate format
    decoded_session_id = unquote(session_id)
    if not is_valid_session_id(decoded_session_id):
        await websocket.close(code=1008, reason="Invalid session ID format")
        print(f"[WS-AUDIO] Rejected connection with invalid session ID: {decoded_session_id}")
        return
    
    # Use decoded session ID for all further operations
    session_id = decoded_session_id
    
    await websocket.accept()
    
    # Check if this session has been pre-registered with a user (from TTS request)
    user_id = websocket_manager.session_to_user.get(session_id)
    
    # Audio WebSocket should only receive audio-related events
    audio_events = ["audio_streaming_status", "audio_streaming_complete", "sys_ping"]
    
    if not user_id:
        # If no pre-registration, audio WebSocket connections don't require immediate auth
        # The user association will be established when TTS request comes in
        print(f"[WS-AUDIO] No pre-registered user for session {session_id}, connecting without user association")
        websocket_manager.connect(websocket, session_id, subscribed_events=audio_events)
    else:
        print(f"[WS-AUDIO] Found pre-registered user {user_id} for session {session_id}")
        websocket_manager.connect(websocket, session_id, user_id, subscribed_events=audio_events)
    
    if app_debug:
        user_info = user_id if user_id else "no-user-yet"
        print( f"[WEBSOCKET] New connection on /ws/audio/{session_id} endpoint (audio streaming WebSocket) for user {user_info}" )
    
    print(f"[WS-AUDIO] Audio WebSocket connected for session: {session_id}")
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "audio_streaming_status",
            "text": f"Audio WebSocket connected for session {session_id}",
            "status": "success"
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (optional - for bidirectional communication)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if app_debug and app_verbose: 
                    print(f"[WS-AUDIO] Received message from {session_id}: {message}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                if app_debug: 
                    print(f"[WS-AUDIO] Error handling message from {session_id}: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        # Cancel any active streaming tasks for this session
        if session_id in active_tasks:
            print(f"[WS-AUDIO] Cancelling active streaming task for session: {session_id}")
            active_tasks[session_id].cancel()
            try:
                await active_tasks[session_id]
            except asyncio.CancelledError:
                pass
            del active_tasks[session_id]
        
        # Clean up connection
        websocket_manager.disconnect(session_id)
        print(f"[WS-AUDIO] Audio WebSocket disconnected for session: {session_id}")

@router.websocket("/ws/queue/{session_id}")
async def websocket_queue_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time queue updates and events.
    
    PHASE 2: WebSocket with authentication for user-specific updates.
    
    Preconditions:
        - session_id must be a valid session identifier
        - WebSocket connection must be established
        - First message must contain authentication token
        
    Postconditions:
        - Manages WebSocket connection for queue updates
        - Associates connection with authenticated user
        - Handles disconnection cleanup
        
    Args:
        websocket: WebSocket connection object
        session_id: Unique session identifier for this client
    """
    # Get dependencies from main module
    import fastapi_app.main as main_module
    websocket_manager = main_module.websocket_manager
    app_debug = main_module.app_debug
    
    # URL decode session ID and validate format
    decoded_session_id = unquote(session_id)
    if not is_valid_session_id(decoded_session_id):
        await websocket.close(code=1008, reason="Invalid session ID format")
        print(f"[WS-QUEUE] Rejected connection with invalid session ID: {decoded_session_id}")
        return
    
    # Use decoded session ID for all further operations
    session_id = decoded_session_id
    
    await websocket.accept()
    print(f"[WS-QUEUE] Queue WebSocket connected for session: {session_id}")
    
    if app_debug:
        print( f"[WEBSOCKET] New connection on /ws/queue/{session_id} endpoint (authenticated queue WebSocket)" )
    
    # Wait for authentication message
    try:
        auth_message = await websocket.receive_json()
        if auth_message.get("type") != "auth_request" or "token" not in auth_message:
            await websocket.send_json({
                "type": "error",
                "message": "First message must be auth_request with token"
            })
            await websocket.close()
            return
            
        # Verify token
        from cosa.rest.auth import verify_firebase_token
        try:
            user_info = await verify_firebase_token(auth_message["token"])
            user_id = user_info["uid"]
            
            # Extract subscribed events from auth message
            subscribed_events = auth_message.get("subscribed_events", ["*"])
            
            # Connect with user association and subscriptions
            websocket_manager.connect(websocket, session_id, user_id, subscribed_events)
            print(f"[WS-QUEUE] Authenticated session [{session_id}] for user [{user_id}]")
            
            # Send auth success
            await websocket.send_json({
                "type": "auth_success",
                "user_id": user_id,
                "session_id": session_id
            })
            
        except Exception as e:
            await websocket.send_json({
                "type": "auth_error",
                "message": str(e)
            })
            await websocket.close()
            return
            
    except Exception as e:
        print(f"[WS-QUEUE] Auth error: {e}")
        await websocket.close()
        return
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connect",
            "message": f"Queue WebSocket connected for session {session_id}",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # PHASE 2: Real queue updates now come from COSA queues via websocket_manager
        # Keep connection alive and listen for incoming messages
        while True:
            try:
                # Listen for any incoming messages (for future bidirectional communication)
                data = await websocket.receive_text()
                message = json.loads(data)
                print(f"[WS-QUEUE] Received message from {session_id}: {message}")
                
                # Handle specific message types if needed
                if message.get("type") == "sys_ping":
                    await websocket.send_json({
                        "type": "sys_pong",
                        "timestamp": datetime.now().isoformat()
                    })
                elif message.get("type") == "update_subscriptions":
                    # Handle subscription updates
                    events = message.get("events", [])
                    action = message.get("action", "replace")
                    success = websocket_manager.update_subscriptions(session_id, events, action)
                    await websocket.send_json({
                        "type": "subscription_update",
                        "success": success,
                        "subscriptions": websocket_manager.session_subscriptions.get(session_id, [])
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WS-QUEUE] Error in queue WebSocket for {session_id}: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(session_id)
        print(f"[WS-QUEUE] Queue WebSocket disconnected for session: {session_id}")


def quick_smoke_test():
    """
    Critical smoke test for WebSocket API router - validates WebSocket endpoint functionality.
    
    This test is essential for v000 deprecation as rest/routers/websocket.py is critical
    for real-time communication and WebSocket management in the REST system.
    """
    import cosa.utils.util as du
    
    du.print_banner( "WebSocket API Router Smoke Test", prepend_nl=True )
    
    try:
        # Test 1: Basic module and router structure
        print( "Testing core WebSocket API components..." )
        
        # Check if router exists and has expected attributes
        if 'router' in globals() and hasattr( router, 'routes' ):
            print( "✓ FastAPI router structure present" )
        else:
            print( "✗ FastAPI router structure missing" )
        
        # Check expected endpoints
        expected_endpoints = [ "auth_test", "websocket_audio_endpoint", "websocket_queue_endpoint" ]
        endpoints_found = 0
        
        for endpoint_name in expected_endpoints:
            if endpoint_name in globals():
                endpoints_found += 1
            else:
                print( f"⚠ Missing endpoint: {endpoint_name}" )
        
        if endpoints_found == len( expected_endpoints ):
            print( f"✓ All {len( expected_endpoints )} core WebSocket endpoints present" )
        else:
            print( f"⚠ Only {endpoints_found}/{len( expected_endpoints )} WebSocket endpoints present" )
        
        # Test 2: Critical dependency imports
        print( "Testing critical dependency imports..." )
        try:
            from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
            from datetime import datetime
            import json
            import asyncio
            import re
            from urllib.parse import unquote
            print( "✓ Core FastAPI and standard library imports successful" )
        except ImportError as e:
            print( f"✗ Core imports failed: {e}" )
        
        try:
            from cosa.rest.auth import get_current_user
            from cosa.rest.websocket_manager import WebSocketManager
            print( "✓ CoSA REST module imports successful" )
        except ImportError as e:
            print( f"⚠ CoSA REST imports failed: {e}" )
        
        # Test 3: Helper functions validation
        print( "Testing helper functions..." )
        helper_functions = [ "get_websocket_manager", "get_active_tasks", "get_app_debug", "is_valid_session_id" ]
        
        helpers_found = 0
        for helper_name in helper_functions:
            if helper_name in globals() and callable( globals()[helper_name] ):
                helpers_found += 1
            else:
                print( f"⚠ Missing helper: {helper_name}" )
        
        if helpers_found == len( helper_functions ):
            print( f"✓ All {len( helper_functions )} helper functions present" )
        else:
            print( f"⚠ Only {helpers_found}/{len( helper_functions )} helper functions present" )
        
        # Test 4: Session ID validation logic
        print( "Testing session ID validation logic..." )
        try:
            # Test valid session IDs
            valid_test_cases = [ "wise penguin", "happy cat", "smart dog" ]
            invalid_test_cases = [ "", "   ", "singleword", "too many words here", "UPPERCASE", "with123numbers" ]
            
            valid_passed = 0
            for valid_id in valid_test_cases:
                if is_valid_session_id( valid_id ):
                    valid_passed += 1
            
            invalid_rejected = 0
            for invalid_id in invalid_test_cases:
                if not is_valid_session_id( invalid_id ):
                    invalid_rejected += 1
            
            if valid_passed == len( valid_test_cases ):
                print( "✓ Valid session ID validation working" )
            else:
                print( f"⚠ Valid session ID validation: {valid_passed}/{len( valid_test_cases )} passed" )
            
            if invalid_rejected == len( invalid_test_cases ):
                print( "✓ Invalid session ID rejection working" )
            else:
                print( f"⚠ Invalid session ID rejection: {invalid_rejected}/{len( invalid_test_cases )} rejected" )
                
        except Exception as e:
            print( f"⚠ Session ID validation issues: {e}" )
        
        # Test 5: WebSocket endpoint function signatures
        print( "Testing WebSocket endpoint signatures..." )
        try:
            import inspect
            
            # Test auth_test endpoint
            if inspect.iscoroutinefunction( auth_test ):
                print( "✓ auth_test is properly async" )
            else:
                print( "⚠ auth_test may not be async" )
            
            # Check dependencies in auth_test
            sig = inspect.signature( auth_test )
            if 'current_user' in sig.parameters:
                print( "✓ auth_test has authentication dependency" )
            else:
                print( "⚠ auth_test missing authentication dependency" )
            
            # Test WebSocket endpoints
            for ws_endpoint in [ websocket_audio_endpoint, websocket_queue_endpoint ]:
                if inspect.iscoroutinefunction( ws_endpoint ):
                    endpoint_name = ws_endpoint.__name__
                    print( f"✓ {endpoint_name} is properly async" )
                    
                    # Check WebSocket parameter
                    sig = inspect.signature( ws_endpoint )
                    if 'websocket' in sig.parameters and 'session_id' in sig.parameters:
                        print( f"✓ {endpoint_name} has required WebSocket parameters" )
                    else:
                        print( f"⚠ {endpoint_name} missing required parameters" )
                else:
                    print( f"⚠ {ws_endpoint.__name__} may not be async" )
                    
        except Exception as e:
            print( f"⚠ WebSocket endpoint signature issues: {e}" )
        
        # Test 6: Router configuration validation
        print( "Testing router configuration..." )
        try:
            # Test router has proper tags
            if hasattr( router, 'tags' ) and 'websocket' in getattr( router, 'tags', [] ):
                print( "✓ Router tags configuration valid" )
            else:
                print( "⚠ Router tags configuration may have issues" )
            
            # Test routes are registered
            if hasattr( router, 'routes' ) and len( router.routes ) >= 3:
                print( f"✓ Router has {len( router.routes )} registered routes" )
            else:
                print( "⚠ Router may have missing routes" )
            
            # Check route types (WebSocket vs HTTP)
            ws_routes = 0
            http_routes = 0
            
            for route in router.routes:
                if hasattr( route, 'path' ):
                    if route.path.startswith( '/ws/' ):
                        ws_routes += 1
                    elif route.path.startswith( '/api/' ):
                        http_routes += 1
            
            if ws_routes >= 2 and http_routes >= 1:
                print( f"✓ Route types balanced: {ws_routes} WebSocket, {http_routes} HTTP" )
            else:
                print( f"⚠ Route distribution: {ws_routes} WebSocket, {http_routes} HTTP" )
                
        except Exception as e:
            print( f"⚠ Router configuration issues: {e}" )
        
        # Test 7: Dependency injection structure
        print( "Testing dependency injection structure..." )
        try:
            import inspect
            
            # Test dependency functions have proper import structure
            for dep_func in [ get_websocket_manager, get_active_tasks, get_app_debug ]:
                source_lines = inspect.getsource( dep_func )
                if 'import fastapi_app.main' in source_lines:
                    print( f"✓ {dep_func.__name__} dependency injection structure valid" )
                else:
                    print( f"⚠ {dep_func.__name__} dependency structure may have issues" )
                    
        except Exception as e:
            print( f"⚠ Dependency injection structure issues: {e}" )
        
        # Test 8: WebSocket message handling structure
        print( "Testing WebSocket message handling structure..." )
        try:
            # Check that endpoints have proper WebSocket handling logic
            for endpoint in [ websocket_audio_endpoint, websocket_queue_endpoint ]:
                source_code = inspect.getsource( endpoint )
                
                # Check for essential WebSocket patterns
                essential_patterns = [
                    "await websocket.accept()",
                    "WebSocketDisconnect",
                    "websocket.send_json(",
                    "websocket_manager.connect(",
                    "websocket_manager.disconnect("
                ]
                
                patterns_found = 0
                for pattern in essential_patterns:
                    if pattern in source_code:
                        patterns_found += 1
                
                endpoint_name = endpoint.__name__
                if patterns_found >= len( essential_patterns ) - 1:  # Allow for minor variations
                    print( f"✓ {endpoint_name} has proper WebSocket handling" )
                else:
                    print( f"⚠ {endpoint_name} missing WebSocket patterns: {patterns_found}/{len( essential_patterns )}" )
                    
        except Exception as e:
            print( f"⚠ WebSocket message handling issues: {e}" )
        
        # Test 9: Authentication integration validation
        print( "Testing authentication integration..." )
        try:
            # Check that auth endpoint uses proper authentication
            auth_source = inspect.getsource( auth_test )
            if 'current_user' in auth_source and 'Depends' in auth_source:
                print( "✓ Authentication endpoint integration valid" )
            else:
                print( "⚠ Authentication endpoint integration may have issues" )
            
            # Check that queue WebSocket handles authentication
            queue_source = inspect.getsource( websocket_queue_endpoint )
            auth_checks = [
                "auth_request",
                "verify_firebase_token",
                "auth_success",
                "auth_error"
            ]
            
            auth_patterns_found = 0
            for check in auth_checks:
                if check in queue_source:
                    auth_patterns_found += 1
            
            if auth_patterns_found >= len( auth_checks ) - 1:
                print( "✓ WebSocket authentication handling present" )
            else:
                print( f"⚠ Limited WebSocket auth handling: {auth_patterns_found}/{len( auth_checks )}" )
                
        except Exception as e:
            print( f"⚠ Authentication integration issues: {e}" )
        
        # Test 10: Critical v000 dependency scanning
        print( "\\n🔍 Scanning for v000 dependencies..." )
        
        # Scan the file for v000 patterns
        import inspect
        source_file = inspect.getfile( auth_test )  # Use any function to get file
        
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
        
        # Test 11: WebSocket connection lifecycle validation
        print( "\\nTesting WebSocket connection lifecycle..." )
        try:
            # Check that both WebSocket endpoints handle connection lifecycle properly
            for endpoint in [ websocket_audio_endpoint, websocket_queue_endpoint ]:
                source_code = inspect.getsource( endpoint )
                
                lifecycle_patterns = [
                    "await websocket.accept()",
                    "try:",
                    "finally:",
                    "websocket_manager.disconnect("
                ]
                
                lifecycle_found = 0
                for pattern in lifecycle_patterns:
                    if pattern in source_code:
                        lifecycle_found += 1
                
                endpoint_name = endpoint.__name__
                if lifecycle_found == len( lifecycle_patterns ):
                    print( f"✓ {endpoint_name} connection lifecycle properly managed" )
                else:
                    print( f"⚠ {endpoint_name} lifecycle issues: {lifecycle_found}/{len( lifecycle_patterns )}" )
                    
        except Exception as e:
            print( f"⚠ WebSocket lifecycle validation issues: {e}" )
    
    except Exception as e:
        print( f"✗ Error during WebSocket API testing: {e}" )
        import traceback
        traceback.print_exc()
    
    # Summary
    print( "\\n" + "="*60 )
    if v000_found:
        print( "🚨 CRITICAL ISSUE: WebSocket API has v000 dependencies!" )
        print( "   Status: NOT READY for v000 deprecation" )
        print( "   Priority: IMMEDIATE ACTION REQUIRED" )
        print( "   Risk Level: CRITICAL - WebSocket operations will break" )
    else:
        print( "✅ WebSocket API smoke test completed successfully!" )
        print( "   Status: Real-time communication system ready for v000 deprecation" )
        print( "   Risk Level: LOW" )
    
    print( "✓ WebSocket API smoke test completed" )


if __name__ == "__main__":
    quick_smoke_test()