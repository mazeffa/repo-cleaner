# Known defects

This file is authoritative for **what is broken and its status**.

Found 2026-09-18 by an adversarial pass against the checker: throwaway repos built to make
it crash, emit a wrong finding on valid input, or stay silent on input violating its own
documented rules. The bundled `--selfcheck` passed all 37 of its own assertions and caught
none of these — its fixtures were written by the same hand as the rules, so each proved its
rule *can* fire, and none proved a rule stays quiet when it should. The rebuilt selfcheck
(50 findings) now pairs every must-fire fixture with a must-not-fire one built from each
repro below.

`Status:` is `confirmed` (reproduced here), `reported` (found by the pass, not independently
reproduced), or `fixed` (with the commit that closed it). All 22 from that pass are fixed,
closed by commit `724dd50`. DEF-23, found later and by a different route, is fixed.

## Fixed 2026-09-19

### DEF-01 — Crash on a repo path containing non-ASCII
Status: fixed
Was: `git_root()`'s `subprocess.run` had no `encoding=`, so git's UTF-8 output was decoded
with the console code page and the resulting path didn't exist — traceback, exit 1, and the
pre-commit hook (which calls with no `--root`) could never run for a user whose home
directory has an accent.
Fix: `encoding="utf-8"` on the subprocess call; git absent or failing now falls back to
`cwd` instead of being fatal (git is optional); `main()` catches any exception and exits 2.

### DEF-02 — Any backticked command with a flag is reported as a missing path
Status: fixed
Was: `PATH_LIKE` allowed spaces and swallowed a whole command line, so a backticked
`scripts/tools/check_docs.py --selfcheck` (the command this repo's own README tells users to
run) was reported as a missing path.
Fix: a backticked span with whitespace is split on whitespace and each token is tested
alone (`path_tokens_from_span`); `CANDIDATE_TOKEN_RE` requires a whitespace-free token.

### DEF-03 — The documented per-rule disable does not exist
Status: fixed
Was: no rule read a rule-id `CONFIG` key, so `CONFIG["<rule-id>"] = None` changed nothing.
Fix: `GENERIC_RULES` is `(rule_id, fn)` pairs; `run_generic_rules` skips any id mapped to
`None` in the merged config.

### DEF-04 — The installed hook is not executable in this repo
Status: fixed
Was: `scripts/hooks/pre-commit` was mode 100644 in the index while the skill's copy was
100755, so a Unix clone silently skipped the hook.
Fix: `git update-index --chmod=+x scripts/hooks/pre-commit`; `init.md` step 7 does the same
after copying, only when `.git` exists.

### DEF-05 — Only the first line of a `Docs:` field is read
Status: fixed
Was: the `Docs:`/`Decisions:` regex was single-line, so a wrapped field (this repo's own
convention) was never actually checked past its first line.
Fix: `parse_fields()` continues a field's value onto following non-blank lines that don't
themselves start a field.

### DEF-06 — `--root` loads the local extension from the wrong directory
Status: fixed
Was: the local extension was imported from the script's own directory rather than the
target repo's, so the installed copy and the plugin copy could reach different verdicts
against the same repo.
Fix: `local_module_dir(root)` — the script's own directory when the script is itself inside
`root`, otherwise `<root>/scripts/tools/`. `--init-config` writes there.

### DEF-07 — One decision superseding two is reported as asymmetric
Status: fixed
Was: only the first id in a `Supersedes:`/`Superseded-by:` list was captured.
Fix: both fields parse every id (`id_re.findall`); symmetry is checked per pair.

### DEF-08 — `Superseded-by:` written in prose is parsed as the field
Status: fixed
Was: fields were searched across the whole entry text, so a sentence mentioning the field
name was read as the field itself.
Fix: `parse_fields()` only starts a field at column 0 or after 2+ spaces on an
already-started field line; a single space before a colon-word is prose.

### DEF-09 — Two rules disagree about whether the heading is part of the entry
Status: fixed
Was: `decisions-integrity` read fields from the body only; `open-questions-sync` still
searched the whole entry including the heading.
Fix: every rule reads fields from `split_entries()`'s body only.

## Fixed 2026-09-19 (false positives)

### DEF-10 — Fenced code blocks are treated as document content
Status: fixed
Was: no rule was fence-aware, so an example inside a fenced block (a TODO comment, a
decision or log heading) tripped the rule that documents its own grammar.
Fix: `read_doc()` blanks fenced-block interiors (line numbers preserved); every rule reads
through it.

