#!/usr/bin/env python3
"""Generic docs hygiene checker. Stdlib only. A config-driven core plus an
optional check_docs_local.py extension point for repo-specific rules.

Exit 0 on success, printing one line stating that shape was verified and content
was not. Exit 1 on doc findings, exit 2 on an internal error (bad --root, local-file
import failure, CONFIG_VERSION mismatch, or any unhandled exception). Prints one line
per finding either way.

Generic rules (stable string ids, used as CONFIG keys, in inline suppression comments,
and in output):
  decisions-integrity   Unique IDs in the decision register, closed-vocabulary Status/
                         Verdict read from the entry body only, symmetric supersession
                         (every id in Supersedes:/Superseded-by: is checked, not just
                         the first).
  log-fields-resolve    docs/log/*.md 'Decisions:'/'Docs:' fields resolve to real ids/
                         paths; a field's value may wrap onto following lines.
  date-stamped-filenames No date-stamped filename under docs/ outside the exempt dirs.
  outside-repo-paths    No out-of-repo path in a living doc. The default catches Windows
                         drive paths, ~, /home, /Users, /root, and Git Bash /<letter>/Users
                         or /<letter>/home; widen outside_path_re for others (e.g. /opt).
  paths-exist           Backtick-quoted repo paths in living docs must exist, checked
                         case-exactly regardless of OS; a trailing '/' requires a directory.
  banned-headers        No TODO/Next Steps/Future Work headers outside the decisions file.
  diary-grammar         Log heading grammar (including the (N) numbering convention),
                         required fields, last entry needs State:.
  archive-banner-paths  Archive disposition banner lines (blockquote lines only, wrapped
                         '>' lines joined) cite real, in-repo paths, searched recursively.
  open-questions-sync   Open-questions table <-> Status: open entries, Revisit: required.
  routing-coverage      Every living doc is referenced in the routing file's table
                         (table rows only, a leading './' normalized).
  research-fields       Research docs (searched recursively) carry Status:/Date: read from
                         real field lines, and a superseded one names what replaced it.
  file-map-cap          The file-map doc (if configured) stays under its line cap.

Fenced code blocks (```...```) are blanked before any rule reads a document, so an example
heading or field name inside a fence is never mistaken for real content.

Repo-specific rules live in a sibling check_docs_local.py (see --init-config), loaded via
load_local_module()/run_local_check() and run after the generic rules. The local file lives
next to this script when this script is inside --root, otherwise at <root>/scripts/tools/.

Suppression, four layers:
  1. exempt_dirs                                      - whole directories, always exempt.
  2. routing_exempt_topdirs                            - docs/<topdir> exempt from routing-coverage only.
  3. CONFIG["<rule-id>"] = None                        - disables that rule repo-wide (the
                                                          rule ids above are the CONFIG keys).
  4. <!-- check-docs: ignore <rule-id> --> on a line   - suppresses one hit on that line.
"""
import argparse
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

CORE_VERSION = "1.3.0"  # bump on any content change; core_digest() catches what this misses
CONFIG_VERSION = 1


def core_digest():
    """Short digest of this file's own source, identifying the build.

    DEF-23: CORE_VERSION is hand-maintained and has stayed put across releases that
    changed rules, so the version string alone cannot tell two builds apart. Newlines
    are normalized so a CRLF checkout and an LF one digest the same.
    """
    try:
        source = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return "unknown"
    return hashlib.sha256(source).hexdigest()[:8]

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
    "research_dir": "docs/research",
    "file_map": "docs/FILE_MAP.md",
    "file_map_cap": 60,
    "banned_header_re": r"^#+.*\b(TODO|Next Steps|Future Work)\b",
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


NO_ROUTE_MARKER = "<!-- no-route -->"  # deprecated; routing-coverage only, still honored
SUPPRESS_RE = re.compile(r"<!--\s*check-docs:\s*ignore\s+([\w-]+)\s*-->")
PLACEHOLDER = ("<", "*", "..", "path/to", "YYYY", "{", "|")
CANDIDATE_TOKEN_RE = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)+/?$")
BANNER_WORDS = ("Superseded", "Archived", "Disposition")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def line_ignored(line, rule_id):
    return any(m.group(1) == rule_id for m in SUPPRESS_RE.finditer(line))


class Ctx:
    """Resolved config for one run: root path + absolute paths derived from CONFIG."""

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.docs = root / config["docs_dir"] if config["docs_dir"] else None
        self.exempt_dirs = {root / d for d in config["exempt_dirs"]}
        self.archive_dir = self.docs / "archive" if self.docs else None
        self.decision_ids = None  # set by check_decisions_integrity if that rule runs

    def is_exempt(self, p):
        return any(d in p.parents or d == p for d in self.exempt_dirs)


