#!/usr/bin/env python3
r"""Generic docs hygiene checker. Stdlib only. There is no per-project add-on file
(D-022) - the checker never runs project code.

Exit 0 on success, printing one line stating that shape was verified and content
was not. Exit 1 on doc findings, exit 2 when there is nothing to check (no `.repo-clean` home
at or above the cwd, or a bad --root) or on any unhandled exception. Prints one line per
finding either way. With no --root, the home is the nearest `.repo-clean` marker at or above
the current folder.

Rules (stable string ids, used in inline suppression comments; D-029(7)):
  decisions-integrity   Unique IDs in the decision register, closed-vocabulary Status
                         read from the entry body only, symmetric supersession
                         (every id in Supersedes:/Superseded-by: is checked, not just
                         the first).
  log-fields-resolve    The newest log entry's 'Decisions:'/'Docs:' fields resolve to real
                         ids/real .md paths; a field's value may wrap onto following lines.
                         Older entries are history: the files they name may have moved.
                         Only .md targets are checked (D-029(5)) - a missing dated output
                         file or a renamed script is routine, not a broken doc link.
  outside-repo-paths    No out-of-repo path in a living doc. The default catches paths under
                         a home folder: C:\Users\, ~, /home, /Users, /root, and Git Bash
                         /<letter>/Users or /<letter>/home (D-029(4)).
  paths-exist           Backtick-quoted .md paths in living docs must exist, checked
                         case-exactly regardless of OS; a trailing '/' requires a directory.
                         Non-.md targets (scripts, data, generated output) are not checked
                         (D-029(5)).
  log-grammar           At least one dated entry; log heading grammar; every entry carries
                         Decisions: and Docs:. State:/Next: lines are history, not checked
                         (D-029(6)).
  work-table            docs/WORK.md exists and every row has an ID, a Type (bug/task/idea)
                         and a Status (open/done/dropped).
  routing-coverage      Every living doc is referenced in the routing file's table
                         (table rows only, a leading './' normalized).

Fenced code blocks (```...```) are blanked before any rule reads a document, so an example
heading or field name inside a fence is never mistaken for real content.

Suppression:
  1. EXEMPT_DIRS                - whole directories, always exempt.
  2. ROUTING_EXEMPT_TOPDIRS     - docs/<topdir> exempt from routing-coverage only.
  3. PATH_SUPPRESSED_PREFIXES   - generated output, never a doc link (D-029(5)).
  4. <!-- check-docs: ignore <rule-id> --> - on a line, for outside-repo-paths and
     paths-exist; anywhere in a docs/ file, exempts that file from routing-coverage.
     The other rules have no in-text escape.
"""
import argparse
import os
import re
import sys
from pathlib import Path

LIVING_ROOTS = ("CLAUDE.md", "README.md")
DOCS_DIR = "docs"
EXEMPT_DIRS = ("docs/archive", "docs/log")
DECISIONS_FILE = "docs/DECISIONS.md"
WORK_FILE = "docs/WORK.md"
WORK_TYPES = ("bug", "task", "idea")
WORK_STATUSES = ("open", "done", "dropped")
ID_PREFIX = "D-"
STATUS_VOCAB = ("active", "superseded", "rejected")
LOG_DIR = "docs/log"
ROUTING_FILE = "CLAUDE.md"
ROUTING_EXEMPT_TOPDIRS = ("archive", "log", "research")
OUTSIDE_PATH_RE = (
    r"(?<![\w\\])[A-Za-z]:\\[Uu]sers\\"   # a Windows home folder (D-029(4)); other drives are shared
    r"|~[\\/]"                           # ~/ or ~\
    r"|(?:^|[\s`(\[])/(?:home|Users|root)/"          # unix absolute home dirs
    r"|(?:^|[\s`(\[])/[A-Za-z]/(?:Users|home)/"      # Git Bash /c/Users, /c/home
)
PATH_SUPPRESSED_PREFIXES = ("output/",)  # analytics homes: generated output is not a doc link


