"""
Generic file serving endpoint for files in the io/ directory.

Provides a unified endpoint for serving:
- Deep research reports (markdown)
- Podcast scripts (markdown)
- Podcast audio files (mp3)
- Other io/ files (pdf, etc.)

Security:
- Path validation prevents directory traversal
- Only serves files within io/ directory
- Validates file extension against content type

Generated on: 2026-01-20
"""

import os
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

import cosa.utils.util as cu

router = APIRouter( tags=[ "io-files" ] )


# Content type mapping by file extension
MEDIA_TYPES = {
    ".md"   : "text/markdown; charset=utf-8",
    ".txt"  : "text/plain; charset=utf-8",
    ".mp3"  : "audio/mpeg",
    ".wav"  : "audio/wav",
    ".pdf"  : "application/pdf",
    ".json" : "application/json",
}


@router.get( "/api/io/file" )
async def get_io_file(
    path: str = Query( ..., description="Relative path within io/ directory" )
):
    """
    Serve files from the io/ directory with security validation.

    Supports serving:
    - Markdown files (.md) - research reports, podcast scripts
    - Audio files (.mp3, .wav) - podcast audio
    - Documents (.pdf, .txt, .json)

    Requires:
        - path is a relative path within io/ directory
        - File must exist
        - File extension must be in allowed list

    Ensures:
        - Returns file with appropriate content type
        - Prevents directory traversal attacks
        - Returns 400 for invalid/unsafe paths
        - Returns 404 for missing files

    Args:
        path: Relative path within io/ directory (URL-decoded automatically)

    Returns:
        FileResponse or PlainTextResponse depending on file type

    Raises:
        HTTPException 400: Invalid or unsafe path
        HTTPException 404: File not found
    """
    # Decode the path (FastAPI does this, but be explicit)
    decoded_path = unquote( path )

    # Get project root and io base
    project_root = cu.get_project_root()
    io_base = project_root + "/io"

    # Build full path - treat as relative to io/
    if decoded_path.startswith( "/" ):
        # Remove leading slash for relative path handling
        decoded_path = decoded_path.lstrip( "/" )

    full_path = os.path.join( io_base, decoded_path )

    # Normalize to prevent directory traversal (../ attacks)
    full_path = os.path.normpath( full_path )

    # Security: ensure resolved path is within io/ directory
    if not full_path.startswith( io_base ):
        raise HTTPException(
            status_code = 400,
            detail      = "Invalid path: must be within io/ directory"
        )

    # Check if file exists
    if not os.path.isfile( full_path ):
        raise HTTPException(
            status_code = 404,
            detail      = f"File not found: {decoded_path}"
        )

    # Determine content type from extension
    _, ext = os.path.splitext( full_path )
    ext = ext.lower()

    if ext not in MEDIA_TYPES:
        raise HTTPException(
            status_code = 400,
            detail      = f"Unsupported file type: {ext}"
        )

    media_type = MEDIA_TYPES[ ext ]

    # For text files, use PlainTextResponse (better encoding handling)
    if ext in [ ".md", ".txt", ".json" ]:
        try:
            with open( full_path, "r", encoding="utf-8" ) as f:
                content = f.read()
            return PlainTextResponse(
                content    = content,
                media_type = media_type
            )
        except Exception as e:
            raise HTTPException(
                status_code = 500,
                detail      = f"Error reading file: {str( e )}"
            )

    # For binary files (audio, pdf), use FileResponse
    else:
        try:
            # Extract filename for Content-Disposition header
            filename = os.path.basename( full_path )
            return FileResponse(
                path       = full_path,
                media_type = media_type,
                filename   = filename
            )
        except Exception as e:
            raise HTTPException(
                status_code = 500,
                detail      = f"Error serving file: {str( e )}"
            )


@router.get( "/api/io/health" )
async def io_files_health():
    """
    Health check for io files endpoint.

    Returns status of io/ directory availability.
    """
    project_root = cu.get_project_root()
    io_path = project_root + "/io"
    io_exists = os.path.isdir( io_path )

    # Count files in subdirectories
    subdirs = {}
    if io_exists:
        for subdir in [ "deep-research", "podcasts" ]:
            subdir_path = os.path.join( io_path, subdir )
            if os.path.isdir( subdir_path ):
                file_count = sum( 1 for _, _, files in os.walk( subdir_path ) for f in files )
                subdirs[ subdir ] = file_count

    return {
        "status"      : "ok",
        "io_path"     : io_path,
        "io_exists"   : io_exists,
        "subdirs"     : subdirs,
        "media_types" : list( MEDIA_TYPES.keys() )
    }