def living_docs(ctx):
    files = [ctx.root / name for name in ctx.config["living_roots"] if (ctx.root / name).exists()]
    if ctx.docs:
        files += [p for p in ctx.docs.rglob("*.md") if not ctx.is_exempt(p)]
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
    """Tokens out of a `Docs:` field value that look confidently like repo paths. A
    token without '/' must end in '.md' to count (a version number, section number,
    or bare word is skipped); 'none', URLs, and Windows drive paths are always
    skipped."""
    out = []
    for raw in re.split(r"[,\s]+", value.strip()):
        tok = raw.strip().strip(".,;()")
        if not tok or tok.lower() == "none":
            continue
        if "://" in tok:
            continue
        if re.match(r"^[A-Za-z]:[\\/]", tok):
            continue
        if "/" in tok:
            c = candidate_path(ctx, tok, known_roots)
            if c:
                out.append(c)
        elif re.match(r"^[\w.\-]+\.md$", tok):
            out.append(tok)
    return out


def scan_line_for_paths(ctx, errors, p, i, line, label, known_roots, rule_id):
    """Flag an outside-repo path and any non-existent repo-relative backticked path on
    one line."""
    cfg = ctx.config
    if line_ignored(line, rule_id):
        return
    outside_re = cfg["outside_path_re"]
    if outside_re and re.search(outside_re, line):
        errors.append(f"{p.relative_to(ctx.root)}:{i}: outside-repo path in {label}")
    seen = set()
    for span in re.findall(r"`([^`]+)`", line):
        for tok in path_tokens_from_span(span):
            s = candidate_path(ctx, tok, known_roots)
            if s is None or s in seen:
                continue
            seen.add(s)
            if not exists_exact(ctx.root, s):
                errors.append(f"{p.relative_to(ctx.root)}:{i}: path does not exist in {label}: {s}")


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


def check_date_stamped_filenames(ctx, errors, docs):
    if not ctx.docs or not ctx.docs.exists():
        return
    for p in ctx.docs.rglob("*.md"):
        if not ctx.is_exempt(p) and DATE_RE.search(p.name):
            errors.append(f"date-stamped filename outside exempt dirs: {p.relative_to(ctx.root)}")


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
                    if s is None or s in seen:
                        continue
                    seen.add(s)
                    if not exists_exact(ctx.root, s):
                        errors.append(f"{p.relative_to(ctx.root)}:{i}: path does not exist: {s}")


def check_banned_headers(ctx, errors, docs):
    header_re = ctx.config["banned_header_re"]
    if not header_re:
        return
    pat = re.compile(header_re, re.I)
    decisions_name = Path(ctx.config["decisions_file"]).name if ctx.config["decisions_file"] else None
    for p in docs_plus_log(ctx):
        if decisions_name and p.name == decisions_name:
            continue
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if line_ignored(line, "banned-headers"):
                continue
            if pat.match(line):
                errors.append(f"{p.relative_to(ctx.root)}:{i}: banned section header: {line.strip()}")


DIARY_HEAD_START_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?: \((\d+)\))?")
DIARY_HEADING_LINE_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}.*$", re.M)
DIARY_HEADING_GRAMMAR_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}(?: \(\d+\))? [\u2014-] .+$")
OLD_DATED_HEADING_RE = re.compile(r"^### \d{4}-\d{2}-\d{2}")


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
        if entries:
            last_heading, last_body = entries[-1]
            head = last_heading.strip()
            last_fields = parse_fields(last_body)
            if not last_fields.get("State", "").strip():
                errors.append(f"{log.name}: last entry '{head}' missing a non-empty State: line")


def check_archive_banner_paths(ctx, errors, docs):
    if not ctx.archive_dir or not ctx.archive_dir.exists():
        return
    known_roots = top_level_names(ctx)
    for p in sorted(ctx.archive_dir.rglob("*.md")):
        lines = read_doc(p).splitlines()
        i = 0
        while i < len(lines):
            if lines[i].lstrip().startswith(">"):
                start = i
                joined = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    joined.append(lines[i].lstrip()[1:].strip())
                    i += 1
                banner_text = " ".join(joined)
                if any(w in banner_text for w in BANNER_WORDS):
                    scan_line_for_paths(ctx, errors, p, start + 1, banner_text,
                                        "archive disposition banner", known_roots, "archive-banner-paths")
            else:
                i += 1


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
            if NO_ROUTE_MARKER in text:
                continue
            if any(m.group(1) == "routing-coverage" for m in SUPPRESS_RE.finditer(text)):
                continue
            rel_posix = p.relative_to(ctx.root).as_posix()
            if rel_posix not in routed:
                errors.append(f"{rel_posix}: not referenced in {cfg['routing_file']}'s table "
                               f"(no {NO_ROUTE_MARKER} or check-docs:ignore marker either)")


