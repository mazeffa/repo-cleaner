#!/usr/bin/env python3
"""Generic docs hygiene checker. Stdlib only. A config-driven core; there is no per-project
add-on file (D-022) - the checker never runs project code.

Exit 0 on success, printing one line stating that shape was verified and content
was not. Exit 1 on doc findings, exit 2 when there is nothing to check (no `.repo-clean` home
at or above the cwd, or a bad --root) or on any unhandled exception. Prints one line per
finding either way. With no --root, the home is the nearest `.repo-clean` marker at or above
the current folder.

Rules (stable string ids, used in inline suppression comments and in output; D-024):
  decisions-integrity   Unique IDs in the decision register, closed-vocabulary Status/
                         Verdict read from the entry body only, symmetric supersession
                         (every id in Supersedes:/Superseded-by: is checked, not just
                         the first).
  log-fields-resolve    docs/log/*.md 'Decisions:'/'Docs:' fields resolve to real ids/
                         real .md paths; a field's value may wrap onto following lines.
                         Only .md targets are checked (D-016(b)) - a missing dated output
                         file or a renamed script is routine, not a broken doc link.
  outside-repo-paths    No out-of-repo path in a living doc. The default catches Windows
                         drive paths, ~, /home, /Users, /root, and Git Bash /<letter>/Users
                         or /<letter>/home.
  paths-exist           Backtick-quoted .md paths in living docs must exist, checked
                         case-exactly regardless of OS; a trailing '/' requires a directory.
                         Non-.md targets (scripts, data, generated output) are not checked
                         (D-016(b)).
  banned-headers        No 'Next Steps'-style header anywhere - next steps live only in the
                         current log entry's Next: field (D-016(c)); narrowed from
                         TODO/Next Steps/Future Work by D-017.
  diary-grammar         Log heading grammar (including the (N) numbering convention),
                         required fields, only the log's last entry, across period files,
                         carries State: and Next: - and it must carry both (D-016(c)).
  open-questions-sync   Open-questions table <-> Status: open entries, Revisit: required.
  routing-coverage      Every living doc is referenced in the routing file's table
                         (table rows only, a leading './' normalized).

Fenced code blocks (```...```) are blanked before any rule reads a document, so an example
heading or field name inside a fence is never mistaken for real content.

Suppression, three layers:
  1. exempt_dirs                                      - whole directories, always exempt.
  2. routing_exempt_topdirs                            - docs/<topdir> exempt from routing-coverage only.
  3. <!-- check-docs: ignore <rule-id> --> on a line   - suppresses one hit on that line.
"""
import argparse
import os
import re
import sys
from pathlib import Path

CONFIG = {
    "living_roots": ["CLAUDE.md", "README.md"],
    "docs_dir": "docs",
    "exempt_dirs": ["docs/archive", "docs/log"],
    "decisions_file": "docs/DECISIONS.md",
    "id_prefix": "D-",
    "status_vocab": ("active", "superseded", "open"),
    "verdict_vocab": ("adopted", "rejected", "unresolved"),
    "open_questions_section": ("## Open questions", "## Fields"),
    "log_dir": "docs/log",
    "routing_file": "CLAUDE.md",
    "routing_exempt_topdirs": ("archive", "log", "research"),
    "banned_header_re": r"^#+.*\bNext Steps\b",
    "outside_path_re": (
        r"(?<![\w\\])[A-Za-z]:\\\w"          # drive letter, not the tail of a word
        r"|~[\\/]"                           # ~/ or ~\
        r"|(?:^|[\s`(\[])/(?:home|Users|root)/"          # unix absolute home dirs
        r"|(?:^|[\s`(\[])/[A-Za-z]/(?:Users|home)/"      # Git Bash /c/Users, /c/home
    ),
    "path_suppressed_prefixes": ("output/",),
    "path_cmd_prefixes": ("python ", "python3 "),
}


def read_doc(p):
    """Read a doc, never raising on a stray non-UTF-8 byte (a mojibake char just fails
    some other rule), with every fenced code block's interior (and its ``` delimiter
    lines) blanked out. Line numbers are preserved so callers can still report them."""
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    out = []
    in_fence = False
    fence_re = re.compile(r"^\s*```")
    for line in lines:
        if fence_re.match(line):
            in_fence = not in_fence
            out.append("")
        elif in_fence:
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


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
    """Resolved config for one run: root path + absolute paths derived from CONFIG."""

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.docs = root / config["docs_dir"] if config["docs_dir"] else None
        self.exempt_dirs = {root / d for d in config["exempt_dirs"]}
        self.decision_ids = None  # set by check_decisions_integrity if that rule runs

    def is_exempt(self, p):
        return any(d in p.parents or d == p for d in self.exempt_dirs)


