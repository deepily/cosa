"""
Audio processing endpoints (STT/TTS)
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
from datetime import datetime

# Import dependencies
from openai import OpenAI
import cosa.utils.util as du
from lib.clients import genie_client as gc
from cosa.rest.websocket_manager import WebSocketManager
from cosa.memory.input_and_output_table import InputAndOutputTable
from cosa.rest import multimodal_munger as mmm
from cosa.config.configuration_manager import ConfigurationManager

router = APIRouter(prefix="/api", tags=["audio"])

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

@router.post("/upload-and-transcribe-mp3")
async def upload_and_transcribe_mp3_file(
    request: Request,
    prefix: Optional[str] = Query(None),
    prompt_key: str = Query("generic"),
    prompt_verbose: str = Query("verbose"),
    whisper_pipeline = Depends(get_whisper_pipeline),
    config_mgr = Depends(get_config_manager)
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
        
        # Handle agent detection and routing
        is_agent_request = False
        if prefix and "agent" in prefix.lower():
            is_agent_request = True
            
        # Get multimodal munger for processing
        processed_transcription = mmm.process_transcription(
            processed_text,
            prompt_key=prompt_key,
            prompt_verbose=prompt_verbose,
            config_mgr=config_mgr
        )
        
        if not is_agent_request:
            # Add to I/O table for non-agent requests
            io_tbl = InputAndOutputTable(debug=app_debug, verbose=app_verbose)
            io_tbl.add_entry(
                input_text=processed_text,
                input_type="stt_mp3",
                output_text=processed_transcription,
                output_type="processed_transcription"
            )
        
        response_data = {
            "status": "success",
            "transcription": processed_transcription,
            "raw_transcription": processed_text,
            "prompt_key": prompt_key,
            "is_agent_request": is_agent_request,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save response to file
        with open("/tmp/last_response.json", "w") as f:
            import json
            json.dump(response_data, f, indent=2)
        
        return JSONResponse(response_data)
        
    except Exception as e:
        print(f"[ERROR] MP3 transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@router.post("/get-audio")
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
        # Parse request body
        request_data = await request.json()
        session_id = request_data.get("session_id")
        msg = request_data.get("text")
        
        if not session_id or not msg:
            raise HTTPException(status_code=400, detail="Missing session_id or text")
        
        # Check if WebSocket connection exists
        if not ws_manager.is_connected(session_id):
            raise HTTPException(status_code=404, detail=f"No WebSocket connection for session {session_id}")
        
        print(f"[TTS] Hybrid TTS request - session: {session_id}, msg: '{msg}'")
        
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
        io_tbl.add_entry(
            input_text=f"WAV file: {file.filename}",
            input_type="stt_wav",
            output_text=processed_text,
            output_type="transcription"
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