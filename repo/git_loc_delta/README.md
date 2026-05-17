# Daily LoC Delta — `cosa.repo.git_loc_delta`

Per-day breakdown of lines-of-code adds/deletes from `git log --numstat`. Sister
tool to [`branch_analyzer`](../branch_analyzer/): where `branch_analyzer`
answers "what did this whole branch change," `git_loc_delta` answers
"what changed when."

| | `branch_analyzer` | `git_loc_delta` (this tool) |
|---|---|---|
| **Question** | "What does this branch differ from main by?" | "What did I do on each day of this branch?" |
| **Driver** | `git diff base...head` (3-dot) | `git log --numstat` (per-commit walk) |
| **Granularity** | Branch-total (single bucket) | Per-(date, file_type) buckets + per-day totals |
| **Output formats** | Console, JSON, Markdown | Console, JSON, **CSV** (tidy-long, pivot-friendly) |
| **Use case** | One-shot branch summary | Daily activity log + end-of-branch summary |

The two tools are designed to be used together: `git_loc_delta` for daily
ritual + branch progression, `branch_analyzer` for the final PR narrative.

---

## Quick Start

```bash
# From the Lupin src/ directory (so cosa is importable):
cd /mnt/DATA01/include/www.deepily.ai/projects/lupin
export PYTHONPATH=src:$PYTHONPATH

# Today's commits (default mode)
python -m cosa.repo.run_git_loc_delta

# Whole current branch (vs main) — the most common invocation
python -m cosa.repo.run_git_loc_delta --branch

# CSV export for the current branch — overwrites in place each day
python -m cosa.repo.run_git_loc_delta --branch --output csv

# Run against the CoSA submodule
python -m cosa.repo.run_git_loc_delta --repo-path src/cosa --branch
```

Output for `--branch` mode lands at:

```
{project_root}/io/git-loc-delta/{repo}-{branch-slug}-loc-delta.csv
```

For example: `io/git-loc-delta/lupin-wip-v0.1.7-spit-and-polish-loc-delta.csv`.

The filename is stable across daily reruns on the same branch — each
invocation **overwrites** the same file with the full branch-to-date snapshot.

---

## Use Case A — End-of-Day Daily Ritual

**Scenario**: You're working on a feature branch. At the end of each session,
you want a running record of "what changed when" that grows day-by-day as you
work. When the branch eventually lands and gets PR'd, you have a complete
day-by-day trace of the work for the PR description, your own log, or simple
velocity tracking.

### Daily command

```bash
python -m cosa.repo.run_git_loc_delta --branch --output csv
```

That's it. Run this at the end of each work session.

### What happens

- The tool walks `git log --numstat` from `main..<current-branch>` (everything
  on your branch not yet on `main`)
- It buckets every file change by `(date, file_type)` and rolls up per-day
  totals
- It writes the result to a **stable per-branch filename** that overwrites
  cleanly each run: `{repo}-{branch-slug}-loc-delta.csv`
- Each subsequent day, you have a complete trace from day 1 of the branch
  through today

### Suggested integration into your session-end workflow

Add this to your `/plan-session-end` ritual or just to a shell alias:

```bash
alias loc-snapshot='python -m cosa.repo.run_git_loc_delta --branch --output csv'
```

Then at end of each session:

```bash
loc-snapshot
git add io/git-loc-delta/*.csv  # optional — version-control the trace
git commit -m "[LUPIN] Session-end LoC snapshot"
```

### Running against a submodule

If your work touches the CoSA submodule, run a second snapshot against it:

```bash
python -m cosa.repo.run_git_loc_delta --repo-path src/cosa --branch --output csv
```

You'll get a separate CSV: `cosa-<branch>-loc-delta.csv`. The two files
together capture both halves of your work.

---

## Use Case B — End-of-Branch Pre-PR Summary

**Scenario**: Your branch is done and you're about to open the PR. You want
a final summary table to:

1. Eyeball the work for sanity ("did I accidentally delete 5,000 lines on day 3?")
2. Paste a digest into the PR description so reviewers can see the day-by-day
   shape of the work
3. Have a permanent CSV record of the branch for post-merge archival

### The summary command

```bash
python -m cosa.repo.run_git_loc_delta --branch
```

Console output shape:

```
─────────────────────────────────────────────────────
  Daily LoC Delta
  Branch: wip-v0.1.7-2026.04.22-spit-and-polish-for-cjflow-tfe-and-bfe
  Range: main..wip-v0.1.7-…
─────────────────────────────────────────────────────

Daily Totals
  Date            Added   Deleted      Net   Files   Commits
  2026-04-23       3112       355 +   2757      25         5
  2026-04-24       2471       298 +   2173      30         7
  …
  TOTAL          147999     13171 + 134828     532       216

By Date × File Type
  Date         File Type         Added   Deleted   Files   Commits
  2026-04-23   markdown           3109       352      20         5
  2026-04-23   other                 3         3       5         2
  …
```