def routed_docs(ctx):
    """Every existing .md a routing-table row names (D-020) - a file the table calls
    authoritative is one the model will trust, so it is one the checker reads."""
    routing = ctx.root / (ctx.config["routing_file"] or "")
    if not ctx.config["routing_file"] or not routing.is_file():
        return []
    out = []
    for line in read_doc(routing).splitlines():
        if line.strip().startswith("|"):
            for span in re.findall(r"`([^`]+)`", line):
                rel = span.strip()
                rel = rel[2:] if rel.startswith("./") else rel
                p = ctx.root / rel
                if rel.endswith(".md") and exists_exact(ctx.root, rel) and not ctx.is_exempt(p):
                    out.append(p)
    return out


def living_docs(ctx):
    files = [ctx.root / name for name in ctx.config["living_roots"] if (ctx.root / name).exists()]
    if ctx.docs:
        files += [p for p in ctx.docs.rglob("*.md") if not ctx.is_exempt(p)]
    seen = {f.resolve() for f in files}
    for p in routed_docs(ctx):
        if p.resolve() not in seen:
            seen.add(p.resolve())
            files.append(p)
    return files


def docs_plus_log(ctx):
    files = list(living_docs(ctx))
    if ctx.config["log_dir"]:
        log_dir = ctx.root / ctx.config["log_dir"]
        if log_dir.exists():
            files += sorted(log_dir.glob("*.md"))
    return files


def top_level_names(ctx):
    names = {p.name for p in ctx.root.iterdir()}
    names |= set(ctx.config["living_roots"])
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
    cfg = ctx.config
    s = token.strip().strip("\"'")
    for pre in cfg["path_cmd_prefixes"]:
        if s.startswith(pre):
            s = s[len(pre):]
    if not s or any(x in s for x in PLACEHOLDER):
        return None
    if s.startswith(("http://", "https://")):
        return None
    s = re.sub(r":\d+(-\d+)?$", "", s.rstrip(":,.\"'()"))
    if not s or s.startswith(tuple(cfg["path_suppressed_prefixes"])):
        return None
    if not CANDIDATE_TOKEN_RE.match(s):
        return None
    if s.split("/", 1)[0] not in known_roots:
        return None
    return s


def docs_field_paths(ctx, value, known_roots):
    """Tokens out of a `Docs:` field value that look confidently like paths to
    documentation. Only a token ending in '.md' counts (D-016(b)): a version number,
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

def check_decisions_integrity(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["decisions_file"]:
        ctx.decision_ids = None
        return
    p = ctx.root / cfg["decisions_file"]
    if not p.exists():
        errors.append(f"{cfg['decisions_file']}: file does not exist")
        ctx.decision_ids = set()
        return
    prefix = re.escape(cfg["id_prefix"])
    id_re = re.compile(prefix + r"\d+")
    heading_re = re.compile(rf"^## {prefix}\d+\b.*$")
    text = read_doc(p)
    entries = split_entries(text, heading_re)
    ids = set()
    superseded_by, supersedes = {}, {}
    for heading, body in entries:
        m = re.match(rf"^## ({prefix}\d+)", heading)
        eid = m.group(1)
        if eid in ids:
            errors.append(f"{cfg['decisions_file']}: duplicate id {eid}")
        ids.add(eid)
        fields = parse_fields(body)
        status = fields.get("Status")
        verdict = fields.get("Verdict")
        if status not in cfg["status_vocab"]:
            errors.append(f"{cfg['decisions_file']}: {eid} bad/missing Status")
        if verdict not in cfg["verdict_vocab"]:
            errors.append(f"{cfg['decisions_file']}: {eid} bad/missing Verdict")
        sb_val = fields.get("Superseded-by", "")
        sp_val = fields.get("Supersedes", "")
        if status == "superseded" and not id_re.search(sb_val):
            errors.append(f"{cfg['decisions_file']}: {eid} is superseded but names no Superseded-by target")
        if sb_val:
            superseded_by[eid] = id_re.findall(sb_val)
        if sp_val:
            supersedes[eid] = id_re.findall(sp_val)
    reported_pairs = set()
    for eid, targets in superseded_by.items():
        for target in targets:
            if target not in ids:
                errors.append(f"{cfg['decisions_file']}: {eid} Superseded-by dangles at {target}")
            elif eid not in supersedes.get(target, []):
                pair = frozenset((eid, target))
                if pair not in reported_pairs:
                    reported_pairs.add(pair)
                    errors.append(f"{cfg['decisions_file']}: {eid}<->{target} supersession is not symmetric")
    for eid, targets in supersedes.items():
        for target in targets:
            if target not in ids:
                errors.append(f"{cfg['decisions_file']}: {eid} Supersedes dangles at {target}")
            elif eid not in superseded_by.get(target, []):
                pair = frozenset((eid, target))
                if pair not in reported_pairs:
                    reported_pairs.add(pair)
                    errors.append(f"{cfg['decisions_file']}: {eid}<->{target} supersession is not symmetric")
    ctx.decision_ids = ids


LOG_HEADING_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}.*$")


def check_log_fields_resolve(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["log_dir"]:
        return
    log_dir = ctx.root / cfg["log_dir"]
    if not log_dir.exists():
        return
    prefix = re.escape(cfg["id_prefix"])
    id_re = re.compile(prefix + r"\d+")
    known_roots = top_level_names(ctx)
    for log in sorted(log_dir.glob("*.md")):
        text = read_doc(log)
        for heading, body in split_entries(text, LOG_HEADING_RE):
            fields = parse_fields(body)
            if ctx.decision_ids is not None and "Decisions" in fields:
                for d in id_re.findall(fields["Decisions"]):
                    if d not in ctx.decision_ids:
                        errors.append(f"{log.name}: Decisions: references unknown {d}")
            if "Docs" in fields:
                for path in docs_field_paths(ctx, fields["Docs"], known_roots):
                    if not exists_exact(ctx.root, path):
                        errors.append(f"{log.name}: Docs: references missing {path}")


def check_outside_repo_paths(ctx, errors, docs):
    outside_re = ctx.config["outside_path_re"]
    if not outside_re:
        return
    pat = re.compile(outside_re)
    for p in docs_plus_log(ctx):
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if line_ignored(line, "outside-repo-paths"):
                continue
            if pat.search(line):
                errors.append(f"{p.relative_to(ctx.root)}:{i}: absolute/outside-repo path in a living doc")


def is_doc_target(s):
    """True for a path this rule should still validate (D-016(b)): a markdown file, or
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