### DEF-11 — Non-path tokens in `Docs:` are resolved as paths
Status: fixed
Was: a parenthetical section number, a version string, a URL, or a Windows separator each
produced a "references missing" finding.
Fix: `docs_field_paths()` requires a slash-free token to end in `.md`; `none`, URLs, and
Windows drive paths are skipped silently.

### DEF-12 — The outside-repo-path regex misfires and misses
Status: fixed
Was: fired on a word followed by a colon and a backslash and on a drive-letter pattern
inside a regex example; missed Git Bash style absolute paths.
Fix: `outside_path_re` requires the drive letter not be preceded by a word/backslash
character and be followed by a word character; added `/<letter>/Users/`, `/<letter>/home/`.

### DEF-13 — Archive banner scanning is shallow and hits frozen prose
Status: fixed
Was: only the archive's top level was scanned, and any line containing a banner keyword —
even ordinary historical prose — was checked.
Fix: `rglob` finds nested archive dirs; only consecutive blockquote (`>`) lines are joined
and scanned.

### DEF-14 — Research fields take the first match anywhere in the file
Status: fixed
Was: prose above the header containing a field name won over the real header; nested
research subdirectories were skipped.
Fix: `parse_fields()` (column/spacing rule, not "anywhere") plus `rglob`.

### DEF-15 — Routing coverage counts any backtick in the routing file
Status: fixed
Was: a doc mentioned anywhere in the routing file passed, including outside the table, and
a leading `./` never matched.
Fix: only backticks on table rows (lines starting with `|`) count; `./` is normalized; the
finding text now says "not referenced in `<routing file>`'s table".

## Fixed 2026-09-19 (documentation contradicted code)

### DEF-16 — README claims a rule that does not exist
Status: fixed
Was: README stated the checker catches literal restatement of code constants; no such rule
exists.
Fix: README and `maintain.md` now say the checker verifies structure, not meaning, and
cannot compare docs to code or to each other.

### DEF-17 — README says maintain and reorganize install the checker
Status: fixed
Was: neither does; `maintain` only reports version drift and prints a copy command.
Fix: README now says only `init` installs, and only copies the pre-commit hook when `.git`
exists.

### DEF-18 — Documented log grammar is unenforced
Status: fixed
Was: a `State:` line on a non-last entry passed, and `(N)` numbering was never checked.
Fix: `diary-grammar` now enforces `(N)` numbering (first entry of a date unnumbered, then
`(2)`, `(3)`, ...) alongside `State:` on the last entry only. `example-layout.md` corrected
to match.

### DEF-19 — `--selfcheck` only works as the first argument
Status: fixed
Was: passed after another flag it was ignored; unknown flags were accepted silently.
Fix: CLI rebuilt on `argparse`; `--selfcheck` works anywhere in argv, unknown flags exit 2.

### DEF-20 — The config starter misstates how a version mismatch is reported
Status: fixed
Was: `LOCAL_STARTER` said a `CONFIG_VERSION` mismatch is a finding; the code reports it as
an internal error with a different exit code.
Fix: `LOCAL_STARTER` now says "internal error, exit 2".

### DEF-21 — `--root` pointed at a file crashes
Status: fixed
Was: only existence was checked, not that the target is a directory; traceback, exit 1.
Fix: `_resolve_root()` checks `is_dir()` and exits 2 with a message otherwise.

### DEF-22 — Directory paths and case differences are not checked
Status: fixed
Was: a backticked path ending in a separator was skipped, so a missing directory passed; a
case mismatch passed on a case-insensitive filesystem.
Fix: `exists_exact()` walks path segments through `os.listdir()` (case-sensitive on Windows
too); a trailing separator requires the final segment to be a real directory.

## Fixed 2026-09-19 (build identity)

### DEF-23 — `CORE_VERSION` does not identify a build, so drift detection cannot work
Status: fixed
Found 2026-09-19 by a user comparing shipped releases in the plugin cache (path in the
repro below) against a target repo's installed copy.

Was: four shipped releases claimed `CORE_VERSION = "1.0.0"` with different code:

| release | CORE_VERSION | `check_*` rules | `check_research_fields` | md5 |
|---|---|---|---|---|
| 0.1.0 | 1.0.0 | 11 | no | a65648d4 |
| 0.1.1 | 1.0.0 | 11 | no | cb62feb9 |
| 0.1.2 | 1.0.0 | 11 | no | 3fb9b33f |
| 0.2.0 | 1.0.0 | 12 | yes | ec77cd83 |
| 0.2.2 | 1.1.0 | 12 | yes | — |
| 0.3.0 | 1.2.0 | 12 | yes | 9bafef37 |
| 0.3.1 | 1.2.0 | 12 | yes | 9bafef37 |
| 0.3.2 | 1.2.0 | 12 | yes | dda3df32 |
| 0.3.3 | 1.3.0 | 12 | yes | 6f7504ae |

