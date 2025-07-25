"""
Speech processing endpoints (STT/TTS)
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
from lib.clients import lupin_client as gc
from cosa.rest.websocket_manager import WebSocketManager
from cosa.memory.input_and_output_table import InputAndOutputTable
from cosa.rest import multimodal_munger as mmm
from cosa.config.configuration_manager import ConfigurationManager

router = APIRouter(prefix="/api", tags=["speech"])

# Global dependencies (temporary access via main module)
def get_whisper_pipeline():
    """Dependency to get Whisper pipeline"""
    import fastapi_app.main as main_module
    return main_module.whisper_pipeline

def get_websocket_manager():
    """Dependency to get WebSocket manager"""
    import fastapi_app.main as main_module
    return main_module.websocket_manager

def get_config_manager():
    """Dependency to get config manager"""
    import fastapi_app.main as main_module
    return main_module.config_mgr

def get_active_tasks():
    """Dependency to get active tasks"""
    import fastapi_app.main as main_module
    return main_module.active_tasks

def get_todo_queue():
    """Dependency to get todo queue"""
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
    Upload and transcribe MP3 audio file using Whisper model.
    
    Preconditions:
        - Request body must contain base64 encoded MP3 audio
        - Whisper pipeline must be initialized
        - Write permissions to docker path
        - Valid prompt_key in configuration
    
    Postconditions:
        - Audio file saved to disk temporarily
        - Transcription completed and processed
        - Response saved to last_response.json
        - Entry added to I/O table if not agent request
        - Job queued if agent request detected
    
    Args:
        request: FastAPI request containing base64 encoded audio
        prefix: Optional prefix for transcription processing
        prompt_key: Key for prompt selection (default: "generic")
        prompt_verbose: Verbosity level (default: "verbose")
    
    Returns:
        JSONResponse: Processed transcription results
    
    Raises:
        HTTPException: If audio decoding or transcription fails
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
        
        path = gc.docker_path.format("recording.mp3")
        
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
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@router.post("/get-speech")
async def get_tts_audio(
    request: Request,
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    active_tasks = Depends(get_active_tasks)
):
    """
    WebSocket-based TTS endpoint that streams audio via WebSocket.
    
    Preconditions:
        - Request body must contain session_id and text
        - WebSocket connection must exist for session_id
        - OpenAI API key must be available
        - config_mgr must be initialized
        
    Postconditions:
        - Returns immediate status response
        - Streams audio chunks via WebSocket to specified session
        
    Args:
        request: FastAPI request containing JSON body with session_id and text
        
    Returns:
        JSONResponse: Immediate status response
    """
    try:
        # Enhanced debugging for TTS requests
        print(f"[TTS-DEBUG] POST /api/get-speech called from {request.client.host}")
        print(f"[TTS-DEBUG] Headers: {dict(request.headers)}")
        
        # Parse request body
        request_data = await request.json()
        print(f"[TTS-DEBUG] Request data: {request_data}")
        
        session_id = request_data.get("session_id")
        msg = request_data.get("text")
        
        print(f"[TTS-DEBUG] Extracted - session_id: '{session_id}', text: '{msg}'")
        
        if not session_id or not msg:
            error_msg = f"Missing session_id or text - session_id: {session_id}, text: {msg}"
            print(f"[TTS-ERROR] {error_msg}")
            raise HTTPException(status_code=400, detail="Missing session_id or text")
        
        # Check if WebSocket connection exists
        is_connected = ws_manager.is_connected(session_id)
        print(f"[TTS-DEBUG] WebSocket connection check for {session_id}: {is_connected}")
        
        if not is_connected:
            error_msg = f"No WebSocket connection for session {session_id}"
            print(f"[TTS-ERROR] {error_msg}")
            # List active connections for debugging
            active_connections = list(ws_manager.active_connections.keys())
            print(f"[TTS-DEBUG] Active connections: {active_connections}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        print(f"[TTS-SUCCESS] Starting TTS for session: {session_id}, msg: '{msg}'")
        
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
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

@router.post("/get-speech-elevenlabs")
async def get_tts_audio_elevenlabs(
    request: Request,
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    active_tasks = Depends(get_active_tasks)
):
    """
    ElevenLabs WebSocket-based TTS endpoint that streams audio via WebSocket.
    
    Preconditions:
        - Request body must contain session_id and text
        - WebSocket connection must exist for session_id
        - ElevenLabs API key must be available
        - ElevenLabs WebSocket streaming API must be accessible
        
    Postconditions:
        - Returns immediate status response
        - Streams audio chunks via WebSocket to specified session
        
    Args:
        request: FastAPI request containing JSON body with session_id, text, and optional voice settings
        
    Returns:
        JSONResponse: Immediate status response
    """
    try:
        # Enhanced debugging for ElevenLabs TTS requests
        print(f"[TTS-ELEVENLABS-DEBUG] POST /api/get-speech-elevenlabs called from {request.client.host}")
        print(f"[TTS-ELEVENLABS-DEBUG] Headers: {dict(request.headers)}")
        
        # Parse request body
        request_data = await request.json()
        print(f"[TTS-ELEVENLABS-DEBUG] Request data: {request_data}")
        
        session_id = request_data.get("session_id")
        msg = request_data.get("text")
        voice_id = request_data.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Default Rachel voice
        stability = request_data.get("stability", 0.5)
        similarity_boost = request_data.get("similarity_boost", 0.8)
        
        print(f"[TTS-ELEVENLABS-DEBUG] Extracted - session_id: '{session_id}', text: '{msg}', voice_id: '{voice_id}'")
        
        if not session_id or not msg:
            error_msg = f"Missing session_id or text - session_id: {session_id}, text: {msg}"
            print(f"[TTS-ELEVENLABS-ERROR] {error_msg}")
            raise HTTPException(status_code=400, detail="Missing session_id or text")
        
        # Check if WebSocket connection exists
        is_connected = ws_manager.is_connected(session_id)
        print(f"[TTS-ELEVENLABS-DEBUG] WebSocket connection check for {session_id}: {is_connected}")
        
        if not is_connected:
            error_msg = f"No WebSocket connection for session {session_id}"
            print(f"[TTS-ELEVENLABS-ERROR] {error_msg}")
            # List active connections for debugging
            active_connections = list(ws_manager.active_connections.keys())
            print(f"[TTS-ELEVENLABS-DEBUG] Active connections: {active_connections}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        print(f"[TTS-ELEVENLABS-SUCCESS] Starting ElevenLabs TTS for session: {session_id}, msg: '{msg}'")
        
        # Start ElevenLabs TTS streaming in background
        task = asyncio.create_task(stream_tts_elevenlabs(
            session_id, msg, ws_manager, voice_id, stability, similarity_boost
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
        raise HTTPException(status_code=500, detail=f"ElevenLabs TTS generation failed: {str(e)}")

@router.post("/upload-and-transcribe-wav")
async def upload_and_transcribe_wav_file(
    file: UploadFile = File(...),
    prefix: Optional[str] = Query(None),
    whisper_pipeline = Depends(get_whisper_pipeline)
):
    """
    Upload and transcribe WAV audio file using Whisper model.
    
    Preconditions:
        - Request must contain a WAV file upload
        - Whisper pipeline must be initialized
        - Write permissions to /tmp directory
        - Valid audio file format (WAV)
    
    Postconditions:
        - Audio file saved to temp location and deleted after processing
        - Transcription completed
        - Entry added to I/O table
        - Returns transcribed text (not JSON like MP3 endpoint)
    
    Args:
        file: WAV audio file upload
        prefix: Optional prefix for transcription processing
    
    Returns:
        str: Transcribed and processed text
    
    Raises:
        HTTPException: If file processing or transcription fails
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
    Hybrid TTS streaming: Forward chunks immediately, client plays when complete.
    Simple, no format complexity, no buffering - just pipe OpenAI chunks to WebSocket.
    
    Args:
        session_id: Session ID for WebSocket connection
        msg: Text to convert to speech
        ws_manager: WebSocket manager instance
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
            "type": "status",
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
                    "type": "audio_complete",
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
    stability: float = 0.5,
    similarity_boost: float = 0.8
):
    """
    ElevenLabs WebSocket streaming: Direct WebSocket connection to ElevenLabs API.
    Provides low-latency streaming optimized for conversational AI with ~150-250ms total latency.
    
    Args:
        session_id: Session ID for WebSocket connection
        msg: Text to convert to speech
        ws_manager: WebSocket manager instance
        voice_id: ElevenLabs voice ID (default: Rachel)
        stability: Voice stability setting (0.0-1.0)
        similarity_boost: Voice similarity boost (0.0-1.0)
    """
    websocket = ws_manager.active_connections.get(session_id)
    if not websocket:
        print(f"[ERROR] No WebSocket connection for session {session_id}")
        return
    
    try:
        # Get ElevenLabs API key using COSA utility
        api_key = du.get_api_key("eleven11")
        if not api_key:
            raise ValueError("ElevenLabs API key not available")
        
        print(f"[TTS-ELEVENLABS] Starting generation for: '{msg}' with voice {voice_id}")
        
        # Send status update
        await websocket.send_json({
            "type": "status",
            "text": "Connecting to ElevenLabs...",
            "status": "loading",
            "provider": "elevenlabs"
        })
        
        # ElevenLabs WebSocket streaming endpoint
        elevenlabs_ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id=eleven_flash_v2_5"
        
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
                    "similarity_boost": similarity_boost
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
                "type": "status",
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
                    
                    if data.get("audio"):
                        # Decode base64 audio chunk
                        audio_chunk = base64.b64decode(data["audio"])
                        
                        # Forward audio chunk to client WebSocket
                        await websocket.send_bytes(audio_chunk)
                        chunk_count += 1
                        
                    elif data.get("isFinal"):
                        # End of stream
                        print(f"[TTS-ELEVENLABS] Stream complete")
                        break
                        
                    elif data.get("error"):
                        # ElevenLabs error
                        error_msg = data.get("error", "Unknown ElevenLabs error")
                        print(f"[TTS-ELEVENLABS] ElevenLabs error: {error_msg}")
                        raise Exception(f"ElevenLabs API error: {error_msg}")
                        
                except json.JSONDecodeError:
                    # Handle binary data if any
                    print(f"[TTS-ELEVENLABS] Received non-JSON message (possibly binary)")
                    continue
                
            # Send completion signal
            await websocket.send_json({
                "type": "audio_complete",
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