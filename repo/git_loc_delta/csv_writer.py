"""
CSV Writer — tidy-long output for the Daily LoC Delta tool.

Emits one row per (date, file_type) bucket:

    date,file_type,added,deleted,files_touched,commits
    2026-05-15,python,128,42,7,3
    2026-05-15,markdown,300,15,2,3
    ...

Schema is fixed regardless of file-type cardinality (long-form), which keeps
downstream pivots stable across runs. Empty input produces a header-only
CSV (no body rows), which is the documented behavior for empty ranges.

Implementation reuses the COSA `to_csv(index=False)` pattern (Reuse Map R6,
extended from `todo_list_agent.py:89-90` to disk writes).
"""

import os
from typing import Dict, Tuple

import pandas as pd


CSV_COLUMNS = [ "date", "file_type", "added", "deleted", "files_touched", "commits" ]


def write_csv( by_type: Dict[Tuple[str, str], Dict[str, int]], path: str, debug: bool = False ) -> int:
    """
    Write the by-(date,file_type) view to a tidy-long CSV at `path`.

    Requires:
        - by_type is dict[(date, file_type)] → {added, deleted, files_touched, commits}
          (an empty dict is allowed and produces a header-only CSV)
        - path is a string path; parent directory will be created if missing

    Ensures:
        - File written at `path` with the fixed CSV_COLUMNS header
        - Rows sorted by (date ascending, added descending) for stable display
        - Returns the number of body rows written (0 for empty input)
    """
    rows = []
    for ( date, file_type ), counts in by_type.items():
        rows.append({
            "date":          date,
            "file_type":     file_type,
            "added":         counts["added"],
            "deleted":       counts["deleted"],
            "files_touched": counts["files_touched"],
            "commits":       counts["commits"],
        })

    # Sort by date asc, then added desc within each date
    rows.sort( key=lambda r: ( r["date"], -r["added"] ) )

    parent = os.path.dirname( path )
    if parent and not os.path.isdir( parent ):
        os.makedirs( parent, exist_ok=True )
        if debug: print( f"[csv_writer] Created directory: {parent}" )

    df = pd.DataFrame( rows, columns=CSV_COLUMNS )
    df.to_csv( path, index=False )

    if debug: print( f"[csv_writer] Wrote {len(rows)} rows to {path}" )
    return len( rows )
