"""
CLI entry point for the Daily LoC Delta tool.

Usage:
    python -m cosa.repo.run_git_loc_delta [OPTIONS]

See `--help` for the full flag list. Mirrors the CLI shape of
`run_branch_analyzer.py` (Reuse Map R4).

Exit codes:
    0 — success
    1 — git failure (GitCommandError / DateRangeError)
    2 — argument-parse error (argparse default)
"""

import argparse
import sys
from typing import Optional

import cosa.utils.util as cu

from cosa.repo.git_loc_delta.analyzer        import GitLogLocDeltaAnalyzer
from cosa.repo.git_loc_delta.csv_writer      import write_csv
from cosa.repo.git_loc_delta.exceptions      import DateRangeError, GitCommandError, GitLocDeltaError
from cosa.repo.git_loc_delta.report_formatter import format_console, format_json


def create_parser() -> argparse.ArgumentParser:
    """
    Create the command-line argument parser.

    Ensures:
        - Returns a fully configured argparse.ArgumentParser
        - All flags documented with help text
        - Mutually exclusive group enforces single date-range mode

    Raises:
        - Never raises
    """
    parser = argparse.ArgumentParser(
        prog        = "run_git_loc_delta",
        description = (
            "Per-day breakdown of LoC adds/deletes from `git log --numstat`. "
            "Sister tool to branch_analyzer (which answers 'what did the whole "
            "branch change') — this answers 'what changed when'."
        ),
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = (
            "Examples:\n"
            "  python -m cosa.repo.run_git_loc_delta\n"
            "  python -m cosa.repo.run_git_loc_delta --branch\n"
            "  python -m cosa.repo.run_git_loc_delta --branch --output csv\n"
            "  python -m cosa.repo.run_git_loc_delta --since 2026-05-01 --until 2026-05-15\n"
        ),
    )

    parser.add_argument(
        "--repo-path",
        default = ".",
        help    = "Repository to analyze (default: cwd)",
    )

    # Date range mode (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--today",
        action  = "store_true",
        help    = "(Default) Commits since today 00:00 local",
    )
    mode_group.add_argument(
        "--since",
        metavar = "YYYY-MM-DD",
        help    = "Inclusive lower bound for commit date",
    )
    mode_group.add_argument(
        "--branch",
        nargs   = "?",
        const   = "__CURRENT__",
        default = None,
        metavar = "BRANCH",
        help    = "Range = merge-base(BASE, BRANCH)..BRANCH. BRANCH defaults to current branch.",
    )

    parser.add_argument(
        "--until",
        metavar = "YYYY-MM-DD",
        help    = "Inclusive upper bound for commit date (default: today)",
    )
    parser.add_argument(
        "--base",
        default = "main",
        help    = "Base ref for --branch mode (default: main)",
    )

    # Filters
    parser.add_argument(
        "--include-merges",
        action = "store_true",
        help   = "Include merge commits (default: exclude)",
    )
    parser.add_argument(
        "--author",
        metavar = "EMAIL",
        help    = "Filter by commit author email (passed to git log --author; matches as substring/regex per git)",
    )

    # Output
    parser.add_argument(
        "--output",
        choices = [ "console", "json", "csv" ],
        default = "console",
        help    = "Output format (default: console)",
    )
    parser.add_argument(
        "--save-output",
        metavar = "PATH",
        help    = (
            "Write to file. For --output csv, the default path is mode-aware: "
            "in --branch mode → {project_root}/io/git-loc-delta/{repo}-{branch-slug}-loc-delta.csv "
            "(stable per-branch filename for daily-overwrite workflow); "
            "in --today / --since/--until mode → {project_root}/io/git-loc-delta/{YYYY-MM-DD}-loc-delta.csv "
            "(date-stamped for archival)."
        ),
    )

    parser.add_argument( "-v", "--verbose", action="store_true",  help="Echo git commands + per-commit progress to stderr" )
    parser.add_argument(       "--debug",   action="store_true",  help="Verbose + full tracebacks on failure" )

    return parser


def _resolve_mode( args ) -> str:
    """
    Resolve which mode the user selected based on flag combinations.

    Ensures:
        - Returns one of: "today", "explicit", "branch"
        - "today" is the default when no range flags are set
    """
    if args.branch is not None: return "branch"
    if args.since is not None or args.until is not None: return "explicit"
    return "today"


