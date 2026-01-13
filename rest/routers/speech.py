"""
Speech processing endpoints for speech-to-text and text-to-speech functionality.

Provides comprehensive audio processing capabilities including Whisper-based STT
for MP3 and WAV files, WebSocket-based TTS streaming with OpenAI and ElevenLabs
integration, and multimodal content processing with agent request detection.

Generated on: 2025-01-24
"""

from fastapi import APIRouter, Request, Query, HTTPException, File, UploadFile, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import base64
import time
import asyncio
import uuid
import os
import json
from datetime import datetime
import aiohttp
import websockets

# Import dependencies
from openai import OpenAI
import cosa.utils.util as du
# from lib.clients import lupin_client as gc
from cosa.rest.websocket_manager import WebSocketManager
from cosa.memory.input_and_output_table import InputAndOutputTable
from cosa.rest import multimodal_munger as mmm
# from cosa.config.configuration_manager import ConfigurationManager
from cosa.rest.auth import get_current_user_id

router = APIRouter(prefix="/api", tags=["speech"])

# Global dependencies (temporary access via main module)
def get_whisper_pipeline():
    """
    Dependency to get Whisper pipeline from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has whisper_pipeline attribute
        
    Ensures:
        - Returns the Whisper pipeline instance
        - Provides access to speech-to-text transcription
        
    Raises:
        - ImportError if main module not available
        - AttributeError if whisper_pipeline not found
    """
    import fastapi_app.main as main_module
    return main_module.whisper_pipeline

def get_websocket_manager():
    """
    Dependency to get WebSocket manager from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has websocket_manager attribute
        
    Ensures:
        - Returns the WebSocket manager instance
        - Provides access to WebSocket communication
        
    Raises:
        - ImportError if main module not available
        - AttributeError if websocket_manager not found
    """
    import fastapi_app.main as main_module
    return main_module.websocket_manager

def get_config_manager():
    """
    Dependency to get configuration manager from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has config_mgr attribute
        
    Ensures:
        - Returns the configuration manager instance
        - Provides access to application configuration
        
    Raises:
        - ImportError if main module not available
        - AttributeError if config_mgr not found
    """
    import fastapi_app.main as main_module
    return main_module.config_mgr

def get_active_tasks():
    """
    Dependency to get active tasks dictionary from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has active_tasks attribute
        
    Ensures:
        - Returns the active tasks dictionary
        - Provides access to background task management
        
    Raises:
        - ImportError if main module not available
        - AttributeError if active_tasks not found
    """
    import fastapi_app.main as main_module
    return main_module.active_tasks

def get_todo_queue():
    """
    Dependency to get todo queue from main module.
    
    Requires:
        - fastapi_app.main module is available
        - main_module has jobs_todo_queue attribute
        
    Ensures:
        - Returns the todo queue instance
        - Provides access to job queue management
        
    Raises:
        - ImportError if main module not available
        - AttributeError if jobs_todo_queue not found
    """
    import fastapi_app.main as main_module
    return main_module.jobs_todo_queue