def check_banned_headers(ctx, errors, docs):
    header_re = ctx.config["banned_header_re"]
    if not header_re:
        return
    pat = re.compile(header_re, re.I)
    for p in docs_plus_log(ctx):
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if line_ignored(line, "banned-headers"):
                continue
            if pat.match(line):
                errors.append(f"{p.relative_to(ctx.root)}:{i}: banned section header: {line.strip()}")


DIARY_HEAD_START_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?: \((\d+)\))?")
DIARY_HEADING_LINE_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}.*$", re.M)
DIARY_HEADING_GRAMMAR_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}(?: \(\d+\))? [\u2014-] .+$")
OLD_DATED_HEADING_RE = re.compile(r"^### \d{4}-\d{2}-\d{2}")


def log_entries(ctx):
    """Every log entry across the period files, oldest first, as (file name, heading, body)."""
    out = []
    log_dir = ctx.root / ctx.config["log_dir"] if ctx.config["log_dir"] else None
    for log in sorted(log_dir.glob("*.md")) if log_dir and log_dir.exists() else []:
        out.extend((log.name, h, b) for h, b in split_entries(read_doc(log), LOG_HEADING_RE))
    return out


def current_fields(root):
    """The parsed fields of the log's last entry (State:, Next:, ...) - the one definition of
    "current state", shared by the checker and the SessionStart hook."""
    entries = log_entries(Ctx(root, dict(CONFIG)))
    return parse_fields(entries[-1][2]) if entries else {}