def _default_csv_path( mode: str, repo_path: str, branch: Optional[str] ) -> str:
    """
    Return the default CSV save path.

    The default filename pattern is mode-aware AND the base directory is
    target-aware. The CSV belongs to the repo being analyzed, NOT to the
    caller's project — so when `--repo-path` resolves to a directory other
    than the Lupin tree, the CSV lands under THAT directory's `io/` tree.

    Target-root resolution uses `git rev-parse --show-toplevel` from the
    supplied path so the CSV always lands at the repo's ROOT directory's
    `io/` tree, regardless of which subdir the user invoked from. Fallback:
    if the path is not a git repository, use `os.path.abspath(repo_path)`
    directly.

    - **branch mode** → `{target_repo_root}/io/git-loc-delta/{repo}-{branch-slug}-loc-delta.csv`
      (stable per-branch filename; daily reruns overwrite in place until merge)
    - **today / explicit mode** → `{target_repo_root}/io/git-loc-delta/{YYYY-MM-DD}-loc-delta.csv`
      (date-stamped; daily reruns produce a dated history)

    Bug-fix arc 2026-05-16:
    1. **Filed by Tiberius 🌑 session `b714e138`**: the original implementation
       used `cu.get_project_root()` as the base, which always resolves to
       LUPIN_ROOT. Cross-repo invocations dumped CSVs into Lupin's `io/`
       tree instead of the target repo's tree.
    2. **First-pass fix regression caught at live-test**: using
       `os.path.abspath(repo_path)` worked for cross-repo but broke the
       in-tree case when the user invoked from a subdir (cwd=`lupin/src/`,
       `--repo-path .` → CSV at `lupin/src/io/git-loc-delta/` instead of
       `lupin/io/git-loc-delta/`).
    3. **Final fix**: `git rev-parse --show-toplevel` resolves to the actual
       repo root regardless of which subdir was supplied. Matches Tiberius's
       workaround in `workflow/session-end.md` §6.2 (he uses the same git
       command in his explicit `--save-output` plumbing).

    Requires:
        - mode is one of: "today", "explicit", "branch"
        - repo_path is a string pointing at a directory (relative or absolute)
        - branch is the resolved branch name (only required for branch mode)

    Ensures:
        - Returns an absolute path under `{git_toplevel(repo_path)}/io/git-loc-delta/`
          when the path is inside a git repo, else `{abspath(repo_path)}/io/git-loc-delta/`
        - Branch names containing `/` are slugified (`/` → `-`) so they
          form valid filename segments
        - Never raises (subprocess failures fall back to abspath)
    """
    import os
    import subprocess
    from datetime import date

    target_path = os.path.abspath( repo_path )
    target_root = target_path
    try:
        result = subprocess.run(
            [ "git", "rev-parse", "--show-toplevel" ],
            capture_output = True,
            text           = True,
            timeout        = 5,
            cwd            = target_path,
        )
        if result.returncode == 0:
            resolved = result.stdout.strip()
            if resolved:
                target_root = resolved
    except Exception:
        # `git` missing, path not a repo, etc. — fall back to abspath
        pass

    base_dir = os.path.join( target_root, "io", "git-loc-delta" )

    if mode == "branch" and branch:
        repo_name   = os.path.basename( target_root ) or "repo"
        branch_slug = branch.replace( "/", "-" )
        return os.path.join( base_dir, f"{repo_name}-{branch_slug}-loc-delta.csv" )

    today = date.today().isoformat()
    return os.path.join( base_dir, f"{today}-loc-delta.csv" )


def main( argv: Optional[list] = None ) -> int:
    """
    CLI entry point. Returns an exit code.

    Ensures:
        - Returns 0 on success, 1 on GitLocDeltaError, 2 on argparse error
        - In --debug mode, full tracebacks are printed for failures
    """
    parser = create_parser()
    args   = parser.parse_args( argv )

    mode = _resolve_mode( args )

    branch_arg = None
    if mode == "branch":
        # __CURRENT__ sentinel means "use current branch" (--branch with no value)
        branch_arg = None if args.branch == "__CURRENT__" else args.branch

    try:
        analyzer = GitLogLocDeltaAnalyzer(
            repo_path      = args.repo_path,
            mode           = mode,
            branch         = branch_arg,
            base           = args.base,
            since          = args.since,
            until          = args.until,
            include_merges = args.include_merges,
            author         = args.author,
            debug          = args.debug,
            verbose        = args.verbose,
        )
        result = analyzer.analyze()
    except DateRangeError as e:
        # Graceful empty output for empty ranges (AC17): print the banner and exit 0
        # only for the "no commits / merge-base == HEAD" subcase. Other invalid
        # ranges (e.g. since > until) are still errors.
        if e.branch is not None and "Empty rev-range" in str( e ):
            print( "No commits in range." )
            return 0
        print( f"Error: {e}", file=sys.stderr )
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    except GitCommandError as e:
        print( f"Git error: {e}", file=sys.stderr )
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    except GitLocDeltaError as e:
        print( f"Error: {e}", file=sys.stderr )
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

    # Emit per --output
    if args.output == "console":
        text = format_console(
            daily     = result["daily"],
            summary   = result["summary"],
            since     = result["since"],
            until     = result["until"],
            branch    = result["branch"],
            rev_range = result["rev_range"],
        )
        if args.save_output:
            with open( args.save_output, "w" ) as f:
                f.write( text )
            if args.verbose: print( f"Saved console output to {args.save_output}", file=sys.stderr )
        else:
            print( text )
        return 0

    if args.output == "json":
        js = format_json(
            daily     = result["daily"],
            summary   = result["summary"],
            since     = result["since"],
            until     = result["until"],
            branch    = result["branch"],
            rev_range = result["rev_range"],
            repo_path = result["repo_path"],
        )
        if args.save_output:
            with open( args.save_output, "w" ) as f:
                f.write( js )
            if args.verbose: print( f"Saved JSON output to {args.save_output}", file=sys.stderr )
        else:
            print( js )
        return 0

    if args.output == "csv":
        csv_path = args.save_output or _default_csv_path(
            mode      = mode,
            repo_path = args.repo_path,
            branch    = result["branch"],
        )
        rows = write_csv( result["by_type"], path=csv_path, debug=args.debug )
        print( f"Wrote {rows} rows to {csv_path}" )
        return 0

    # Shouldn't reach — argparse validates --output choices
    print( f"Unknown --output value: {args.output!r}", file=sys.stderr )
    return 1


if __name__ == "__main__":
    sys.exit( main() )
