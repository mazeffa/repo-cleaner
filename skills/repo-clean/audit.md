# audit

Read-only. Report findings; make no edits.

## 1. Run the checker

If the plugin is installed in the target repo: `python scripts/tools/check_docs.py`.
Otherwise: `python <skill>/scripts/check_docs.py --root <repo>`.

## 2. Manual pass, beyond what the checker catches

- Topics discussed in the repo (issues, comments, commit messages) that have no routing-table
  row at all.
- A fact restated in 2+ living docs in different words (the checker's config-constant rules
  catch literal restatement of code constants; this catches paraphrased duplication the
  checker can't regex for).
- A log's last `State:` line that looks stale against recent `git log` activity.
- An `open` decision whose `Revisit:` trigger condition has clearly already been met.

## 3. Checker version drift

Compare the target repo's `scripts/tools/check_docs.py` `CORE_VERSION`/`CONFIG_VERSION`
(`python scripts/tools/check_docs.py --version`) against the plugin's copy
(`python <skill>/scripts/check_docs.py --version`). If they differ, report it as:
"target CORE_VERSION X, plugin CORE_VERSION Y" and print the exact re-sync command:
`cp <skill>/scripts/check_docs.py <repo>/scripts/tools/check_docs.py`.

## 4. Report

One line per finding: `path:line — issue — suggested owner`. Group checker findings
separately from the manual-pass findings. No edits, no confirmation prompts — audit only
reports.
