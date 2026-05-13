"""
Whitelisted documentation file serving endpoint.

Sibling to io_files.py — serves project source-tree docs and (per the
multi-repo extension on 2026-05-12) external-repo files via `?scope=<name>`.

Built-in `scope=docs` preserves backwards compatibility: the legacy narrow
whitelist (src/docs/, src/rnd/, src/workflow/, root *.md) under the project
root. Every other `scope` value is resolved through SCOPE_REGISTRY built at
startup from `[Lupin: Baseline]` INI keys (see _scope_registry.py).

Security model:
- JWT auth required on all requests (Depends(get_current_user)).
- Path normalized to block `..` traversal; resolved path must stay within
  scope root.
- Secrets blocklist (filename pattern match) applied to ALL scopes after
  per-scope whitelist (defense-in-depth).
- Only text-document and source-code extensions are allowed (MEDIA_TYPES).

Generated on: 2026-05-04, extended 2026-05-12.
"""

import os
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

import cosa.utils.util as cu
from cosa.config.configuration_manager import ConfigurationManager
from cosa.rest.auth import get_current_user
from cosa.rest.routers._dir_listing import list_directory
from cosa.rest.routers._scope_registry import (
    SECRETS_BLOCKLIST_PATTERNS,
    ScopeConfig,
    _is_secrets_path,
    _is_whitelisted_in_scope,
    build_scope_registry,
    resolve_in_scope,
)

router = APIRouter( tags=[ "docs-files" ] )


# Whitelist of allowed root-level files (exact-match) for legacy scope=docs
ALLOWED_FILES = {
    "history.md",
    "CLAUDE.md",
    "TODO.md",
    "README.md",
    "bug-fix-queue.md",
}

# Whitelist of allowed directory prefixes (must end with /) for legacy scope=docs
ALLOWED_PREFIXES = [
    "src/docs/",
    "src/rnd/",
    "src/workflow/",
]

# Allowed extensions:
#   - Markdown / text-renderable docs (handled as text/markdown in the viewer)
#   - Source code (handled as plain <pre> in the viewer; syntax highlighting
#     is a Phase 2.5 follow-on per design §8)
MEDIA_TYPES = {
    # Existing — markdown-renderable text
    ".md"   : "text/markdown; charset=utf-8",
    ".txt"  : "text/plain; charset=utf-8",
    ".json" : "application/json",
    ".yaml" : "text/yaml; charset=utf-8",
    ".yml"  : "text/yaml; charset=utf-8",

    # NEW (2026-05-12) — source code, rendered as plain <pre> in the frontend
    ".py"   : "text/x-python; charset=utf-8",
    ".ts"   : "text/typescript; charset=utf-8",
    ".tsx"  : "text/typescript; charset=utf-8",
    ".js"   : "text/javascript; charset=utf-8",
    ".jsx"  : "text/javascript; charset=utf-8",
    ".css"  : "text/css; charset=utf-8",
    ".html" : "text/html; charset=utf-8",
    ".sh"   : "text/x-shellscript; charset=utf-8",
    ".sql"  : "text/x-sql; charset=utf-8",
    ".toml" : "text/x-toml; charset=utf-8",
    ".ini"  : "text/plain; charset=utf-8",
    ".cfg"  : "text/plain; charset=utf-8",
    ".xml"  : "text/xml; charset=utf-8",
}


# Process-lifetime scope registry. Lazy-init on first access; subsequent
# calls hit the cached dict (no per-request rebuild).
_SCOPE_REGISTRY: dict = None  # sentinel — None means "not built yet"


def _get_scope_registry() -> dict:
    """
    Return the process-wide name→ScopeConfig dict, building it on first access.

    Ensures:
        - Returns a dict (possibly empty if no external repos configured)
        - Built exactly once per process via build_scope_registry(config_mgr)
    """
    global _SCOPE_REGISTRY
    if _SCOPE_REGISTRY is None:
        config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
        _SCOPE_REGISTRY = build_scope_registry( config_mgr )
    return _SCOPE_REGISTRY


def _is_whitelisted_legacy_docs( relative_path: str ) -> bool:
    """
    Legacy whitelist for scope=docs — preserves existing behavior unchanged.

    Requires:
        - relative_path is a non-empty project-relative string with no leading slash

    Ensures:
        - returns True iff path matches ALLOWED_FILES exactly, OR starts with an
          ALLOWED_PREFIXES entry, OR equals a bare prefix root (Q2 resolution
          from the doc-viewer-directory-listing design)
        - returns False otherwise
    """
    if relative_path in ALLOWED_FILES:
        return True
    for prefix in ALLOWED_PREFIXES:
        if relative_path.startswith( prefix ):
            return True
        if relative_path == prefix.rstrip( "/" ):
            return True
    return False