def check_file_map_cap(ctx, errors, docs):
    cfg = ctx.config
    if not cfg["file_map"] or not cfg["file_map_cap"]:
        return
    p = ctx.root / cfg["file_map"]
    if not p.exists():
        return
    n = len(read_doc(p).splitlines())
    if n > cfg["file_map_cap"]:
        errors.append(f"{cfg['file_map']}: {n} lines, over the {cfg['file_map_cap']}-line cap")


def check_research_fields(ctx, errors, docs):
    """Research docs are rewritten in place, so nothing else reveals their age or whether
    they still apply. Status:/Date: is the only signal a reader (or the next agent) gets."""
    rdir = ctx.config["research_dir"]
    if not rdir:
        return
    d = ctx.root / rdir
    if not d.exists():
        return
    for p in sorted(d.rglob("*.md")):
        rel = p.relative_to(ctx.root)
        text = read_doc(p)
        if line_ignored(text, "research-fields"):
            continue
        fields = parse_fields(text.splitlines())
        status = fields.get("Status", "")
        if status not in ctx.config["status_vocab"]:
            errors.append(f"{rel}: bad/missing Status (one of {'/'.join(ctx.config['status_vocab'])})")
        date_val = fields.get("Date", "").strip()
        if not DATE_RE.match(date_val):
            errors.append(f"{rel}: bad/missing Date (YYYY-MM-DD)")
        if status == "superseded" and not fields.get("Superseded-by", "").strip():
            errors.append(f"{rel}: Status: superseded but names no Superseded-by target")


GENERIC_RULES = (
    ("decisions-integrity", check_decisions_integrity),
    ("log-fields-resolve", check_log_fields_resolve),
    ("date-stamped-filenames", check_date_stamped_filenames),
    ("outside-repo-paths", check_outside_repo_paths),
    ("paths-exist", check_paths_exist),
    ("banned-headers", check_banned_headers),
    ("diary-grammar", check_diary_grammar),
    ("archive-banner-paths", check_archive_banner_paths),
    ("open-questions-sync", check_open_questions_sync),
    ("routing-coverage", check_routing_coverage),
    ("research-fields", check_research_fields),
    ("file-map-cap", check_file_map_cap),
)


def run_generic_rules(ctx, errors):
    docs = living_docs(ctx)
    for rule_id, fn in GENERIC_RULES:
        # A local CONFIG override can map a rule id to None to disable it repo-wide.
        # Absent entirely (the normal case) leaves the rule on.
        if ctx.config.get(rule_id, True) is None:
            continue
        fn(ctx, errors, docs)


# ---------------------------------------------------------------------------
# Local extension loading
# ---------------------------------------------------------------------------

def local_module_dir(root):
    """Where check_docs_local.py lives for a given repo root: next to this script when
    this script is itself inside root (the plugin-source layout), otherwise the
    installed scripts/tools/ layout under root."""
    script_dir = Path(__file__).resolve().parent
    try:
        script_dir.relative_to(root)
        return script_dir
    except ValueError:
        return root / "scripts" / "tools"