@router.post("/upload-and-transcribe-mp3")
async def upload_and_transcribe_mp3_file(
    request: Request,
    prefix: Optional[str] = Query(None),
    prompt_key: str = Query("generic"),
    prompt_verbose: str = Query("verbose"),
    whisper_pipeline = Depends(get_whisper_pipeline),
    config_mgr = Depends(get_config_manager),
    todo_queue = Depends(get_todo_queue)
):
    """
    Upload and transcribe MP3 audio file using Whisper model with multimodal processing.
    
    Requires:
        - request.body() contains valid base64 encoded MP3 audio data
        - whisper_pipeline is initialized and functional
        - Write permissions exist for docker path location
        - prompt_key exists in configuration manager settings
        - config_mgr is accessible and properly configured
        
    Ensures:
        - Audio file is temporarily saved to docker path and processed
        - Whisper transcription is completed with chunked processing
        - MultiModalMunger processes transcription with agent detection
        - Agent requests are pushed to todo queue with websocket tracking
        - Non-agent requests are logged to InputAndOutputTable
        - Response is saved to /io/last_response.json in JSON format
        - Returns JSONResponse with processed transcription results
        
    Raises:
        - HTTPException with 500 status if base64 decoding fails
        - HTTPException with 500 status if file writing fails
        - HTTPException with 500 status if Whisper transcription fails
        - HTTPException with 500 status if multimodal processing fails
        
    Args:
        request: FastAPI request containing base64 encoded MP3 audio
        prefix: Optional prefix for transcription processing context
        prompt_key: Configuration key for prompt selection (default: "generic")
        prompt_verbose: Verbosity level for processing (default: "verbose")
        
    Returns:
        JSONResponse: Processed transcription with munger JSON format
    """
    try:
        # Get global debug settings
        import fastapi_app.main as main_module
        app_debug = main_module.app_debug
        app_verbose = main_module.app_verbose
        
        if app_debug:
            print("upload_and_transcribe_mp3_file() called")
            print(f"    prefix: [{prefix}]")
            print(f"prompt_key: [{prompt_key}]")
        
        # Get the request body (base64 encoded audio)
        body = await request.body()
        decoded_audio = base64.b64decode(body)
        
        # path = gc.docker_path.format("recording.mp3")
        # TODO: replace this with a unique file name to avoid runtime collisions?
        path = "/var/io/recording.mp3"
        
        if app_debug: 
            print(f"Saving file recorded audio bytes to [{path}]...", end="")
        
        with open(path, "wb") as f:
            f.write(decoded_audio)
        
        if app_debug: 
            print(" saved.")
        
        # Transcribe using Whisper pipeline
        raw_transcription = whisper_pipeline(path, chunk_length_s=30, stride_length_s=5)
        
        if app_debug:
            print(f"Raw transcription: [{raw_transcription}]")
        
        # Process transcription
        processed_text = raw_transcription["text"].strip()
        
        if app_debug:
            print(f"Processed text: [{processed_text}]")
        
        # Create multimodal munger instance for processing
        munger = mmm.MultiModalMunger(
            processed_text,
            prefix=prefix if prefix else "",
            prompt_key=prompt_key,
            debug=app_debug,
            verbose=app_verbose,
            config_mgr=config_mgr
        )
        
        # Check if this is an agent request using munger's method
        if munger.is_agent():
            # Push to todo queue for agent processing
            if app_debug:
                print(f"Munger: Posting [{munger.transcription}] to the agent's todo queue...")
            
            # TODO: Get websocket_id from the browser plugin request
            # The browser plugin should be sending this as part of the request
            munger.results = todo_queue.push_job(munger.transcription)
        else:
            # For non-agent requests, handle normally
            # Get the processed transcription
            processed_transcription = munger.transcription
            
            # If there are special results (e.g., contact info), use those instead
            if munger.results:
                processed_transcription = munger.results
            
            # Add to I/O table for non-agent requests
            io_tbl = InputAndOutputTable(debug=app_debug, verbose=app_verbose)
            io_tbl.insert_io_row(
                input_type="stt_mp3",
                input=processed_text,
                output_raw=processed_text,
                output_final=str(processed_transcription) if processed_transcription else ""
            )
        
        # Get the munger's JSON representation for browser compatibility
        response_json_str = munger.get_jsons()
        response_data = json.loads(response_json_str)
        
        # Save response to file (using the munger JSON format)
        last_response_path = "/io/last_response.json"
        du.write_string_to_file(du.get_project_root() + last_response_path, response_json_str)
        
        return JSONResponse(response_data)
        
    except Exception as e:
        print(f"[ERROR] MP3 transcription failed: {e}")
        raise HTTPException(status_code=500, detail="Audio transcription failed. Please try uploading the file again or check that it's a valid audio format.")