### Pasting into the PR description

The console table works inside a fenced code block in GitHub markdown:

````markdown
## Branch LoC Delta

```
Daily Totals
  Date            Added   Deleted      Net   Files   Commits
  2026-04-23       3112       355 +   2757      25         5
  …
  TOTAL          147999     13171 + 134828     532       216
```
````

(A future enhancement could add `--output markdown` that emits a GitHub-native
pipe-table — see "Future Enhancements" below.)

### Final CSV snapshot

Your daily CSV from Use Case A **is already your final snapshot** — same file,
last write. Optionally archive it post-merge:

```bash
mv io/git-loc-delta/lupin-<branch>-loc-delta.csv \
   io/git-loc-delta/archive/lupin-<branch>-merged-$(date +%F).csv
```

---

## CLI Reference

```
python -m cosa.repo.run_git_loc_delta [OPTIONS]

  --repo-path PATH         Repo to analyze (default: cwd)

  Date range (mutually exclusive):
  --today                  (Default) Commits since today 00:00 local
  --since YYYY-MM-DD       Inclusive lower bound
  --branch [BRANCH]        merge-base(BASE, BRANCH)..BRANCH
                           BRANCH defaults to current branch
  --until YYYY-MM-DD       Inclusive upper bound
  --base REF               Base ref for --branch mode (default: main)

  Filters:
  --include-merges         Include merge commits (default: exclude)
  --author EMAIL           Filter by commit author email
                           (passed to git log --author; substring/regex per git)

  Output:
  --output FORMAT          console | json | csv (default: console)
  --save-output PATH       Write to file. For --output csv:
                           --branch mode default → io/git-loc-delta/{repo}-{branch-slug}-loc-delta.csv
                           today / explicit mode → io/git-loc-delta/{YYYY-MM-DD}-loc-delta.csv

  -v, --verbose            Echo git commands + per-commit progress to stderr
  --debug                  Verbose + full tracebacks
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (including the "no commits in range" graceful-empty case) |
| `1` | Git failure (`GitCommandError`) or invalid date range (`DateRangeError`) |
| `2` | Argument parse error (raised by `argparse` on bad flags) |

---

## Output Formats

### Console (default)

Two tables: daily totals + by date × file type. Suitable for terminal viewing
and pasting into PR descriptions inside fenced code blocks.

### JSON (`--output json`)

Single nested dict for programmatic consumption:

```json
{
  "since": "2026-04-23",
  "until": null,
  "branch": "wip-v0.1.7-spit-and-polish-…",
  "rev_range": "main..wip-v0.1.7-…",
  "repo_path": ".",
  "summary": {
    "total_added": 147999,
    "total_deleted": 13171,
    "total_files": 532,
    "total_commits": 216,
    "total_days": 21,
    "net": 134828
  },
  "days": [
    {
      "date": "2026-04-23",
      "added": 3112,
      "deleted": 355,
      "files_touched": 25,
      "commits": 5,
      "by_file_type": [
        { "file_type": "markdown", "added": 3109, "deleted": 352, "files_touched": 20, "commits": 5 },
        { "file_type": "other",    "added":    3, "deleted":   3, "files_touched":  5, "commits": 2 }
      ]
    }
    // … one entry per date
  ]
}
```

### CSV (`--output csv`)

Tidy-long, pivot-friendly, **fixed 6-column schema regardless of file-type
cardinality**:

```csv
date,file_type,added,deleted,files_touched,commits
2026-04-23,markdown,3109,352,20,5
2026-04-23,other,3,3,5,2
2026-04-24,python,1455,34,9,6
2026-04-24,markdown,988,261,18,7
…
```

**Why long not wide**: new file types over time would add columns in a wide
format, breaking downstream consumers. Long is stable, pivotable in pandas
with `pivot_table(index="date", columns="file_type", values="added")`, and
graphs cleanly in matplotlib/Excel.

---

## Architecture

```
src/cosa/repo/
  run_git_loc_delta.py       # CLI entry (argparse, mode resolution, default-path logic)
  git_loc_delta/
    __init__.py              # Package exports
    analyzer.py              # GitLogLocDeltaAnalyzer — orchestrator + quick_smoke_test()
    git_log_parser.py        # Shells `git log --numstat`, yields per-file dicts
    daily_aggregator.py      # Buckets by (date, file_type); computes totals
    csv_writer.py            # Tidy-long CSV with stable schema
    report_formatter.py      # Console + JSON formatters
    exceptions.py            # GitLocDeltaError, DateRangeError; re-exports GitCommandError
    README.md                # ← you are here