0.3.2 reproduced this defect's headline even after adding `core_digest()`: it and 0.3.1
both print `CORE_VERSION 1.2.0` with different bytes (`9bafef37` vs `dda3df32`), and
nothing ran the comparison unasked.

0.1.2 → 0.2.0 added a whole rule without bumping the version; the other three 1.0.0 builds
differ byte-for-byte. A target repo (core copied in 2026-09-18) is a fifth distinct
"1.0.0" — 11 rules, md5 295453c9, matching none of the four.

Repro:

```
cd ~/.claude/plugins/cache/repo-clean/repo-clean
for v in 0.1.2 0.2.0; do
  f="$v/skills/repo-clean/scripts/check_docs.py"
  echo "$v $(grep -m1 'CORE_VERSION *=' $f) rules=$(grep -cE '^def check_' $f)"
done
```

What it breaks. `maintain.md` step 7 is the plugin's only drift detection and it compares
version strings, so a repo on the 0.1.x core and one on the 0.2.0 core both read "1.0.0" and
compare equal — step 7 reports in-sync with a whole rule missing. It is sound only across
the 1.0.0→1.2.0 boundary, the case it was least needed for. Nothing else reads the version:
`hooks/session_start.py:18` tests `checker_path(cwd) is None`, existence only, and
`_lib.run_checker()` then runs whatever stale copy it finds, with `scripts/hooks/pre-commit`
enforcing it. A repo three releases behind keeps a green Stop hook and a green pre-commit
gate; the only signal is prose that fires when a human types `/repo-clean maintain`.

`CONFIG_VERSION` does not cover the gap either: it has been `1` from 0.1.0 through 0.3.1,
including across `check_research_fields`, which requires `Status:`/`Date:` headers that
target `docs/research/*.md` files did not previously need. Neither number tells a repo its
docs now need structure they didn't need before.

Effect on re-sync, measured on one unchanged target repo: core 1.0.0 exits 0, core 1.2.0
reports 44 findings — 14 from the added research-fields rule, 4 from the DEF-18
diary-grammar change (now rejects `(1)` on the first entry of a date), the rest from changed
`CONFIG` defaults (`exempt_dirs` dropped that repo's council directory,
`path_suppressed_prefixes` dropped `data/ops/`, `path_cmd_prefixes` dropped `Rscript ` and
`uv run python -m ops`, `outside_path_re` widened). Zero are doc regressions. The user sees
a 44-finding wall and a blocked commit with nothing saying these are rule changes, not rot.

Fix: `core_digest()` hashes the checker's own source (newlines normalized, so a CRLF
checkout and an LF one agree) and `--version` prints `CORE_VERSION 1.3.0+<8hex>
(CONFIG_VERSION 1)`. `maintain.md` step 7 compares the full `--version` line, digest
included, instead of the version strings alone. That closed the mechanism but not the
symptom: 0.3.2 shipped it and still reproduced the headline, because nothing ran the
comparison unasked — the only signal was prose that fires when a human types
`/repo-clean maintain`. `hooks/_lib.py:checker_drift()` now computes the same comparison
itself (it doesn't need `--version` from the target; it hashes both checkers directly, so
it also works against pre-0.3.2 targets that print no digest) and reports direction —
behind, ahead, or same version with different bytes. `session_start.py` prints it once per
distinct drift state, as a finding for the user to act on, not an instruction; `stop.py`
adds a short note to every block reason while the drift persists, since a user who ignores
the once-per-state SessionStart line would otherwise see nothing again. `CORE_VERSION` is
bumped to 1.3.0 here — not because a rule changed, but because 1.2.0 already named two
different builds (0.3.1 without a digest, 0.3.2 with one) and 1.3.0 is the label 0.3.2's
checker should have had.

What is still true after this fix: `run_checker()` executes whatever checker the target
repo actually has, so a stale ruleset is what the pre-commit gate enforces until the user
re-syncs it. The fix makes the hooks say so instead of staying silent about it; it does not
make the gate itself version-aware. Cost of saying so: the SessionStart line is silent
after the first time a given drift state is seen, but the Stop clause is ungated and
repeats on every block for as long as the repo stays un-synced — chosen so the nag can't be
outwaited by retrying Stop; if that turns out to be the complaint, revisit it there.

Remaining ideas from the original fix directions are improvements, not part of this
defect: bumping `CONFIG_VERSION` when a rule change requires new target-doc structure and
naming the responsible rule ids; offering the re-sync `cp` instead of just printing it.