def scan_doc(p):
    """Read a doc, never raising on a stray non-UTF-8 byte (a mojibake char just fails
    some other rule), with every fenced code block's interior (and its ``` delimiter
    lines) blanked out. Line numbers are preserved so callers can still report them.
    Returns (text, line of a fence opener that is never closed, or None); the text stays
    blanked to the end, so example headings inside it never fire a rule."""
    text = p.read_text(encoding="utf-8", errors="replace")
    out = []
    opener = None
    fence_re = re.compile(r"^\s*```")
    for n, line in enumerate(text.split("\n"), 1):
        if fence_re.match(line):
            opener = None if opener else n
            out.append("")
        elif opener:
            out.append("")
        else:
            out.append(line)
    return "\n".join(out), opener


def read_doc(p):
    return scan_doc(p)[0]


def parse_fields(lines):
    """Parse `Key: value` fields out of a block of lines (typically an entry body).

    A field starts either at column 0 of a line (`Key:`) or after 2+ spaces later on a
    line that already started a field (`Key: value   Key2: value2`). A single space
    before a colon-word does not start a new field, so prose like "we considered
    Superseded-by: X but rejected it" never becomes a real field. A following non-blank
    line that does not itself start a field continues the previous field's value (so a
    field can wrap across lines). A blank line ends the current field.
    """
    field_start_re = re.compile(r"^([A-Z][\w-]*):[ \t]?")
    field_inline_re = re.compile(r"  +([A-Z][\w-]*):[ \t]?")
    fields = {}
    current = None
    for raw in lines:
        line = raw.rstrip("\r")
        if line.strip() == "":
            current = None
            continue
        m = field_start_re.match(line)
        if not m:
            if current is not None:
                fields[current] = (fields[current] + " " + line.strip()).strip()
            continue
        starts = [(0, m.group(1), m.end())]
        for im in field_inline_re.finditer(line):
            starts.append((im.start(1), im.group(1), im.end()))
        for idx, (pos, key, val_start) in enumerate(starts):
            val_end = starts[idx + 1][0] if idx + 1 < len(starts) else len(line)
            fields[key] = line[val_start:val_end].strip()
        current = starts[-1][1]
    return fields


def split_entries(text, heading_re):
    """Split text into (heading_line, body_lines) pairs at lines matching heading_re
    (matched against each line individually). Body excludes the heading line itself.
    Content inside fenced code blocks is already blanked by read_doc(), so an example
    heading inside a fence never starts a fake entry."""
    lines = text.split("\n")
    entries = []
    cur_head = None
    cur_body = []
    for line in lines:
        if heading_re.match(line):
            if cur_head is not None:
                entries.append((cur_head, cur_body))
            cur_head = line
            cur_body = []
        elif cur_head is not None:
            cur_body.append(line)
    if cur_head is not None:
        entries.append((cur_head, cur_body))
    return entries


SUPPRESS_RE = re.compile(r"<!--\s*check-docs:\s*ignore\s+([\w-]+)\s*-->")
PLACEHOLDER = ("<", "*", "..", "path/to", "YYYY", "{", "|")
CANDIDATE_TOKEN_RE = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)+/?$")


def line_ignored(line, rule_id):
    return any(m.group(1) == rule_id for m in SUPPRESS_RE.finditer(line))


class Ctx:
    """One run: the home's root path and the absolute paths derived from the constants."""

    def __init__(self, root):
        self.root = root
        self.docs = root / DOCS_DIR
        self.exempt_dirs = {root / d for d in EXEMPT_DIRS}
        self.decision_ids = None  # set by check_decisions_integrity

    def is_exempt(self, p):
        return any(d in p.parents or d == p for d in self.exempt_dirs)


def routing_table_paths(ctx):
    """Every backticked span in a routing-table row, a leading './' stripped - the one reader
    of the table's format. The caller checks that ROUTING_FILE exists."""
    out = []
    for line in read_doc(ctx.root / ROUTING_FILE).splitlines():
        if line.strip().startswith("|"):
            for span in re.findall(r"`([^`]+)`", line):
                rel = span.strip()
                out.append(rel[2:] if rel.startswith("./") else rel)
    return out


