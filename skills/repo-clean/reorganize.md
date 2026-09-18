# reorganize

Migrate an existing, messy docs tree into the routing-table system. Never delete — archive.

## 1. Preconditions

Require a **clean git working tree** (`git status` shows nothing to commit) before touching
anything. If it's not clean, stop and ask the user to commit or stash first.

Record `HEAD` now — this is the rollback point for the whole run: `git rev-parse HEAD`.

## 2. Inventory

Every `.md`/`.html` outside `docs/archive/`: path, question it answers, `mtime`, line count.
Include untracked files in the inventory, but flag them clearly — untracked files are never
moved by this command (see step 6).

## 3. Map facts to owners, flag problems

Build a fact→owner map. Flag duplicates and contradictions by grepping for repeated numbers,
`D-NNN` ids, and rule phrases across files.

## 4. Migration table — this IS the dry run

Produce a table: `from | to | merge/archive/keep` plus any new routing-table rows this
implies. Nothing is written yet. Walk the user through it and get **explicit confirmation
per row, or an explicit "yes to all."** Do not proceed past this step without confirmation.

## 5. Apply — one working-tree transformation, no commits

Once confirmed:
- `git mv` superseded/duplicate docs into `docs/archive/`, prepending the banner:
  `> **Archived YYYY-MM-DD.** Superseded by \`docs/X.md\` — rationale, not instruction.`
- Rewrite survivors to remove what moved to the archive.
- Update the routing table with the new/changed rows.
- Add a log entry and, if any belief changed, a `D-NNN` entry.
- Run the checker; it must reach 0.

Apply all of this as **one uncommitted working-tree change** — don't commit between steps
(that would fire the pre-commit hook on an intermediate, half-migrated state). Leave the
result for the user to review and commit themselves.

**On any `git mv` failure:** stop immediately. Report exactly what was applied so far, and
print the rollback command (step 7). Do not continue past a failed move.

**On checker findings after all moves succeeded:** list them plainly. Offer the same
rollback. Never auto-fix a finding here — that's a `maintain`-shaped decision, not a
mechanical one.

## 6. Untracked files are never moved

Untracked files are inventoried in step 2 but this command never touches them — a clean-tree
precondition plus `git mv` can't act on something untracked, and `git reset --hard` won't
restore a manual move of one. If an untracked file needs to move, tell the user and let them
`git add` + move it themselves.

## 7. Rollback

Always: `git reset --hard <the HEAD recorded in step 1>`. State this command explicitly
whenever offering rollback — don't make the user look it up.