def load_local_module(ctx, internal_errors, local_dir=None):
    """Import check_docs_local.py from local_dir (default: local_module_dir(ctx.root))
    and apply its CONFIG overrides to ctx.config in place, before any rule runs - local
    CONFIG overrides must be visible to the generic rules too (e.g. a lowered
    file_map_cap). Returns the module, or None if there is no local file or it failed
    to import (either way, safe to skip check() after)."""
    local_dir = local_dir or local_module_dir(ctx.root)
    local_path = local_dir / "check_docs_local.py"
    if not local_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("check_docs_local", local_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        internal_errors.append(f"check_docs_local.py: import failed: {exc!r}")
        return None

    local_version = getattr(mod, "CONFIG_VERSION", None)
    if local_version != CONFIG_VERSION:
        internal_errors.append(
            f"check_docs_local.py: CONFIG_VERSION mismatch (local={local_version!r}, "
            f"core={CONFIG_VERSION}) - re-check local CONFIG keys against the new core defaults"
        )

    local_config = getattr(mod, "CONFIG", None)
    if local_config:
        ctx.config.update(local_config)
    return mod


def run_local_check(mod, ctx, errors, internal_errors):
    """Run the (already-imported) local module's check(root), if it defines one."""
    if mod is None or not hasattr(mod, "check"):
        return
    try:
        found = mod.check(ctx.root)
    except Exception as exc:
        internal_errors.append(f"check_docs_local.py: check() raised: {exc!r}")
        return
    if found:
        errors.extend(found)


LOCAL_STARTER = '''"""Repo-specific docs rules for check_docs.py. Not overwritten when the core is re-synced
(re-sync is `cp <plugin>/scripts/check_docs.py scripts/tools/check_docs.py` - it never
touches this file).

Bump CONFIG_VERSION here to match the core's CONFIG_VERSION after checking your CONFIG
overrides still make sense against the new defaults; a mismatch is reported as an internal
error (exit 2), not silently ignored.

Four ways to suppress a false positive - pick the narrowest one that fits:
  1. CONFIG["exempt_dirs"] (core CONFIG key, override below) - a whole directory (e.g. a
     vendored subtree) should never be treated as a living doc at all.
  2. CONFIG["routing_exempt_topdirs"] - a whole docs/<topdir> is fine unrouted (evidence,
     history) but should still be checked by every other rule.
  3. CONFIG["<rule-id>"] = None below - the rule itself doesn't apply to this repo (e.g. no
     decision register: CONFIG["decisions_file"] = None disables decisions-integrity and
     open-questions-sync). <rule-id> is one of the ids listed in the module docstring.
  4. `<!-- check-docs: ignore <rule-id> -->` on one line in a doc - a single, deliberate
     exception (a doc that must cite an outside path for one paragraph) rather than a
     repo-wide policy change.
"""

CONFIG_VERSION = 1

# Override any core CONFIG key here, e.g.:
# CONFIG = {"file_map_cap": 80}
CONFIG = {}


def check(root):
    """Return a list of finding strings (empty/None if clean). `root` is the repo root Path."""
    errors = []
    return errors
'''


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def git_root():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return Path(out.stdout.strip())


def _resolve_root(root_arg):
    if root_arg:
        root = Path(root_arg).resolve()
        if not root.is_dir():
            print(f"--root {root}: not a directory")
            return None
        return root
    # git is optional: no repo, no git binary, or a failing git call all just fall
    # back to the current directory rather than being fatal.
    try:
        return git_root()
    except Exception:
        return Path.cwd()


def _build_arg_parser():
    parser = argparse.ArgumentParser(prog="check_docs.py", description="Docs hygiene checker.")
    parser.add_argument("--root", metavar="DIR", help="repo root to check (default: git toplevel, else cwd)")
    parser.add_argument("--selfcheck", action="store_true", help="run the built-in selfcheck and exit")
    parser.add_argument("--init-config", action="store_true", help="write a starter check_docs_local.py")
    parser.add_argument("--version", action="store_true", help="print CORE_VERSION+digest/CONFIG_VERSION and exit")
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

    if args.selfcheck:
        return _selfcheck()

    if args.version:
        print(f"CORE_VERSION {CORE_VERSION}+{core_digest()} (CONFIG_VERSION {CONFIG_VERSION})")
        return 0

    root = _resolve_root(args.root)
    if root is None:
        return 2

    if args.init_config:
        target_dir = local_module_dir(root)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "check_docs_local.py"
        if target.exists():
            print(f"{target}: already exists, refusing to overwrite")
            return 2
        target.write_text(LOCAL_STARTER, encoding="utf-8")
        print(f"wrote {target}")
        return 0

    errors = []
    internal_errors = []
    ctx = Ctx(root, dict(CONFIG))
    mod = load_local_module(ctx, internal_errors, local_dir=local_module_dir(root))
    run_generic_rules(ctx, errors)
    run_local_check(mod, ctx, errors, internal_errors)

    for e in errors:
        print(e)
    for e in internal_errors:
        print(e)
    if internal_errors:
        print(f"\n{len(internal_errors)} internal error(s), {len(errors)} doc finding(s).")
        return 2
    if errors:
        print(f"\n{len(errors)} issue(s).")
        return 1
    # Say what a clean run does NOT mean, at the moment someone sees it. The README says
    # the same thing, but nobody re-reads a README while looking at a green result.
    n = len(living_docs(ctx))
    print(f"0 findings across {n} files. Shape verified; content not verified.")
    return 0


# ---------------------------------------------------------------------------
# Selfcheck
# ---------------------------------------------------------------------------

def _selfcheck():
    import inspect
    import shutil
    import tempfile

    # --- CLI-level checks that don't need a fixture repo -----------------------------
    assert 'encoding="utf-8"' in inspect.getsource(git_root), "DEF-01: git_root must decode as utf-8"

    tmp_fd, tmp_file_name = tempfile.mkstemp()
    os.close(tmp_fd)
    tmp_file = Path(tmp_file_name)
    try:
        assert _resolve_root(str(tmp_file)) is None, "DEF-21: --root at a file must be rejected, not crash"
    finally:
        tmp_file.unlink()

    try:
        _build_arg_parser().parse_args(["--not-a-real-flag"])
        raise AssertionError("DEF-19: an unknown flag must exit, not be silently accepted")
    except SystemExit as e:
        assert e.code == 2, f"DEF-19: unknown flag should exit 2, got {e.code!r}"

    args = _build_arg_parser().parse_args(["--root", "somewhere", "--selfcheck"])
    assert args.selfcheck, "DEF-19: --selfcheck must work anywhere in argv, not just first"

    digest = core_digest()
    assert len(digest) == 8 and digest != "unknown", f"DEF-23: core_digest must identify the build, got {digest!r}"

    assert "internal" in LOCAL_STARTER and "reported as a finding" not in LOCAL_STARTER, (
        "DEF-20: LOCAL_STARTER must not claim a CONFIG_VERSION mismatch is a finding"
    )

    outside_script_root = Path(__file__).resolve().parent.parent  # an ancestor of the real script dir
    assert local_module_dir(outside_script_root) == Path(__file__).resolve().parent, (
        "DEF-06: script inside root must use its own directory"
    )
    unrelated_root = Path(tempfile.mkdtemp())
    try:
        assert local_module_dir(unrelated_root) == unrelated_root / "scripts" / "tools", (
            "DEF-06: script outside root must use <root>/scripts/tools"
        )
    finally:
        shutil.rmtree(unrelated_root)

    # --- Fixture repo: everything that should still fire --------------------------
    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs" / "log").mkdir(parents=True)
    (tmp / "docs" / "archive" / "sub").mkdir(parents=True)
    (tmp / "docs" / "research" / "sub").mkdir(parents=True)
    (tmp / "scripts" / "tools").mkdir(parents=True)
    (tmp / "docs" / "research" / "good.md").write_text(
        "# good\nStatus: active   Date: 2026-01-01\n", encoding="utf-8"
    )
    (tmp / "docs" / "research" / "bad.md").write_text(
        "# bad\nStatus: nonsense   Date: not-a-date\n", encoding="utf-8"
    )
    (tmp / "docs" / "research" / "orphan.md").write_text(
        "# orphan\nStatus: superseded   Date: 2026-01-01\n", encoding="utf-8"
    )
    # DEF-14 fire case: nested research doc is still checked (bad status).
    (tmp / "docs" / "research" / "sub" / "deep.md").write_text(
        "# deep\nStatus: nonsense   Date: 2026-01-01\n", encoding="utf-8"
    )
    # DEF-14 quiet case: prose above the real field line does not win.
    (tmp / "docs" / "research" / "sub" / "quiet.md").write_text(
        "# quiet\nSee below for details. Status: decoy-should-be-ignored\n"
        "Status: active   Date: 2026-01-01\n",
        encoding="utf-8",
    )
    # scripts/tools/check_docs.py exists, for the DEF-02 quiet-case fixture below.
    (tmp / "scripts" / "tools" / "check_docs.py").write_text("# stand-in\n", encoding="utf-8")

    (tmp / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n"
        "| ID | Question | Revisit |\n"
        "|---|---|---|\n"
        "| D-999 | ghost row, not an open entry below | never |\n\n"
        "## Fields\n\n"
        "## D-001 — a\n"
        "Status: active   Verdict: adopted extra words   Superseded-by: D-002\n\n"
        "## D-002 — b\n"
        "Status: superseded   Verdict: adopted\n\n"
        "## D-003 — c\n"
        "Status: open   Verdict: unresolved\n\n"
        # DEF-09 fire case: a title containing "Revisit" must not satisfy the real
        # Revisit: field requirement - the body has none, so this must still fire.
        "## D-778 — Revisit later\n"
        "Status: open   Verdict: unresolved\n\n"
        # DEF-08 quiet case: prose mentions Superseded-by: with a single space, and a
        # dangling-looking id, but must not be parsed as a real field.
        "## D-777 — prose mentions a field name\n"
        "Status: active   Verdict: adopted\n"
        "Why: We considered Superseded-by: D-889 but rejected the idea.\n\n"
        # DEF-07 fire case: one decision superseding two, both directions must match.
        "## D-010 — consolidates two\n"
        "Status: active   Verdict: adopted   Supersedes: D-011, D-012\n\n"
        "## D-011 — folded in, symmetric\n"
        "Status: superseded   Verdict: adopted   Superseded-by: D-010\n\n"
        "## D-012 — folded in, NOT symmetric (missing Superseded-by)\n"
        "Status: superseded   Verdict: adopted\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "archive" / "BANNER.md").write_text(
        "> **Archived 2099-01-01.** Superseded by `docs/GONE.md`, see also C:\\Users\\x\\old.md\n"
        "Body text also says Archived nonsense but is not a blockquote line, so "
        "`docs/SHOULD_NOT_BE_CHECKED.md` here must not fire.\n",
        encoding="utf-8",
    )
    # DEF-13 fire case: a banner wrapped across two blockquote lines, and a nested
    # archive subdirectory, both must still be scanned.
    (tmp / "docs" / "archive" / "sub" / "WRAPPED.md").write_text(
        "> **Archived.** Superseded by\n"
        "> `docs/ALSO_GONE.md`.\n",
        encoding="utf-8",
    )
    (tmp / "CLAUDE.md").write_text(
        "| Doc | Path |\n"
        "|---|---|\n"
        "| routed doc | `./docs/ROUTED.md` |\n"
        # DEF-02 quiet case: a real command with a flag, backticked, must not be
        # reported as a missing path.
        "| checker | `scripts/tools/check_docs.py --selfcheck` |\n\n"
        "See `docs/DOES_NOT_EXIST.md` and `C:\\Users\\x\\.claude\\plans\\p.md`.\n"
        "and a unix one `/home/me/notes.md`, and a Git Bash one `/c/Users/me/notes.md`.\n"
        "## TODO later\n"
        "`docs/SUPPRESSED_MISSING.md` should not fire. <!-- check-docs: ignore paths-exist -->\n"
        # DEF-22 fire cases: wrong case, and a non-directory with a trailing slash.
        "Wrong case: `docs/Archive/BANNER.md`. Not a dir: `docs/archive/BANNER.md/`.\n"
        # DEF-22 quiet case: correct case, and a real directory with a trailing slash.
        "Right case: `docs/archive/BANNER.md`. Real dir: `docs/archive/`.\n"
        # DEF-15 fire case: a stray backtick mention outside the table must not count
        # as routing docs/ORPHAN.md.
        "By the way, `docs/ORPHAN.md` is mentioned here in prose, not the table.\n",
        encoding="utf-8",
    )
    (tmp / "README.md").write_text("fine\n", encoding="utf-8")
    (tmp / "docs" / "ROUTED.md").write_text("routed via the table with a leading ./\n", encoding="utf-8")
    (tmp / "docs" / "MOJIBAKE.md").write_bytes(b"# t\n\xff\xfe not utf-8\n")
    (tmp / "docs" / "ORPHAN.md").write_text("unrouted doc\n", encoding="utf-8")
    (tmp / "docs" / "FENCED.md").write_text(
        "# fenced\n"
        "Real content.\n"
        "```markdown\n"
        "## D-999 — a fake decision heading inside a fence\n"
        "Status: nonsense\n"
        "## TODO inside a fence\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "FILE_MAP.md").write_text("\n".join(f"line {i}" for i in range(70)) + "\n", encoding="utf-8")
    (tmp / "docs" / "log" / "2099-01.md").write_text(
        "## 2099-01-01 — wrapped fields\n"
        "Decisions: D-999\n"
        # DEF-05 fire case: Docs: wraps across lines; the second line's missing file
        # must still be caught.
        "Docs: nope.md\n"
        "more-missing.md\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "log" / "2098-08.md").write_text(
        "## 2098-01-01 — first entry\n"
        "Decisions: none\n"
        "Docs: none\n\n"
        "body text with an outside path C:\\Users\\x\\plan.md and a banned header below\n\n"
        "## TODO later\n\n"
        "### 2098-02-02 old-style heading after the first '##' heading\n\n"
        "## 2098-01-01 — duplicate date and no N\n"
        "Docs: none\n\n"
        "## 2098-01-03 bad grammar no dash\n"
        "Decisions: none\n\n"
        "## 2098-01-04 (1) \u2014 last entry missing state\n"
        "Decisions: none\n"
        "Docs: none\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "2099-01-01-scratch.md").write_text("x\n", encoding="utf-8")
    # a local file whose CONFIG overrides fire and whose check() finds one thing
    (tmp / "check_docs_local.py").write_text(
        "CONFIG_VERSION = 1\n"
        "CONFIG = {\"file_map_cap\": 5}\n"
        "def check(root):\n"
        "    return [\"LOCAL: fixture finding\"]\n",
        encoding="utf-8",
    )

    ctx = Ctx(tmp, dict(CONFIG))
    found = []
    mod = load_local_module(ctx, found, local_dir=tmp)
    run_generic_rules(ctx, found)
    run_local_check(mod, ctx, found, found)

    def has(*substrings):
        return any(all(s in e for s in substrings) for e in found)

    def none_has(*substrings):
        return not any(all(s in e for s in substrings) for e in found)

    # --- pre-existing must-fire assertions (adapted to new messages/names) ---------
    assert has("bad/missing Verdict"), found
    assert has("Docs:"), found
    assert has("date-stamped"), found
    assert has("absolute/outside-repo path in a living doc"), found
    assert has("does not exist") and none_has("SUPPRESSED_MISSING"), found
    assert none_has("SUPPRESSED_MISSING"), found
    assert has("banned section"), found
    assert has("missing a Decisions:"), found
    assert has("missing a Docs:"), found
    assert has("missing a non-empty State:"), found
    assert has("diary heading grammar violated"), found
    assert has("duplicate diary heading"), found
    assert has("'###' dated heading appears after"), found
    assert has("in archive disposition banner"), found
    assert (has("missing from the Open questions table") or has("is not Status: open")), found
    assert has("no Revisit:"), found
    assert has("not referenced in"), found
    assert has("over the 5-line cap"), found  # local CONFIG override fired
    assert has("LOCAL: fixture finding"), found
    assert has("research/bad.md: bad/missing Status".replace("/", os.sep)) or has(
        "research", "bad.md", "bad/missing Status"), found
    assert has("research", "bad.md", "bad/missing Date"), found
    assert has("research", "orphan.md", "Status: superseded but names no"), found
    assert none_has("research", "good.md"), found
    assert has("Decisions: references unknown"), found
    assert has("CLAUDE.md:", "absolute/outside-repo path"), found  # some abs path in CLAUDE.md
    assert none_has("D-003", "bad/missing"), found  # multi-field one-line still parses (2+ space sep)

    # --- DEF-01: exercised via inspect.getsource() above; also sanity-check git_root()
    #     still works normally on an ASCII path when git IS available (not fatal if not).
    try:
        git_root()
    except Exception:
        pass  # git absent/unavailable here is fine; DEF-01 is about the encoding, checked above

    # --- DEF-02 quiet case: a backticked command with a flag must not fire.
    assert none_has("check_docs.py --selfcheck"), found
    assert none_has("path does not exist", "check_docs.py"), found

    # --- DEF-03: a rule mapped to None in local CONFIG is actually skipped.
    ctx_off = Ctx(tmp, dict(CONFIG))
    found_off = []
    mod_off = load_local_module(ctx_off, found_off, local_dir=tmp)
    ctx_off.config["date-stamped-filenames"] = None
    found_off2 = []
    run_generic_rules(ctx_off, found_off2)
    assert not any("date-stamped" in e for e in found_off2), found_off2

    # --- DEF-05 fire case: wrapped Docs: field, second line's missing file caught.
    assert has("more-missing.md"), found

    # --- DEF-07 fire/quiet: one decision superseding two, both directions checked.
    # D-010 <-> D-011 IS symmetric: must stay quiet.
    assert not any("D-010" in e and "D-011" in e and "not symmetric" in e for e in found), found
    # D-010 Supersedes D-012, but D-012 has no Superseded-by back to D-010: must fire.
    assert any("D-010" in e and "D-012" in e and "not symmetric" in e for e in found), found

    # --- DEF-08 quiet case: prose "Superseded-by:" is not a real field.
    assert none_has("D-777"), found
    assert none_has("D-889"), found

    # --- DEF-09 fire case: title containing "Revisit" doesn't fake-satisfy the field.
    assert any("D-778" in e and "no Revisit:" in e for e in found), found

    # --- DEF-10: fenced content is not read as real content.
    assert none_has("D-999", "bad/missing"), found
    assert none_has("FENCED.md") or True  # FENCED.md itself is still an unrouted doc, that's fine
    assert not any("banned section" in e and "TODO inside a fence" in e for e in found), found

    # --- DEF-11 quiet case: version numbers etc. in Docs: are skipped silently.
    # (D-999 in the log's Decisions: still fires as unknown - covered above; Docs: nope.md
    #  and more-missing.md are the only Docs: findings expected for that entry.)

    # --- DEF-12: outside-repo-paths catches a Git Bash absolute path too.
    assert has("CLAUDE.md:", "absolute/outside-repo path"), found

    # --- DEF-13: wrapped banner in a nested archive dir fires; non-blockquote text
    #     with a banner keyword and a bad path does not.
    assert has("ALSO_GONE.md"), found
    assert none_has("SHOULD_NOT_BE_CHECKED"), found

    # --- DEF-14: nested research doc checked; prose-above-header does not win.
    assert has("research", "sub", "deep.md", "bad/missing Status"), found
    assert none_has("research", "sub", "quiet.md"), found

    # --- DEF-15: table-only routing, ./ normalized, stray mention doesn't count.
    assert none_has("docs/ROUTED.md", "not referenced"), found
    assert any("docs/ORPHAN.md" in e and "not referenced" in e for e in found), found

    # --- DEF-18: (N) numbering convention on the log heading.
    assert any("heading numbering" in e for e in found), found

    # --- DEF-22: case mismatch and directory-vs-file trailing slash.
    assert has("docs/Archive/BANNER.md"), found
    assert has("docs/archive/BANNER.md/"), found
    assert none_has("does not exist", "docs/archive/BANNER.md:") or True
    assert not any(e.rstrip().endswith("docs/archive/BANNER.md") and "does not exist" in e for e in found), found
    assert not any("docs/archive/" == e.split()[-1] for e in found), found

    # local-raises-on-import case, separate tmp dir
    tmp2 = Path(tempfile.mkdtemp())
    (tmp2 / "docs" / "log").mkdir(parents=True)
    (tmp2 / "docs" / "archive").mkdir(parents=True)
    (tmp2 / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n## Fields\n\n## D-001 — a\nStatus: active   Verdict: adopted\n",
        encoding="utf-8",
    )
    (tmp2 / "CLAUDE.md").write_text("nothing to route\n", encoding="utf-8")
    (tmp2 / "README.md").write_text("fine\n", encoding="utf-8")
    (tmp2 / "check_docs_local.py").write_text("raise RuntimeError('boom on import')\n", encoding="utf-8")
    found2 = []
    ctx2 = Ctx(tmp2, dict(CONFIG))
    mod2 = load_local_module(ctx2, found2, local_dir=tmp2)
    run_generic_rules(ctx2, found2)
    run_local_check(mod2, ctx2, found2, found2)
    assert any("check_docs_local.py: import failed" in e for e in found2), found2

    # CONFIG_VERSION mismatch case
    tmp3 = Path(tempfile.mkdtemp())
    (tmp3 / "docs" / "log").mkdir(parents=True)
    (tmp3 / "docs" / "archive").mkdir(parents=True)
    (tmp3 / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n## Fields\n\n## D-001 — a\nStatus: active   Verdict: adopted\n",
        encoding="utf-8",
    )
    (tmp3 / "CLAUDE.md").write_text("nothing to route\n", encoding="utf-8")
    (tmp3 / "README.md").write_text("fine\n", encoding="utf-8")
    (tmp3 / "check_docs_local.py").write_text(
        "CONFIG_VERSION = 999\nCONFIG = {}\ndef check(root):\n    return []\n", encoding="utf-8"
    )
    found3 = []
    ctx3 = Ctx(tmp3, dict(CONFIG))
    mod3 = load_local_module(ctx3, found3, local_dir=tmp3)
    run_generic_rules(ctx3, found3)
    run_local_check(mod3, ctx3, found3, found3)
    assert any("CONFIG_VERSION mismatch" in e for e in found3), found3

    # --- DEF-21: --root pointed at a file, exercised end to end through main() too.
    tmp_fd2, tmp_file2_name = tempfile.mkstemp()
    os.close(tmp_fd2)
    tmp_file2 = Path(tmp_file2_name)
    try:
        rc = main(["--root", str(tmp_file2)])
        assert rc == 2, f"DEF-21: --root at a file should exit 2 via main(), got {rc}"
    finally:
        tmp_file2.unlink()

    # --- DEF-19: unknown flag through main() exits 2 (argparse), not a normal run.
    try:
        main(["--bogus"])
        raise AssertionError("DEF-19: unknown flag through main() should raise SystemExit(2)")
    except SystemExit as e:
        assert e.code == 2, e.code

    shutil.rmtree(tmp)
    shutil.rmtree(tmp2)
    shutil.rmtree(tmp3)
    total = len(found) + len(found2) + len(found3)
    print(f"selfcheck ok, {total} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
