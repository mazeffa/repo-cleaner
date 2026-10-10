# reorganize

Migrate an existing, messy docs tree into the routing-table system. Never delete — archive.

## 1. Preconditions

Require a **clean git working tree** (`git status` shows nothing to commit) before touching
anything. If it's not clean, stop and ask the user to commit or stash first — never do it
for them. The pending changes are the user's work, often unrelated to the docs.

Never commit, stash, stage, or change git settings (including `.gitignore`) at any step.
Docs move with a plain file move (step 5), which git shows as a delete plus an untracked file
until the user stages it.

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
- Move superseded/duplicate docs into `docs/archive/` with a plain move (not `git mv`),
  prepending the banner:
  `> **Archived YYYY-MM-DD.** Superseded by \`docs/X.md\` — rationale, not instruction.`
- Rewrite survivors to remove what moved to the archive.
- Update the routing table with the new/changed rows.
- Add a log entry and, if any belief changed, a `D-NNN` entry.
- Run the checker; it must reach 0.

Apply all of this as **one uncommitted working-tree change**. Leave the result for the user
to review and commit themselves.

As you go, record exactly what this run touched: each **source** it moved or rewrote, and each
**destination** it created (including every new copy in `docs/archive/`). Step 7 undoes that
list and nothing else.

**On any move failure:** stop immediately. Report exactly what was applied so far, and
print the rollback commands (step 7). Do not continue past a failed move.

**On checker findings after all moves succeeded:** list them plainly. Offer the same
rollback. Never auto-fix a finding here — that's a `maintain`-shaped decision, not a
mechanical one.

## 6. Untracked files are never moved

Untracked files are inventoried in step 2 but this command never touches them — a clean-tree
precondition can't account for something untracked, and a rollback can't restore a manual
move of one. If an untracked file needs to move, tell the user and let them
`git add` + move it themselves.

## 7. Rollback

Undo only what step 5 recorded, in this order — never anything else in the tree, which holds
the user's other work (a `git reset --hard` would wipe it, so this command never runs one):

1. `git restore -- <each source it moved or rewrote>` — restores from the index, so changes
   the user staged stay.
2. Delete each destination it created, including the new copies in `docs/archive/`.
3. If any command fails, stop and print the exact commands still left to run by hand.

State these commands explicitly whenever offering rollback — don't make the user look them up.
Restoring this command's own edits is not one of the git actions the rules above rule out
(D-022).