def routed_docs(ctx):
    """Every existing .md a routing-table row names (D-020) - a file the table calls
    authoritative is one the model will trust, so it is one the checker reads."""
    if not (ctx.root / ROUTING_FILE).is_file():
        return []
    return [ctx.root / rel for rel in routing_table_paths(ctx)
            if rel.endswith(".md") and exists_exact(ctx.root, rel) and not ctx.is_exempt(ctx.root / rel)]


def living_docs(ctx):
    files = [ctx.root / name for name in LIVING_ROOTS if (ctx.root / name).exists()]
    files += [p for p in ctx.docs.rglob("*.md") if not ctx.is_exempt(p)]
    seen = {f.resolve() for f in files}
    for p in routed_docs(ctx):
        if p.resolve() not in seen:
            seen.add(p.resolve())
            files.append(p)
    return files


def docs_plus_log(ctx, docs):
    files = list(docs)
    log_dir = ctx.root / LOG_DIR
    if log_dir.exists():
        files += sorted(log_dir.glob("*.md"))
    return files


def top_level_names(ctx):
    names = {p.name for p in ctx.root.iterdir()}
    names |= set(LIVING_ROOTS)
    return names


def exists_exact(root, rel_path):
    """Existence check that is case-sensitive even on a case-insensitive filesystem
    (Windows), by walking segments through os.listdir() instead of Path.exists(). A
    trailing '/' or '\\' requires the final segment to be a directory."""
    want_dir = rel_path.endswith("/") or rel_path.endswith("\\")
    parts = [seg for seg in re.split(r"[\\/]", rel_path) if seg not in ("", ".")]
    if not parts:
        return False
    cur = root
    for i, seg in enumerate(parts):
        try:
            names = os.listdir(cur)
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return False
        if seg not in names:
            return False
        cur = cur / seg
        if i == len(parts) - 1 and want_dir and not cur.is_dir():
            return False
    return True


def path_tokens_from_span(span):
    """A backticked span with no whitespace is one candidate token. A span with
    whitespace (a shell command, two paths joined by "and", ...) is split on
    whitespace and each token is tested on its own, so a flag or a second word never
    gets swallowed into what looks like one long "path"."""
    s = span.strip().strip("\"'")
    if not s:
        return []
    return s.split() if re.search(r"\s", s) else [s]


def candidate_path(ctx, token, known_roots):
    """Normalize a single whitespace-free token to a repo-relative path to check, or
    None to skip it. Only tokens that look confidently like a repo path are returned:
    whitespace-free, made of word/dot/dash segments joined by '/', with a real
    top-level name as the first segment."""
    s = token.strip().strip("\"'")
    if not s or any(x in s for x in PLACEHOLDER):
        return None
    if s.startswith(("http://", "https://")):
        return None
    s = re.sub(r":\d+(-\d+)?$", "", s.rstrip(":,.\"'()"))
    if not s or s.startswith(PATH_SUPPRESSED_PREFIXES):
        return None
    if not CANDIDATE_TOKEN_RE.match(s):
        return None
    if s.split("/", 1)[0] not in known_roots:
        return None
    return s


def docs_field_paths(ctx, value, known_roots):
    """Tokens out of a `Docs:` field value that look confidently like paths to
    documentation. Only a token ending in '.md' counts (D-029(5)): a version number,
    section number, script, data file, or generated output is skipped, since a missing
    dated output file or a renamed script is routine, not a broken doc link. 'none',
    URLs, and Windows drive paths are always skipped."""
    out = []
    for raw in re.split(r"[,\s]+", value.strip()):
        tok = raw.strip().strip(".,;()")
        if not tok or tok.lower() == "none":
            continue
        if "://" in tok:
            continue
        if re.match(r"^[A-Za-z]:[\\/]", tok):
            continue
        if not tok.lower().endswith(".md"):
            continue
        if "/" in tok:
            c = candidate_path(ctx, tok, known_roots)
            if c:
                out.append(c)
        else:
            out.append(tok)
    return out


# ---------------------------------------------------------------------------
# Generic rules
# ---------------------------------------------------------------------------

VERDICT_RE = re.compile(r"(?:^|\s)Verdict:", re.M)  # raw text: also catches 'Status: x Verdict: y'
DECISION_HEADING_RE = re.compile(rf"^## ({re.escape(ID_PREFIX)}\d+)\b.*$")