@router.post("/get-speech")
async def get_tts_audio(
    request: Request,
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    active_tasks = Depends(get_active_tasks),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    WebSocket-based TTS endpoint that streams audio via WebSocket using hybrid streaming.
    
    Requires:
        - request JSON body contains session_id and text fields
        - WebSocket connection exists and is active for session_id
        - OpenAI API key is available via du.get_api_key("openai")
        - current_user_id is authenticated and valid
        - ws_manager and active_tasks are properly initialized
        
    Ensures:
        - Session is registered with authenticated user for tracking
        - WebSocket connection status is verified before processing
        - TTS streaming task is created and managed in background
        - Returns immediate status response without blocking
        - Active task is tracked in active_tasks dictionary
        - Audio streaming occurs asynchronously via stream_tts_hybrid
        
    Raises:
        - HTTPException with 400 status if session_id or text missing
        - HTTPException with 404 status if WebSocket connection not found
        - HTTPException with 500 status if TTS generation setup fails
        
    Args:
        request: FastAPI request containing JSON with session_id and text
        ws_manager: WebSocket manager for connection handling
        active_tasks: Dictionary for background task management
        current_user_id: Authenticated user identifier
        
    Returns:
        JSONResponse: Immediate status confirmation with session details
    """
    try:
        # Get global debug settings
        import fastapi_app.main as main_module
        app_debug = main_module.app_debug
        app_verbose = main_module.app_verbose

        # Enhanced debugging for TTS requests
        if app_debug and app_verbose:
            print(f"[TTS-DEBUG] POST /api/get-speech called from {request.client.host}")
            print(f"[TTS-DEBUG] Headers: {dict(request.headers)}")

        # Parse request body
        request_data = await request.json()
        if app_debug and app_verbose: print(f"[TTS-DEBUG] Request data: {request_data}")
        
        # Validate request structure
        if not isinstance(request_data, dict):
            raise HTTPException(status_code=400, detail="Request body must be a valid JSON object")
        
        session_id = request_data.get("session_id")
        msg = request_data.get("text")

        if app_debug and app_verbose: print(f"[TTS-DEBUG] Extracted - session_id: '{session_id}', text: '{msg}'")

        # Validate required fields
        if not session_id or not msg:
            error_msg = f"Missing session_id or text - session_id: {session_id}, text: {msg}"
            print(f"[TTS-ERROR] {error_msg}")
            raise HTTPException(status_code=400, detail="Please provide both a session ID and text message for audio generation")

        # Validate field types and formats
        if not isinstance(session_id, str) or not isinstance(msg, str):
            raise HTTPException(status_code=400, detail="Both session_id and text must be strings")

        # Validate lengths to prevent abuse
        if len(session_id) > 255:
            raise HTTPException(status_code=400, detail="Session ID too long (max 255 characters)")

        if len(msg) > 10000:  # 10KB limit for TTS text
            raise HTTPException(status_code=400, detail="Text message too long (max 10,000 characters)")

        # Sanitize text input
        msg = msg.strip()
        if not msg:
            raise HTTPException(status_code=400, detail="Text message cannot be empty after trimming whitespace")

        # Register session with authenticated user
        if app_debug and app_verbose: print(f"[TTS-DEBUG] Registering session {session_id} for user {current_user_id}")
        ws_manager.register_session_user(session_id, current_user_id)

        # Check if WebSocket connection exists
        is_connected = ws_manager.is_connected(session_id)
        if app_debug and app_verbose: print(f"[TTS-DEBUG] WebSocket connection check for {session_id}: {is_connected}")

        if not is_connected:
            error_msg = f"No WebSocket connection for session {session_id}"
            print(f"[TTS-ERROR] {error_msg}")
            # List active connections for debugging
            if app_debug and app_verbose:
                active_connections = list(ws_manager.active_connections.keys())
                print(f"[TTS-DEBUG] Active connections: {active_connections}")
            raise HTTPException(status_code=404, detail="Audio connection lost. Please refresh the page and try again.")

        if app_debug and app_verbose: print(f"[TTS-SUCCESS] Starting TTS for session: {session_id}, msg: '{msg}'")
        
        # Start hybrid TTS streaming in background
        task = asyncio.create_task(stream_tts_hybrid(session_id, msg, ws_manager))
        active_tasks[session_id] = task
        
        # Return immediate status response
        return JSONResponse({
            "status": "success",
            "message": "TTS generation started",
            "session_id": session_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] TTS request failed: {e}")
        raise HTTPException(status_code=500, detail="Audio generation failed. Please try again, or check your connection and refresh the page.")

@router.post("/get-speech-elevenlabs")
async def get_tts_audio_elevenlabs(
    request: Request,
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    active_tasks = Depends(get_active_tasks),
    config_mgr = Depends(get_config_manager),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    ElevenLabs WebSocket-based TTS endpoint with low-latency streaming optimization.
    
    Requires:
        - request JSON body contains session_id and text fields
        - WebSocket connection exists and is active for session_id
        - ElevenLabs API key is available via du.get_api_key("eleven11")
        - current_user_id is authenticated and valid
        - ElevenLabs WebSocket streaming API is accessible
        - Optional voice_id, stability, and similarity_boost parameters are valid
        
    Ensures:
        - Session is registered with authenticated user for tracking
        - WebSocket connection status is verified before processing
        - ElevenLabs TTS streaming task is created and managed in background
        - Returns immediate status response with provider and voice information
        - Active task is tracked in active_tasks dictionary
        - Audio streaming occurs asynchronously via stream_tts_elevenlabs
        - Voice settings are properly configured for optimal quality
        
    Raises:
        - HTTPException with 400 status if session_id or text missing
        - HTTPException with 404 status if WebSocket connection not found
        - HTTPException with 500 status if ElevenLabs TTS setup fails
        
    Args:
        request: FastAPI request containing JSON with session_id, text, and voice settings
        ws_manager: WebSocket manager for connection handling
        active_tasks: Dictionary for background task management
        current_user_id: Authenticated user identifier
        
    Returns:
        JSONResponse: Immediate status with ElevenLabs provider details
    """
    try:
        # Get global debug settings
        import fastapi_app.main as main_module
        app_debug = main_module.app_debug
        app_verbose = main_module.app_verbose

        # Enhanced debugging for ElevenLabs TTS requests
        if app_debug and app_verbose:
            print(f"[TTS-ELEVENLABS-DEBUG] POST /api/get-speech-elevenlabs called from {request.client.host}")
            print(f"[TTS-ELEVENLABS-DEBUG] Headers: {dict(request.headers)}")

        # Parse request body
        request_data = await request.json()
        if app_debug and app_verbose: print(f"[TTS-ELEVENLABS-DEBUG] Request data: {request_data}")
        
        # Validate request structure
        if not isinstance(request_data, dict):
            raise HTTPException(status_code=400, detail="Request body must be a valid JSON object")
        
        session_id = request_data.get("session_id")
        msg = request_data.get("text")
        voice_id = request_data.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Default Rachel voice
        model_id = request_data.get("model_id", "eleven_turbo_v2_5")
        stability = request_data.get("stability", 0.5)
        similarity_boost = request_data.get("similarity_boost", 0.8)
        style = request_data.get("style", 0.0)
        use_speaker_boost = request_data.get("use_speaker_boost", False)
        speed = request_data.get("speed", 1.0)
        quality_profile = request_data.get("quality_profile", "balanced")
        debug_simulate_error = request_data.get("debug_simulate_error", False)
        
        # Validate required fields
        if not session_id or not msg:
            error_msg = f"Missing session_id or text - session_id: {session_id}, text: {msg}"
            print(f"[TTS-ELEVENLABS-ERROR] {error_msg}")
            raise HTTPException(status_code=400, detail="Please provide both a session ID and text message for audio generation")
        
        # Validate field types and formats
        if not isinstance(session_id, str) or not isinstance(msg, str):
            raise HTTPException(status_code=400, detail="Both session_id and text must be strings")
        
        # Validate lengths
        if len(session_id) > 255:
            raise HTTPException(status_code=400, detail="Session ID too long (max 255 characters)")
        
        if len(msg) > 10000:
            raise HTTPException(status_code=400, detail="Text message too long (max 10,000 characters)")
        
        # Validate numeric parameters
        if not isinstance(stability, (int, float)) or not (0.0 <= stability <= 1.0):
            raise HTTPException(status_code=400, detail="Stability must be a number between 0.0 and 1.0")
        
        if not isinstance(similarity_boost, (int, float)) or not (0.0 <= similarity_boost <= 1.0):
            raise HTTPException(status_code=400, detail="Similarity boost must be a number between 0.0 and 1.0")
        
        if not isinstance(speed, (int, float)) or not (0.1 <= speed <= 3.0):
            raise HTTPException(status_code=400, detail="Speed must be a number between 0.1 and 3.0")
        
        # Sanitize text input
        msg = msg.strip()
        if not msg:
            raise HTTPException(status_code=400, detail="Text message cannot be empty after trimming whitespace")

        if app_debug and app_verbose:
            print(f"[TTS-ELEVENLABS-DEBUG] Extracted - session_id: '{session_id}', text: '{msg}', voice_id: '{voice_id}'")
            if debug_simulate_error:
                print(f"[TTS-ELEVENLABS-DEBUG] 🧪 Debug mode: Error simulation enabled for this request")

        # Register session with authenticated user
        if app_debug and app_verbose: print(f"[TTS-ELEVENLABS-DEBUG] Registering session {session_id} for user {current_user_id}")
        ws_manager.register_session_user(session_id, current_user_id)

        # Check if WebSocket connection exists
        is_connected = ws_manager.is_connected(session_id)
        if app_debug and app_verbose: print(f"[TTS-ELEVENLABS-DEBUG] WebSocket connection check for {session_id}: {is_connected}")

        if not is_connected:
            error_msg = f"No WebSocket connection for session {session_id}"
            print(f"[TTS-ELEVENLABS-ERROR] {error_msg}")
            # List active connections for debugging
            if app_debug and app_verbose:
                active_connections = list(ws_manager.active_connections.keys())
                print(f"[TTS-ELEVENLABS-DEBUG] Active connections: {active_connections}")
            raise HTTPException(status_code=404, detail="Audio connection lost. Please refresh the page and try again.")

        if app_debug and app_verbose: print(f"[TTS-ELEVENLABS-SUCCESS] Starting ElevenLabs TTS for session: {session_id}, msg: '{msg}'")
        
        # Start ElevenLabs TTS streaming in background
        task = asyncio.create_task(stream_tts_elevenlabs(
            session_id, msg, ws_manager, voice_id, model_id, stability, 
            similarity_boost, style, use_speaker_boost, speed, quality_profile, config_mgr, debug_simulate_error
        ))
        active_tasks[session_id] = task
        
        # Return immediate status response
        return JSONResponse({
            "status": "success",
            "message": "ElevenLabs TTS generation started",
            "session_id": session_id,
            "provider": "elevenlabs",
            "voice_id": voice_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] ElevenLabs TTS request failed: {e}")
        raise HTTPException(status_code=500, detail="Audio generation failed. Please try again, or check your connection and refresh the page.")

@router.post("/upload-and-transcribe-wav")
async def upload_and_transcribe_wav_file(
    file: UploadFile = File(...),
    prefix: Optional[str] = Query(None),
    whisper_pipeline = Depends(get_whisper_pipeline)
):
    """
    Upload and transcribe WAV audio file using Whisper model with temporary file handling.
    
    Requires:
        - file is a valid UploadFile containing WAV audio data
        - whisper_pipeline is initialized and functional
        - Write permissions exist for /tmp directory
        - Audio file is in valid WAV format readable by Whisper
        - fastapi_app.main module is accessible for debug settings
        
    Ensures:
        - Uploaded file is saved to unique temporary location
        - Whisper transcription is completed on temporary file
        - Processed text is extracted and cleaned from transcription
        - Entry is logged to InputAndOutputTable with stt_wav type
        - Temporary file is always deleted after processing (success or failure)
        - Returns plain text string (different from MP3 JSON response)
        
    Raises:
        - HTTPException with 500 status if file upload/saving fails
        - HTTPException with 500 status if Whisper transcription fails
        - HTTPException with 500 status if I/O table insertion fails
        
    Args:
        file: WAV audio file upload from client
        prefix: Optional prefix for transcription processing context
        whisper_pipeline: Whisper model pipeline for transcription
        
    Returns:
        str: Transcribed and processed text content
    """
    try:
        # Get global debug settings
        import fastapi_app.main as main_module
        app_debug = main_module.app_debug
        app_verbose = main_module.app_verbose
        
        # Save uploaded file to temp location
        temp_file = f"/tmp/{uuid.uuid4()}-{file.filename}"
        
        if app_debug:
            print(f"Saving uploaded WAV file to [{temp_file}]...")
        
        with open(temp_file, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Transcribe using Whisper pipeline
        raw_transcription = whisper_pipeline(temp_file)
        
        # Process transcription
        processed_text = raw_transcription["text"].strip()
        
        if app_debug:
            print(f"WAV transcription: [{processed_text}]")
        
        # Add to I/O table
        io_tbl = InputAndOutputTable(debug=app_debug, verbose=app_verbose)
        io_tbl.insert_io_row(
            input_type="stt_wav",
            input=f"WAV file: {file.filename}",
            output_raw=processed_text,
            output_final=processed_text
        )
        
        # Clean up temp file
        os.remove(temp_file)
        
        # Return plain text (different from MP3 endpoint)
        return processed_text
        
    except Exception as e:
        # Clean up temp file on error
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        
        print(f"[ERROR] WAV transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"WAV transcription failed: {str(e)}")

async def stream_tts_hybrid(session_id: str, msg: str, ws_manager: WebSocketManager):
    """
    Hybrid TTS streaming with OpenAI: Forward chunks immediately for low-latency playback.
    
    Requires:
        - session_id exists in ws_manager.active_connections
        - msg is a non-empty string for TTS conversion
        - ws_manager is properly initialized with active WebSocket connections
        - OpenAI API key is available via du.get_api_key("openai")
        - WebSocket connection remains stable during streaming
        
    Ensures:
        - Creates OpenAI client with hardcoded base URL for real TTS API
        - Sends status updates to WebSocket during generation process
        - Streams MP3 audio chunks directly from OpenAI to WebSocket
        - Forwards each 8192-byte chunk immediately without buffering
        - Sends completion signal with timing and chunk count statistics
        - Handles connection loss gracefully with appropriate cleanup
        - Provides error messages via WebSocket on failures
        
    Raises:
        - None (handles all exceptions gracefully with error reporting)
        
    Args:
        session_id: Session ID for active WebSocket connection
        msg: Text content to convert to speech
        ws_manager: WebSocket manager instance for connection handling
    """
    websocket = ws_manager.active_connections.get(session_id)
    if not websocket:
        print(f"[ERROR] No WebSocket connection for session {session_id}")
        return
    
    try:
        # Always use OpenAI with MP3 - simple and reliable
        api_key = du.get_api_key("openai")
        # TODO: We should be dynamically getting the proper base URL for this connection.
        # Override base URL for TTS - vLLM doesn't support TTS, need real OpenAI API
        client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")
        
        print(f"[TTS-HYBRID] Starting generation for: '{msg}'")
        
        # Send status update
        await websocket.send_json({
            "type": "audio_streaming_status",
            "text": "Generating and streaming audio...",
            "status": "loading"
        })
        
        # Stream from OpenAI directly to WebSocket - no buffering, no format logic
        try:
            with client.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice="alloy",
                speed=1.125,
                response_format="mp3",  # Always MP3 - simple and universal
                input=msg
            ) as response:
                
                chunk_count = 0
                start_time = time.time()
                
                # Forward each chunk immediately as received
                for chunk in response.iter_bytes(chunk_size=8192):
                    # Check connection
                    if not ws_manager.is_connected(session_id):
                        print(f"[TTS-HYBRID] Connection lost for {session_id}")
                        return
                    
                    # Send chunk via WebSocket as binary
                    await websocket.send_bytes(chunk)
                    chunk_count += 1
                
                # Send completion signal
                await websocket.send_json({
                    "type": "audio_streaming_complete",
                    "text": f"Streaming complete ({chunk_count} chunks, {time.time() - start_time:.1f}s)",
                    "status": "success"
                })
                
                print(f"[TTS-HYBRID] ✓ Complete - {chunk_count} chunks in {time.time() - start_time:.2f}s")
                
        except Exception as e:
            print(f"[TTS-HYBRID] OpenAI API error: {e}")
            await websocket.send_json({
                "type": "error",
                "text": f"TTS generation failed: {str(e)}",
                "status": "error"
            })
            
    except Exception as e:
        print(f"[TTS-HYBRID] General error: {e}")
        if websocket:
            try:
                await websocket.send_json({
                    "type": "error", 
                    "text": f"TTS error: {str(e)}",
                    "status": "error"
                })
            except:
                pass  # Connection might be lost

async def stream_tts_elevenlabs(
    session_id: str, 
    msg: str, 
    ws_manager: WebSocketManager,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    model_id: str = "eleven_turbo_v2_5",
    stability: float = 0.5,
    similarity_boost: float = 0.8,
    style: float = 0.0,
    use_speaker_boost: bool = False,
    speed: float = 1.0,
    quality_profile: str = "balanced",
    config_mgr = None,
    debug_simulate_error: bool = False
):
    """
    ElevenLabs WebSocket streaming with optimized low-latency configuration for conversational AI.
    
    Requires:
        - session_id exists in ws_manager.active_connections
        - msg is a non-empty string for TTS conversion
        - ws_manager is properly initialized with active WebSocket connections
        - ElevenLabs API key is available via du.get_api_key("eleven11")
        - voice_id is a valid ElevenLabs voice identifier
        - stability and similarity_boost are floats between 0.0-1.0
        - ElevenLabs WebSocket streaming API is accessible
        
    Ensures:
        - Establishes WebSocket connection to ElevenLabs streaming endpoint
        - Configures optimized chunk length schedule for low latency (~150-250ms)
        - Sends voice settings and generation configuration to ElevenLabs
        - Streams text with try_trigger_generation for immediate processing
        - Forwards base64-decoded audio chunks to client WebSocket
        - Handles ElevenLabs protocol messages (audio, isFinal, error)
        - Sends completion signal with timing and chunk count statistics
        - Gracefully handles connection failures and API errors
        
    Raises:
        - None (handles all exceptions gracefully with error reporting)
        
    Args:
        session_id: Session ID for active WebSocket connection
        msg: Text content to convert to speech
        ws_manager: WebSocket manager instance for connection handling
        voice_id: ElevenLabs voice ID (default: Rachel voice)
        stability: Voice stability setting for consistent output (0.0-1.0)
        similarity_boost: Voice similarity enhancement (0.0-1.0)
    """
    websocket = ws_manager.active_connections.get(session_id)
    if not websocket:
        print(f"[ERROR] No WebSocket connection for session {session_id}")
        return
    
    try:
        # Load configuration profile settings if provided
        if config_mgr and quality_profile and quality_profile != "custom":
            profile_prefix = f"elevenlabs tts profile {quality_profile}"
            
            # Load profile settings, using current values as defaults if profile keys don't exist
            model_id = config_mgr.get( f"{profile_prefix} model", default=model_id )
            stability = config_mgr.get( f"{profile_prefix} stability", default=stability, return_type="float" )
            similarity_boost = config_mgr.get( f"{profile_prefix} similarity boost", default=similarity_boost, return_type="float" )
            style = config_mgr.get( f"{profile_prefix} style", default=style, return_type="float" )
            use_speaker_boost = config_mgr.get( f"{profile_prefix} use speaker boost", default=use_speaker_boost, return_type="boolean" )
            speed = config_mgr.get( f"{profile_prefix} speed", default=speed, return_type="float" )
        
        # Fall back to default config values if still using original defaults and config_mgr available
        if config_mgr:
            if voice_id == "21m00Tcm4TlvDq8ikWAM":  # Check if still using default
                voice_id = config_mgr.get( "elevenlabs tts default voice id", default=voice_id )
            if model_id == "eleven_turbo_v2_5" and quality_profile == "balanced":  # Check if still default and no profile applied
                model_id = config_mgr.get( "elevenlabs tts default model", default=model_id )
        
        # Get ElevenLabs API key using COSA utility
        api_key = du.get_api_key("eleven11")
        if not api_key:
            raise ValueError("ElevenLabs API key not available")
        
        print( f"[TTS-ELEVENLABS] Starting generation with voice {voice_id}" )
        print( f"[TTS-ELEVENLABS] Using model: {model_id}, profile: {quality_profile}" )
        print( f"[TTS-ELEVENLABS] >>>> FULL TTS TEXT ({len( msg )} chars):" )
        print( f"[TTS-ELEVENLABS] >>>>" )
        print( f"{msg}" )
        print( f"[TTS-ELEVENLABS] <<<<" )
        
        # Get app_verbose from main module (same pattern as other dependencies)
        import fastapi_app.main as main_module
        app_verbose = main_module.app_verbose
        
        if app_verbose:
            # Build vertically aligned banner text with colons aligned
            banner_text = f"""Voice Quality Settings:
Model ID         : {model_id}
Voice ID         : {voice_id}
Quality Profile  : {quality_profile}
Stability        : {stability:.2f}
Similarity Boost : {similarity_boost:.2f}
Style            : {style:.2f}
Speaker Boost    : {use_speaker_boost}
Speed            : {speed:.2f}"""
            du.print_banner( banner_text )
        else:
            print(f"[TTS-ELEVENLABS] Voice settings: stability={stability}, similarity_boost={similarity_boost}, style={style}, speaker_boost={use_speaker_boost}, speed={speed}")
        
        # 🧪 DEBUG: Check for error simulation before connecting to ElevenLabs
        if debug_simulate_error:
            if app_debug and app_verbose: print(f"[TTS-ELEVENLABS-DEBUG] 🧪 Simulating quota_exceeded error for testing")
            
            # Send initial status
            await websocket.send_json({
                "type": "audio_streaming_status",
                "text": "Connecting to ElevenLabs...",
                "status": "loading",
                "provider": "elevenlabs"
            })
            
            # Small delay to simulate connection attempt
            await asyncio.sleep(0.5)
            
            # Simulate the quota_exceeded error
            await websocket.send_json({
                "type": "tts_error",
                "text": "TTS service temporarily unavailable",
                "status": "error",
                "provider": "elevenlabs",
                "details": "Please try again in a moment"
            })
            return
        
        # Send status update
        await websocket.send_json({
            "type": "audio_streaming_status",
            "text": "Connecting to ElevenLabs...",
            "status": "loading",
            "provider": "elevenlabs"
        })
        
        # ElevenLabs WebSocket streaming endpoint with dynamic model and PCM 24000 format
        # PCM 24000 enables smooth Web Audio API playback without MP3 decoding gaps
        elevenlabs_ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model_id}&output_format=pcm_24000"
        
        # Connect to ElevenLabs WebSocket with authentication header
        elevenlabs_ws = await websockets.connect(
            elevenlabs_ws_url,
            additional_headers={"xi-api-key": api_key}
        )
        
        async with elevenlabs_ws:
            
            print(f"[TTS-ELEVENLABS] Connected to ElevenLabs WebSocket")
            
            # Send configuration message to ElevenLabs
            config_message = {
                "text": " ",  # Initial space to start stream
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": use_speaker_boost,
                    "speed": speed
                },
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290]  # Optimized for low latency
                }
            }
            
            await elevenlabs_ws.send(json.dumps(config_message))
            
            # Send the actual text
            text_message = {
                "text": msg,
                "try_trigger_generation": True
            }
            
            await elevenlabs_ws.send(json.dumps(text_message))
            
            # Send end-of-stream marker
            await elevenlabs_ws.send(json.dumps({"text": ""}))
            
            # Update status
            await websocket.send_json({
                "type": "audio_streaming_status",
                "text": "Streaming audio from ElevenLabs...",
                "status": "streaming",
                "provider": "elevenlabs"
            })
            
            chunk_count = 0
            start_time = time.time()
            
            # Stream audio chunks from ElevenLabs to client
            async for message in elevenlabs_ws:
                # Check if client WebSocket is still connected
                if not ws_manager.is_connected(session_id):
                    print(f"[TTS-ELEVENLABS] Client connection lost for {session_id}")
                    break

                try:
                    # Parse ElevenLabs message
                    data = json.loads(message)

                    # DEBUG: Log all non-audio messages from ElevenLabs
                    if not data.get("audio"):
                        print( f"[TTS-ELEVENLABS] <<<< RAW MESSAGE: {json.dumps( data, indent=2 )}" )

                    if data.get("audio"):
                        # Decode base64 audio chunk
                        audio_chunk = base64.b64decode(data["audio"])

                        # Forward audio chunk to client WebSocket
                        await websocket.send_bytes(audio_chunk)
                        chunk_count += 1
                        if chunk_count <= 3:
                            print( f"[TTS-ELEVENLABS] Audio chunk #{chunk_count}: {len(audio_chunk)} bytes" )

                    elif data.get("isFinal"):
                        # End of stream
                        print(f"[TTS-ELEVENLABS] Stream complete (isFinal=true)")
                        break

                    elif data.get( "error" ):
                        error_msg = data.get( "error", "Unknown ElevenLabs error" )

                        # Detailed logging for developers (shows real error for debugging)
                        print( f"[TTS-ELEVENLABS] !!!! ERROR DETECTED !!!!" )
                        print( f"[TTS-ELEVENLABS] Raw error field: {error_msg}" )
                        print( f"[TTS-ELEVENLABS] Full error data: {json.dumps( data, indent=2 )}" )

                        # Parse error type for user-friendly message
                        error_code   = "unknown"
                        user_message = "TTS service temporarily unavailable"

                        if "quota_exceeded" in error_msg.lower():
                            error_code   = "quota_exceeded"
                            user_message = "ElevenLabs quota exceeded. TTS unavailable until reset."
                        elif "rate_limit" in error_msg.lower():
                            error_code   = "rate_limit"
                            user_message = "Too many TTS requests. Please wait a moment."
                        elif "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
                            error_code   = "auth_error"
                            user_message = "TTS authentication failed."

                        await websocket.send_json( {
                            "type"       : "tts_error",
                            "text"       : user_message,
                            "error_code" : error_code,
                            "status"     : "error",
                            "provider"   : "elevenlabs",
                            "details"    : error_msg
                        } )

                        # Break instead of raise to allow graceful completion
                        break
                        
                except json.JSONDecodeError:
                    # Handle binary data if any
                    print(f"[TTS-ELEVENLABS] Received non-JSON message (possibly binary)")
                    continue
                
            # Send completion signal
            await websocket.send_json({
                "type": "audio_streaming_complete",
                "text": f"ElevenLabs streaming complete ({chunk_count} chunks, {time.time() - start_time:.1f}s)",
                "status": "success",
                "provider": "elevenlabs"
            })
            
            print(f"[TTS-ELEVENLABS] ✓ Complete - {chunk_count} chunks in {time.time() - start_time:.2f}s")
            
    except websockets.exceptions.ConnectionClosed:
        print(f"[TTS-ELEVENLABS] ElevenLabs WebSocket connection closed")
        if websocket:
            try:
                await websocket.send_json({
                    "type": "error",
                    "text": "ElevenLabs connection closed",
                    "status": "error",
                    "provider": "elevenlabs"
                })
            except:
                pass
                
    except Exception as e:
        print(f"[TTS-ELEVENLABS] Error: {e}")
        if websocket:
            try:
                await websocket.send_json({
                    "type": "error", 
                    "text": f"ElevenLabs TTS error: {str(e)}",
                    "status": "error",
                    "provider": "elevenlabs"
                })
            except:
                pass  # Connection might be lost