```

### Reuse map (verified citations)

| Need | Source | Reuse strategy |
|---|---|---|
| File extension → file_type | `cosa/repo/branch_analyzer/file_classifier.py` | Import `FileTypeClassifier` (loaded via `ConfigLoader().load()`) |
| Custom git exception | `cosa/repo/branch_analyzer/exceptions.py` | Re-export `GitCommandError` |
| Subprocess pattern | `cosa/repo/branch_analyzer/git_diff_parser.py:115-150` | Same idiom: capture_output, text, timeout, GitCommandError translation |
| CLI scaffolding | `cosa/repo/run_branch_analyzer.py:69-156` | Same `create_parser()` + `main()` shape |
| `quick_smoke_test()` template | `cosa/repo/branch_analyzer/analyzer.py:279-407` | Same signature, `du.print_banner` headers, ✓/✗ indicators |
| CSV writing | `cosa/agents/todo_list_agent.py:89-90` | `pandas.to_csv(path, index=False)` — extended to disk writes |
| Project root resolution | `cosa/utils/util.py:626` | `cu.get_project_root()` |

---

## Testing

| Tier | Spec | Run |
|---|---|---|
| **Unit** | 4 tests in `src/tests/unit/test_git_loc_delta.py` (parser binary skip, aggregator bucketing, CSV schema stability, empty-input header-only) | `pytest src/tests/unit/test_git_loc_delta.py -v` |
| **Smoke** | `quick_smoke_test()` in `analyzer.py` — runs over current repo for last 7 days, 7 ✓/✗ checks | `python -m cosa.repo.git_loc_delta.analyzer` |
| **py_compile** | All 8 source files | `python -c "import py_compile; py_compile.compile('<file>', doraise=True)"` |
| **Import chain** | Public surface resolves cleanly | `python -c "from cosa.repo.git_loc_delta.analyzer import GitLogLocDeltaAnalyzer"` |
| **Live CLI** | Three modes against current repo | `--today`, `--branch`, `--branch --output csv` |

No server-side tests required — this is a pure CLI tool with no API/UI/WebSocket
surface.

---

## Edge Cases

| Edge case | Behavior |
|---|---|
| No commits in date range | Prints "No commits in range." banner, writes a header-only CSV when `--output csv`, exits 0 |
| `--branch` on the base branch itself (e.g. on `main` with `--base main`) | Same as no-commits case — empty rev-range, graceful exit 0 |
| Rename rows from `git log --numstat` | Counted as separate added/deleted entries per the numstat numbers (git's default rename detection is left on) |
| Submodule paths in the parent | `git log --numstat` does NOT descend into submodules by default; run against the submodule directly with `--repo-path src/cosa` for its commits |
| Timezone for `--today` | `--since today 00:00` uses git's interpretation, which respects the local timezone |
| Author filter (`--author EMAIL`) | Passed through to `git log --author=<value>` which matches as substring/regex |

---

## Future Enhancements

These are deliberately deferred from v1; track in `bug-fix-queue.md` or the
R&D plan doc when promoting:

- **`--output markdown`** — GitHub-native pipe-table format for pasting straight
  into PR descriptions (current console output works inside `<pre>` fences but
  isn't a markdown table proper)
- **`--classify-lines`** — code-vs-comment-vs-docstring split per day (requires
  fetching diff content per commit; expensive — opt-in flag)
- **Cumulative chart generation** — matplotlib plot of cumulative LoC over the
  branch's lifetime (currently you'd pipe the CSV into your own plotting)
- **Author breakdown view** — aggregate by author when multiple people work on
  the branch (currently `--author EMAIL` filters but doesn't multi-author group)
- **Archive command** — `--archive` flag that moves the per-branch CSV to
  `io/git-loc-delta/archive/{repo}-{branch}-merged-{YYYY-MM-DD}.csv` post-merge

---

## See Also

- **R&D plan** (design rationale + acceptance criteria + reuse audit + Pass 1 Fitness findings):
  `src/cosa/rnd/2026.05.16-daily-loc-delta-tool.md`
- **Sister tool**: [`cosa.repo.branch_analyzer`](../branch_analyzer/) — branch-total
  analysis (use for the PR-narrative "what does this branch change vs main")
- **CLAUDE.md `codebase-analysis` skill** — runs both tools in tandem when you
  invoke `/codebase-analysis`

---

**Author**: María 🌸 (session `3c9fce51`, 2026-05-16)
**Plan**: `src/cosa/rnd/2026.05.16-daily-loc-delta-tool.md`
**Status**: 🟢 SHIPPED — all 5 test tiers green; default filename mode-aware (branch-named for branch mode, date-stamped for archival modes)
