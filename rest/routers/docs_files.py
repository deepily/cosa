"""
Whitelisted documentation file serving endpoint.

Sibling to io_files.py — serves project source-tree docs (markdown, README,
CLAUDE.md, R&D plans, etc.) so the document viewer can render them via
`/app/docs?path=<path>&scope=docs`.

Security model (mirrors io_files.py):
- Path must match one of ALLOWED_FILES (exact) or start with one of ALLOWED_PREFIXES
- Path is normalized to block `..` traversal
- Resolved path must stay within project root
- Only text-document extensions are allowed

Generated on: 2026-05-04
"""

import os
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

import cosa.utils.util as cu

router = APIRouter( tags=[ "docs-files" ] )


# Whitelist of allowed root-level files (exact-match)
ALLOWED_FILES = {
    "history.md",
    "CLAUDE.md",
    "TODO.md",
    "README.md",
    "bug-fix-queue.md",
}

# Whitelist of allowed directory prefixes (must end with /)
ALLOWED_PREFIXES = [
    "src/docs/",
    "src/rnd/",
    "src/workflow/",
]

# Allowed extensions — text documents only (no audio/pdf/etc, that's io_files.py's job)
MEDIA_TYPES = {
    ".md"   : "text/markdown; charset=utf-8",
    ".txt"  : "text/plain; charset=utf-8",
    ".json" : "application/json",
    ".yaml" : "text/yaml; charset=utf-8",
    ".yml"  : "text/yaml; charset=utf-8",
}


def _is_whitelisted( relative_path: str ) -> bool:
    """
    Check whether a relative path is permitted by the docs whitelist.

    Requires:
        - relative_path is a non-empty project-relative string with no leading slash

    Ensures:
        - returns True iff path matches ALLOWED_FILES exactly or starts with an ALLOWED_PREFIXES entry
        - returns False otherwise
    """
    if relative_path in ALLOWED_FILES:
        return True
    return any( relative_path.startswith( prefix ) for prefix in ALLOWED_PREFIXES )


@router.get(
    "/api/docs/file",
    summary     = "Serve project documentation file",
    description = "Serve text documents from a whitelisted set of project paths (src/docs/, src/rnd/, src/workflow/, root-level *.md). Path traversal is blocked."
)
async def get_docs_file(
    path: str = Query( ..., description="Project-relative path; must be in the docs whitelist" )
):
    """
    Serve a documentation file with whitelist + traversal protection.

    Requires:
        - path is a project-relative path (no leading slash); URL-decoded automatically
        - path resolves under the project root
        - path matches the whitelist (exact root file or allowed prefix)
        - file extension is in MEDIA_TYPES

    Ensures:
        - returns PlainTextResponse with the appropriate text media type
        - 400 for paths outside the whitelist or with directory-traversal artifacts
        - 400 for unsupported extensions
        - 404 if the file does not exist on disk

    Raises:
        - HTTPException 400: invalid/unsafe path or extension
        - HTTPException 404: file not found
        - HTTPException 500: read failure
    """
    decoded_path = unquote( path ).lstrip( "/" )

    if not decoded_path:
        raise HTTPException( status_code=400, detail="Empty path" )

    if not _is_whitelisted( decoded_path ):
        raise HTTPException(
            status_code = 400,
            detail      = f"Path not in docs whitelist: {decoded_path}"
        )

    project_root = cu.get_project_root()
    full_path    = os.path.normpath( os.path.join( project_root, decoded_path ) )

    # Block directory traversal — resolved path must stay inside project root
    if not full_path.startswith( project_root + os.sep ) and full_path != project_root:
        raise HTTPException(
            status_code = 400,
            detail      = "Invalid path: must be within project root"
        )

    if not os.path.isfile( full_path ):
        raise HTTPException(
            status_code = 404,
            detail      = f"File not found: {decoded_path}"
        )

    _, ext = os.path.splitext( full_path )
    ext = ext.lower()

    if ext not in MEDIA_TYPES:
        raise HTTPException(
            status_code = 400,
            detail      = f"Unsupported file type: {ext}"
        )

    media_type = MEDIA_TYPES[ ext ]

    try:
        with open( full_path, "r", encoding="utf-8" ) as f:
            content = f.read()
        return PlainTextResponse( content=content, media_type=media_type )
    except Exception as e:
        raise HTTPException(
            status_code = 500,
            detail      = f"Error reading file: {str( e )}"
        )


@router.get(
    "/api/docs/health",
    summary     = "Docs files health check",
    description = "Report which whitelisted prefixes/files are present on disk."
)
async def docs_files_health():
    """
    Health check for docs files endpoint.

    Ensures:
        - returns dict with project_root, whitelist contents, and per-entry existence flags
    """
    project_root = cu.get_project_root()

    file_status = {
        name: os.path.isfile( os.path.join( project_root, name ) )
        for name in sorted( ALLOWED_FILES )
    }
    prefix_status = {
        prefix: os.path.isdir( os.path.join( project_root, prefix.rstrip( "/" ) ) )
        for prefix in ALLOWED_PREFIXES
    }

    return {
        "status"           : "ok",
        "project_root"     : project_root,
        "allowed_files"    : file_status,
        "allowed_prefixes" : prefix_status,
        "media_types"      : list( MEDIA_TYPES.keys() ),
    }
