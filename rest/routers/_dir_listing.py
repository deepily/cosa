"""
Shared directory-listing primitives for the doc/io file-serving endpoints.

Both `/api/docs/file` and `/api/io/file` now respond polymorphically:
- If path resolves to a file → existing PlainTextResponse / FileResponse
- If path resolves to a directory → JSONResponse with listing per §3.2

The per-extension `view_url` routing table (§3.4a) lives here so both
endpoints stay honest. Frontend consumes `view_url` as-is — no JS-side
extension sniffing.

Extended 2026-05-12 (multi-repo doc viewer): `scope` may now be any
registered external scope name (lupin, cosa-voice, claude-plans, etc.);
all non-`io` scopes route to /api/docs/file?scope=<name>. Secrets-blocklist
filtering applied per-entry inside list_directory.

Design docs:
- src/rnd/v0.1.7/2026.05.12-doc-viewer-directory-listing.md (original)
- src/rnd/v0.1.7/2026.05.12-multi-repo-doc-viewer.md (multi-repo extension)
"""

import os
from typing import Callable
from urllib.parse import quote

from cosa.rest.routers._scope_registry import _is_secrets_path


def _build_view_url( rel_path: str, scope: str, kind: str, ext: str ) -> str:
    """
    Build the viewer/player/download URL for a directory entry.

    Single source of truth for the per-extension routing table (§3.4a):
    - directory → /app/docs?path=...&scope=<scope>
    - .md/.txt/.json/.yaml/.yml → /app/docs?path=...&scope=<scope>
    - source-code extensions (.py/.ts/.tsx/.js/.jsx/.css/.html/.sh/.sql/.toml/
      .ini/.cfg/.xml) → /app/docs?path=...&scope=<scope> (plain <pre> in viewer)
    - .mp3/.wav (io only) → /app/audio?path=... (player page, NOT download)
    - .pdf (io only) → /api/io/file?path=... (browser renders inline)
    - .pptx (io only) → /api/io/file?path=...&download=true

    Requires:
        - rel_path is a non-empty path string relative to the scope root
        - scope is a non-empty scope name (built-in: "docs" or "io"; external:
          any name registered in SCOPE_REGISTRY)
        - kind is "file" or "directory"
        - ext is a lowercase extension including the dot (e.g., ".md"), or "" for directories

    Ensures:
        - returns a non-empty URL string
        - rel_path is URL-encoded via quote(safe="")
        - non-`io` scopes (built-in `docs` AND external scopes) all route to
          /api/docs/file?scope=<scope>; only `io` has the binary-content routing
          variants
    """
    encoded = quote( rel_path, safe="" )

    if kind == "directory":
        return f"/app/docs?path={encoded}&scope={scope}"

    if scope == "io":
        if ext in ( ".mp3", ".wav" ):
            return f"/app/audio?path={encoded}"
        if ext == ".pdf":
            return f"/api/io/file?path={encoded}"
        if ext in ( ".png", ".jpg", ".jpeg", ".gif", ".webp" ):
            # Images render inline in the browser via direct URL (Option A
            # per 2026.05.12-doc-viewer-directory-listing.md decision).
            return f"/api/io/file?path={encoded}"
        if ext == ".pptx":
            return f"/api/io/file?path={encoded}&download=true"

    # Default for text-renderable files (md/txt/json/yaml/yml AND source code)
    # in any non-io scope (built-in docs + every external scope).
    return f"/app/docs?path={encoded}&scope={scope}"


def list_directory(
    abs_dir          : str,
    rel_dir          : str,
    scope            : str,
    allowed_exts     : set,
    parent_validator : Callable[ [ str ], bool ]
) -> dict:
    """
    Build a directory-listing JSON dict for a whitelisted directory.

    Requires:
        - abs_dir is an absolute filesystem path to an existing directory
        - rel_dir is the project-relative (scope=docs) or io-relative (scope=io)
          path string; may or may not have a trailing slash; may be empty string
          (scope=io root case)
        - scope is "docs" or "io"
        - allowed_exts is a set of lowercase extension strings (e.g., {".md", ".txt"})
        - parent_validator(parent_rel) returns True iff that parent path should be
          exposed as the `parent` field (lets caller plug in scope-specific
          whitelist logic)

    Ensures:
        - returns dict shaped per §3.2:
          {kind: "directory", scope, path, parent, entries: [...]}
        - hidden entries (names starting with ".") are excluded (Q5)
        - file entries are filtered to those whose extension is in allowed_exts
        - entries are sorted directories-first, then alphabetical case-insensitive (Q4)
        - each entry carries a `view_url` from _build_view_url
        - directory entries have size=None; file entries have size=int (bytes)
        - parent is None if rel_dir has no dirname OR parent_validator rejects it
    """
    rel_dir_norm = rel_dir.rstrip( "/" )

    entries = [ ]
    with os.scandir( abs_dir ) as it:
        for entry in it:
            # Q5: hidden files / directories always excluded
            if entry.name.startswith( "." ):
                continue

            # Secrets blocklist (2026-05-12) — drop entries whose basename
            # matches a SECRETS_BLOCKLIST_PATTERNS entry so they don't surface
            # in listings at all. The per-request file fetch also rejects these
            # (defense-in-depth).
            if _is_secrets_path( entry.name ):
                continue

            try:
                if entry.is_dir( follow_symlinks=False ):
                    child_rel = f"{rel_dir_norm}/{entry.name}" if rel_dir_norm else entry.name
                    entries.append( {
                        "name"     : entry.name,
                        "kind"     : "directory",
                        "size"     : None,
                        "rel_path" : child_rel,
                        "view_url" : _build_view_url( child_rel, scope, "directory", "" ),
                    } )
                elif entry.is_file( follow_symlinks=False ):
                    ext = os.path.splitext( entry.name )[ 1 ].lower()
                    if ext not in allowed_exts:
                        continue
                    stat = entry.stat()
                    child_rel = f"{rel_dir_norm}/{entry.name}" if rel_dir_norm else entry.name
                    entries.append( {
                        "name"     : entry.name,
                        "kind"     : "file",
                        "size"     : stat.st_size,
                        "rel_path" : child_rel,
                        "view_url" : _build_view_url( child_rel, scope, "file", ext ),
                    } )
            except OSError:
                # Permission errors etc. — silently skip the entry rather than
                # poisoning the whole listing
                continue

    # Q4: directories first, then files; alphabetical case-insensitive within group
    entries.sort( key=lambda e: ( e[ "kind" ] != "directory", e[ "name" ].lower() ) )

    # Parent calculation
    parent_rel = os.path.dirname( rel_dir_norm )
    if not parent_rel or not parent_validator( parent_rel ):
        parent_rel = None

    return {
        "kind"    : "directory",
        "scope"   : scope,
        "path"    : rel_dir_norm,
        "parent"  : parent_rel,
        "entries" : entries,
    }