def decision_entries(text):
    """(id, heading, body lines, fields) for each `## D-NNN` entry of the decision register."""
    return [(DECISION_HEADING_RE.match(h).group(1), h, b, parse_fields(b))
            for h, b in split_entries(text, DECISION_HEADING_RE)]


def check_decisions_integrity(ctx, errors, docs):
    p = ctx.root / DECISIONS_FILE
    if not p.exists():
        errors.append(f"{DECISIONS_FILE}: file does not exist")
        ctx.decision_ids = set()
        return
    prefix = re.escape(ID_PREFIX)
    id_re = re.compile(prefix + r"\d+")
    text = read_doc(p)
    for n, line in enumerate(text.split("\n"), 1):
        m = re.match(rf"^(?:#|#{{3,}}) ({prefix}\d+)", line)
        if m:
            errors.append(f"{DECISIONS_FILE}:{n}: {m.group(1)}: decision heading must be '## {ID_PREFIX}NNN'")
    ids = set()
    verdict_ids = []
    superseded_by, supersedes = {}, {}
    for eid, _, body, fields in decision_entries(text):
        if eid in ids:
            errors.append(f"{DECISIONS_FILE}: duplicate id {eid}")
        ids.add(eid)
        status = fields.get("Status")
        if VERDICT_RE.search("\n".join(body)):
            verdict_ids.append(eid)
        if status == "open":
            errors.append(f"{DECISIONS_FILE}: {eid} Status: open is retired (D-029) - "
                          f"make it a {WORK_FILE} item, or decide it")
        elif status not in STATUS_VOCAB:
            errors.append(f"{DECISIONS_FILE}: {eid} bad/missing Status: {(status or '')!r}")
        sb_val = fields.get("Superseded-by", "")
        sp_val = fields.get("Supersedes", "")
        if status == "superseded" and not id_re.search(sb_val):
            errors.append(f"{DECISIONS_FILE}: {eid} is superseded but names no Superseded-by target")
        if sb_val:
            superseded_by[eid] = id_re.findall(sb_val)
        if sp_val:
            supersedes[eid] = id_re.findall(sp_val)
    if verdict_ids:
        errors.append(
            f"{DECISIONS_FILE}: {len(verdict_ids)} entries still carry Verdict: (retired, D-029): "
            f"{', '.join(verdict_ids)} - adopted: delete it; rejected and never in force: "
            f"Status: rejected; unresolved: a {WORK_FILE} item")
    reported_pairs = set()
    for eid, targets in superseded_by.items():
        for target in targets:
            if target not in ids:
                errors.append(f"{DECISIONS_FILE}: {eid} Superseded-by dangles at {target}")
            elif eid not in supersedes.get(target, []):
                pair = frozenset((eid, target))
                if pair not in reported_pairs:
                    reported_pairs.add(pair)
                    errors.append(f"{DECISIONS_FILE}: {eid}<->{target} supersession is not symmetric")
    for eid, targets in supersedes.items():
        for target in targets:
            if target not in ids:
                errors.append(f"{DECISIONS_FILE}: {eid} Supersedes dangles at {target}")
            elif eid not in superseded_by.get(target, []):
                pair = frozenset((eid, target))
                if pair not in reported_pairs:
                    reported_pairs.add(pair)
                    errors.append(f"{DECISIONS_FILE}: {eid}<->{target} supersession is not symmetric")
    ctx.decision_ids = ids


LOG_HEADING_RE = re.compile(r"^## \d{4}-\d.*$", re.M)


def check_log_fields_resolve(ctx, errors, docs):
    prefix = re.escape(ID_PREFIX)
    id_re = re.compile(prefix + r"\d+")
    known_roots = top_level_names(ctx)
    for name, heading, body in log_entries(ctx)[-1:]:  # older entries are history (D-029(7))
        fields = parse_fields(body)
        if ctx.decision_ids is not None and "Decisions" in fields:
            for d in id_re.findall(fields["Decisions"]):
                if d not in ctx.decision_ids:
                    errors.append(f"{name}: Decisions: references unknown {d}")
        if "Docs" in fields:
            for path in docs_field_paths(ctx, fields["Docs"], known_roots):
                if not exists_exact(ctx.root, path):
                    errors.append(f"{name}: Docs: references missing {path}")