@router.get(
    "/api/docs/file",
    summary     = "Serve project documentation file or directory listing (multi-scope)",
    description = "Polymorphic file/directory endpoint. `scope=docs` (default) preserves the legacy narrow whitelist under the project root. Other scope values are resolved via SCOPE_REGISTRY built from [Lupin: Baseline] INI keys. JWT auth required on every request."
)
async def get_docs_file(
    path        : str  = Query( ..., description="Scope-relative path; URL-decoded automatically" ),
    scope       : str  = Query( "docs", description="Scope name — defaults to 'docs' for back-compat" ),
    current_user: dict = Depends( get_current_user ),
):
    """
    Serve a documentation file OR directory listing with per-scope whitelist + traversal protection.

    Polymorphic by resolved path type:
    - File → PlainTextResponse with appropriate media type
    - Directory → JSONResponse with {kind, scope, path, parent, entries}

    Requires:
        - JWT bearer token in Authorization header (enforced by get_current_user)
        - path is a scope-relative path (no leading slash); URL-decoded automatically
        - For scope='docs' (legacy): resolves under project root, path matches legacy whitelist
        - For other scopes: scope must exist in SCOPE_REGISTRY; path resolves under scope root,
          path matches the scope's allowed_prefixes (empty = wildcard)
        - File extension must be in MEDIA_TYPES (for file branch)
        - Resolved path must not match the secrets blocklist (filename pattern)

    Ensures:
        - file path → PlainTextResponse with appropriate text media type
        - directory path → JSONResponse with listing
        - 401 if missing/invalid auth (raised by get_current_user)
        - 400 for unknown scope, paths outside the whitelist, traversal artifacts,
          unsupported extensions, or secrets-blocklist matches
        - 404 if the resolved path does not exist on disk

    Raises:
        - HTTPException 401: invalid/missing auth (from get_current_user)
        - HTTPException 400: invalid/unsafe path, unknown scope, unsupported extension,
                             or secrets blocklist match
        - HTTPException 404: file or directory not found
        - HTTPException 500: read failure
    """
    decoded_path = unquote( path ).lstrip( "/" )

    # Secrets blocklist applies to ALL scopes BEFORE per-scope resolution —
    # if the path itself names a secret, never even attempt to resolve it.
    if _is_secrets_path( decoded_path ):
        raise HTTPException(
            status_code = 400,
            detail      = "Path matches secrets blocklist"
        )

    # ---------------------------------------------------------------------
    # Branch A: legacy scope=docs — preserves all existing behavior
    # ---------------------------------------------------------------------
    if scope == "docs":
        if not decoded_path:
            raise HTTPException( status_code=400, detail="Empty path" )

        if not _is_whitelisted_legacy_docs( decoded_path ):
            raise HTTPException(
                status_code = 400,
                detail      = f"Path not in docs whitelist: {decoded_path}"
            )

        project_root = cu.get_project_root()
        full_path    = os.path.normpath( os.path.join( project_root, decoded_path ) )

        if not full_path.startswith( project_root + os.sep ) and full_path != project_root:
            raise HTTPException(
                status_code = 400,
                detail      = "Invalid path: must be within project root"
            )

        return _serve( full_path, decoded_path, scope="docs", parent_validator=_is_whitelisted_legacy_docs )

    # ---------------------------------------------------------------------
    # Branch B: external scope — registry lookup
    # ---------------------------------------------------------------------
    registry  = _get_scope_registry()
    scope_cfg = registry.get( scope )

    if scope_cfg is None:
        raise HTTPException(
            status_code = 400,
            detail      = f"Unknown scope: {scope!r}"
        )

    if not _is_whitelisted_in_scope( scope_cfg, decoded_path ):
        raise HTTPException(
            status_code = 400,
            detail      = f"Path not in scope whitelist: {decoded_path}"
        )

    try:
        full_path = resolve_in_scope( scope_cfg, decoded_path )
    except ValueError as e:
        raise HTTPException( status_code=400, detail=str( e ) )

    # Bind scope_cfg into the parent_validator so the directory listing's
    # "parent" field uses per-scope whitelist logic.
    return _serve(
        full_path,
        decoded_path,
        scope            = scope,
        parent_validator = lambda p, _cfg=scope_cfg: _is_whitelisted_in_scope( _cfg, p ),
    )


def _serve( full_path: str, rel_path: str, scope: str, parent_validator ) -> JSONResponse | PlainTextResponse:
    """
    Common file/directory dispatch — shared by legacy `docs` branch and registry branch.

    Requires:
        - full_path is an absolute filesystem path inside the scope root (caller verified)
        - rel_path is the scope-relative path string used for response composition
        - scope is the scope name string
        - parent_validator is a callable taking a candidate parent path and returning
          True iff that parent should be exposed in the directory listing's `parent` field

    Ensures:
        - directory → JSONResponse with the standard listing shape; secrets blocklist
          filtering applied per-entry inside list_directory
        - file → PlainTextResponse with the appropriate MEDIA_TYPES entry
        - 404 if path doesn't exist; 400 if extension not in MEDIA_TYPES; 500 on read failure
    """
    # Directory branch (polymorphic response) — must come before isfile check
    if os.path.isdir( full_path ):
        listing = list_directory(
            abs_dir          = full_path,
            rel_dir          = rel_path,
            scope            = scope,
            allowed_exts     = set( MEDIA_TYPES.keys() ),
            parent_validator = parent_validator,
        )
        return JSONResponse( content=listing )

    if not os.path.isfile( full_path ):
        raise HTTPException(
            status_code = 404,
            detail      = f"Path not found: {rel_path}"
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
    description = "Report which whitelisted prefixes/files are present on disk, plus the registered external scopes and their reachability."
)
async def docs_files_health():
    """
    Health check for docs files endpoint.

    Ensures:
        - returns dict with project_root, legacy whitelist contents, external-scope
          registry (name → root, allowed_prefixes, exists flag), and the
          full MEDIA_TYPES extension list
        - intentionally unauthenticated — health endpoints are public probes
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

    # Reflect the registry shape — useful for `/api/docs/health` smoke checks.
    registry = _get_scope_registry()
    external_scopes = {
        name: {
            "root"             : cfg.root,
            "exists"           : os.path.isdir( cfg.root ),
            "allowed_prefixes" : list( cfg.allowed_prefixes ),
        }
        for name, cfg in registry.items()
    }

    return {
        "status"           : "ok",
        "project_root"     : project_root,
        "allowed_files"    : file_status,
        "allowed_prefixes" : prefix_status,
        "external_scopes"  : external_scopes,
        "media_types"      : list( MEDIA_TYPES.keys() ),
    }