def check_diary_grammar(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["log_dir"]:
        return
    log_dir = ctx.root / cfg["log_dir"]
    if not log_dir.exists():
        return
    for log in sorted(log_dir.glob("*.md")):
        text = read_doc(log)
        lines = text.splitlines()

        first_idx = None
        for i, line in enumerate(lines):
            if DIARY_HEAD_START_RE.match(line):
                first_idx = i
                break
        if first_idx is not None:
            for i, line in enumerate(lines[first_idx + 1:], start=first_idx + 1):
                if OLD_DATED_HEADING_RE.match(line):
                    errors.append(
                        f"{log.name}:{i + 1}: '###' dated heading appears after the first '##' dated heading"
                    )

        seen_keys = set()
        date_groups = {}
        for m in DIARY_HEADING_LINE_RE.finditer(text):
            heading = m.group(0)
            lineno = text[:m.start()].count("\n") + 1
            if not DIARY_HEADING_GRAMMAR_RE.match(heading):
                errors.append(f"{log.name}:{lineno}: diary heading grammar violated: {heading.strip()}")
            hm = DIARY_HEAD_START_RE.match(heading)
            date, n = hm.group(1), hm.group(2)
            key = (date, n or "")
            if key in seen_keys:
                errors.append(f"{log.name}:{lineno}: duplicate diary heading date+N {key}")
            seen_keys.add(key)
            date_groups.setdefault(date, []).append((n, lineno, heading))

        for date, group in date_groups.items():
            for idx, (n, lineno, heading) in enumerate(group):
                expected = None if idx == 0 else str(idx + 1)
                if n != expected:
                    want = "no (N)" if expected is None else f"({expected})"
                    errors.append(
                        f"{log.name}:{lineno}: heading numbering should be {want} for the "
                        f"#{idx + 1} entry dated {date}: {heading.strip()}"
                    )

        entries = split_entries(text, LOG_HEADING_RE)
        for heading, body in entries:
            head = heading.strip()
            fields = parse_fields(body)
            if "Decisions" not in fields:
                errors.append(f"{log.name}: entry '{head}' missing a Decisions: line")
            if "Docs" not in fields:
                errors.append(f"{log.name}: entry '{head}' missing a Docs: line")

    all_entries = log_entries(ctx)
    if all_entries:
        name, heading, body = all_entries[-1]
        fields = parse_fields(body)
        for field in ("State", "Next"):
            if not fields.get(field, "").strip():
                errors.append(f"{name}: last entry '{heading.strip()}' missing a non-empty {field}: line")
        for name, heading, body in all_entries[:-1]:
            for field in ("State", "Next"):
                if parse_fields(body).get(field, "").strip():
                    errors.append(
                        f"{name}: entry '{heading.strip()}' carries a {field}: line but is not the "
                        "log's last entry - only the last entry holds current state; delete it"
                    )


def check_open_questions_sync(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["open_questions_section"] or not cfg["decisions_file"]:
        return
    start, end = cfg["open_questions_section"]
    p = ctx.root / cfg["decisions_file"]
    if not p.exists():
        return
    prefix = re.escape(cfg["id_prefix"])
    id_re = prefix + r"\d+"
    text = read_doc(p)
    m = re.search(rf"^{re.escape(start)}\n(.*?)^{re.escape(end)}", text, flags=re.M | re.S)
    if not m:
        errors.append(f"{cfg['decisions_file']}: '{start}' ... '{end}' section not found")
        return
    table_ids = set(re.findall(rf"\|\s*({id_re})\s*\|", m.group(1)))

    heading_re = re.compile(rf"^## {prefix}\d+\b.*$")
    open_ids = set()
    for heading, body in split_entries(text, heading_re):
        eid = re.match(rf"^## ({id_re})", heading).group(1)
        fields = parse_fields(body)
        if fields.get("Status") == "open":
            open_ids.add(eid)
            if not fields.get("Revisit", "").strip():
                errors.append(f"{cfg['decisions_file']}: {eid} is Status: open but has no Revisit: trigger")

    for eid in sorted(open_ids - table_ids):
        errors.append(f"{cfg['decisions_file']}: {eid} is Status: open but missing from the Open questions table")
    for eid in sorted(table_ids - open_ids):
        errors.append(f"{cfg['decisions_file']}: {eid} is in the Open questions table but is not Status: open")


def check_routing_coverage(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["routing_file"] or not ctx.docs:
        return
    routing_path = ctx.root / cfg["routing_file"]
    if not routing_path.exists():
        errors.append(f"{cfg['routing_file']}: file does not exist")
        return
    routing_text = read_doc(routing_path)
    routed = set()
    for line in routing_text.splitlines():
        if line.strip().startswith("|"):
            for span in re.findall(r"`([^`]+)`", line):
                norm = span.strip()
                if norm.startswith("./"):
                    norm = norm[2:]
                routed.add(norm)
    exempt_topdirs = tuple(cfg["routing_exempt_topdirs"])
    for ext in ("*.md", "*.html"):
        for p in sorted(ctx.docs.rglob(ext)):
            rel = p.relative_to(ctx.docs)
            if rel.parts and rel.parts[0] in exempt_topdirs:
                continue
            text = read_doc(p)
            if any(m.group(1) == "routing-coverage" for m in SUPPRESS_RE.finditer(text)):
                continue
            rel_posix = p.relative_to(ctx.root).as_posix()
            if rel_posix not in routed:
                errors.append(f"{rel_posix}: not referenced in {cfg['routing_file']}'s table "
                               "(no check-docs:ignore routing-coverage marker either)")


GENERIC_RULES = (
    ("decisions-integrity", check_decisions_integrity),
    ("log-fields-resolve", check_log_fields_resolve),
    ("outside-repo-paths", check_outside_repo_paths),
    ("paths-exist", check_paths_exist),
    ("banned-headers", check_banned_headers),
    ("diary-grammar", check_diary_grammar),
    ("open-questions-sync", check_open_questions_sync),
    ("routing-coverage", check_routing_coverage),
)


def run_generic_rules(ctx, errors):
    docs = living_docs(ctx)
    for _rule_id, fn in GENERIC_RULES:
        fn(ctx, errors, docs)


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
    ctx = Ctx(root, dict(CONFIG))
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