def check_outside_repo_paths(ctx, errors, docs):
    pat = re.compile(OUTSIDE_PATH_RE)
    for p in docs_plus_log(ctx, docs):
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if line_ignored(line, "outside-repo-paths"):
                continue
            if pat.search(line):
                errors.append(f"{p.relative_to(ctx.root)}:{i}: absolute/outside-repo path in a living doc")


def is_doc_target(s):
    """True for a path this rule should still validate (D-029(5)): a markdown file, or
    a markdown file's own directory-shaped mistake ('foo.md/'). False for a script, data
    file, generated output, or plain directory reference - those are not documentation
    links, and a missing one is routine."""
    bare = s[:-1] if s.endswith(("/", "\\")) else s
    return bare.lower().endswith(".md")


def check_paths_exist(ctx, errors, docs):
    known_roots = top_level_names(ctx)
    for p in docs:
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if line_ignored(line, "paths-exist"):
                continue
            seen = set()
            for span in re.findall(r"`([^`]+)`", line):
                for tok in path_tokens_from_span(span):
                    s = candidate_path(ctx, tok, known_roots)
                    if s is None or s in seen or not is_doc_target(s):
                        continue
                    seen.add(s)
                    if not exists_exact(ctx.root, s):
                        errors.append(f"{p.relative_to(ctx.root)}:{i}: path does not exist: {s}")


LOG_HEAD_START_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?: \((\d+)\))?")
LOG_HEADING_GRAMMAR_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}(?: \(\d+\))? [\u2014-] .+$")
OLD_DATED_HEADING_RE = re.compile(r"^### \d{4}-\d{2}-\d{2}")


def log_entries(ctx):
    """Every log entry across the period files, oldest first, as (file name, heading, body)."""
    out = []
    log_dir = ctx.root / LOG_DIR
    for log in sorted(log_dir.glob("*.md")) if log_dir.exists() else []:
        out.extend((log.name, h, b) for h, b in split_entries(read_doc(log), LOG_HEADING_RE))
    return out


def work_rows(text):
    """(line number, stripped cells) for each data row of the work table; the header row
    (first cell 'ID') and the separator row are skipped."""
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if cells and cells[0] != "ID" and not all(re.fullmatch(r":?-+:?", c) for c in cells):
                rows.append((n, cells))
    return rows


def open_items(root):
    """What is to do (D-029(a)): each open row of the work list, as 'ID - item'. A missing
    file yields nothing; the work-table rule reports it."""
    p = root / WORK_FILE
    if not p.exists():
        return []
    return [f"{c[0]} — {c[1]}" for _, c in work_rows(read_doc(p)) if len(c) > 3 and c[3] == "open"]


def check_log_grammar(ctx, errors, docs):
    if not log_entries(ctx):
        errors.append(f"{LOG_DIR}: no dated entry ('## YYYY-MM-DD \u2014 headline') found")
        return
    log_dir = ctx.root / LOG_DIR
    for log in sorted(log_dir.glob("*.md")):
        text = read_doc(log)
        lines = text.splitlines()

        first_idx = None
        for i, line in enumerate(lines):
            if LOG_HEAD_START_RE.match(line):
                first_idx = i
                break
        if first_idx is not None:
            for i, line in enumerate(lines[first_idx + 1:], start=first_idx + 1):
                if OLD_DATED_HEADING_RE.match(line):
                    errors.append(
                        f"{log.name}:{i + 1}: '###' dated heading appears after the first '##' dated heading"
                    )

        seen_keys = set()
        for m in LOG_HEADING_RE.finditer(text):
            heading = m.group(0)
            lineno = text[:m.start()].count("\n") + 1
            if not LOG_HEADING_GRAMMAR_RE.match(heading):
                errors.append(f"{log.name}:{lineno}: log heading grammar violated: {heading.strip()}")
                continue
            hm = LOG_HEAD_START_RE.match(heading)
            key = (hm.group(1), hm.group(2) or "")
            if key in seen_keys:
                errors.append(f"{log.name}:{lineno}: duplicate log heading date+N {key}")
            seen_keys.add(key)

        entries = split_entries(text, LOG_HEADING_RE)
        for heading, body in entries:
            head = heading.strip()
            fields = parse_fields(body)
            if "Decisions" not in fields:
                errors.append(f"{log.name}: entry '{head}' missing a Decisions: line")
            if "Docs" not in fields:
                errors.append(f"{log.name}: entry '{head}' missing a Docs: line")


def check_work_table(ctx, errors, docs):
    p = ctx.root / WORK_FILE
    if not p.exists():
        errors.append(f"{WORK_FILE}: file does not exist")
        return
    for n, c in work_rows(read_doc(p)):
        if len(c) != 6 or not c[0] or c[2] not in WORK_TYPES or c[3] not in WORK_STATUSES:
            errors.append(f"{WORK_FILE}:{n}: bad row - needs ID | Item | Type ({'/'.join(WORK_TYPES)}) "
                          f"| Status ({'/'.join(WORK_STATUSES)}) | Added | Closed")


def check_routing_coverage(ctx, errors, docs):
    routing_path = ctx.root / ROUTING_FILE
    if not routing_path.exists():
        errors.append(f"{ROUTING_FILE}: file does not exist")
        return
    routed = set(routing_table_paths(ctx))
    for ext in ("*.md", "*.html"):
        for p in sorted(ctx.docs.rglob(ext)):
            rel = p.relative_to(ctx.docs)
            if rel.parts and rel.parts[0] in ROUTING_EXEMPT_TOPDIRS:
                continue
            text = read_doc(p)
            if any(m.group(1) == "routing-coverage" for m in SUPPRESS_RE.finditer(text)):
                continue
            rel_posix = p.relative_to(ctx.root).as_posix()
            if rel_posix not in routed:
                errors.append(f"{rel_posix}: not referenced in {ROUTING_FILE}'s table "
                               "(no check-docs:ignore routing-coverage marker either)")


GENERIC_RULES = (
    check_decisions_integrity,
    check_log_fields_resolve,
    check_outside_repo_paths,
    check_paths_exist,
    check_log_grammar,
    check_work_table,
    check_routing_coverage,
)


def run_generic_rules(ctx, errors):
    docs = living_docs(ctx)
    for fn in GENERIC_RULES:
        fn(ctx, errors, docs)
    for p in docs_plus_log(ctx, docs):
        opener = scan_doc(p)[1]
        if opener:
            errors.append(f"{p.relative_to(ctx.root)}:{opener}: unclosed code fence; "
                          "the rest of the file is unchecked")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _is_home(root):
    """A repo-clean home (D-023): a folder with the `.repo-clean` marker, nothing else."""
    return (root / ".repo-clean").exists()


def _resolve_root(root_arg):
    """The home to check, or None after printing why (the caller exits 2)."""
    if root_arg:
        root = Path(root_arg).resolve()
        if not root.is_dir():
            print(f"--root {root}: not a directory")
        elif not _is_home(root):
            print(f"{root}: no repo-clean home here (no .repo-clean marker); not checking")
        else:
            return root
        return None
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if _is_home(candidate):
            return candidate
    print(f"no repo-clean home at or above {cwd}")
    return None


def _build_arg_parser():
    parser = argparse.ArgumentParser(prog="check_docs.py", description="Docs hygiene checker.")
    parser.add_argument("--root", metavar="DIR",
                        help="home to check (default: the nearest .repo-clean at or above the cwd)")
    return parser


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return _main(argv)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"internal error: {exc!r}")
        return 2


def _main(argv):
    args = _build_arg_parser().parse_args(argv)  # exits 2 itself on an unknown flag
    root = _resolve_root(args.root)
    if root is None:
        return 2

    errors = []
    ctx = Ctx(root)
    run_generic_rules(ctx, errors)

    for e in errors:
        print(e)
    if errors:
        print(f"\n{len(errors)} issue(s).")
        return 1
    # Say what a clean run does NOT mean, at the moment someone sees it. The README says
    # the same thing, but nobody re-reads a README while looking at a green result.
    n = len(living_docs(ctx))
    print(f"0 findings across {n} files. Shape verified; content not verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
