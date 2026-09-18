#!/usr/bin/env python3
"""Generic docs hygiene checker. Stdlib only. A config-driven core plus an
optional check_docs_local.py extension point for repo-specific rules.

Exit 0 and silent on success. Exit 1 on doc findings, exit 2 on an internal error
(bad --root, local-file import failure, CONFIG_VERSION mismatch). Prints one line per
finding either way.

Generic rules (stable string ids, used as CONFIG keys, in inline suppression comments,
and in output):
  decisions-integrity   Unique IDs in the decision register, closed-vocabulary Status/
                         Verdict read to the end of the field, symmetric supersession.
  log-fields-resolve    docs/log/*.md 'Decisions:'/'Docs:' fields resolve to real ids/paths.
  date-stamped-filenames No date-stamped filename under docs/ outside the exempt dirs.
  outside-repo-paths    No absolute or outside-repo path in a living doc.
  paths-exist           Backtick-quoted repo paths in living docs must exist.
  banned-headers        No TODO/Next Steps/Future Work headers outside the decisions file.
  diary-grammar         Log heading grammar, required fields, last entry needs State:.
  archive-banner-paths  Archive disposition banner lines cite real, in-repo paths.
  open-questions-sync   Open-questions table <-> Status: open entries, Revisit: required.
  routing-coverage      Every living doc is routed in the routing file's table.
  file-map-cap          The file-map doc (if configured) stays under its line cap.

Repo-specific rules live in a sibling check_docs_local.py (see --init-config), loaded via
load_local_module()/run_local_check() and run after the generic rules.

Suppression, four layers (see LOCAL_STARTER for the long version):
  1. exempt_dirs                                    - whole directories, always exempt.
  2. routing_exempt_topdirs                          - docs/<topdir> exempt from routing-coverage only.
  3. CONFIG["<rule-id>"] = None                       - disables that rule repo-wide.
  4. <!-- check-docs: ignore <rule-id> --> on a line   - suppresses one hit on that line.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

CORE_VERSION = "1.0.0"
CONFIG_VERSION = 1

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
    "file_map": "docs/FILE_MAP.md",
    "file_map_cap": 60,
    "banned_header_re": r"^#+.*\b(TODO|Next Steps|Future Work)\b",
    "outside_path_re": r"[A-Za-z]:\\|~[\\/]|(?:^|[\s`(\[])/(?:home|Users|root)/",
    "path_suppressed_prefixes": ("output/",),
    "path_cmd_prefixes": ("python ", "python3 "),
}

def read_doc(p):
    """Never raise on a stray non-UTF-8 byte; a mojibake char just fails some other rule."""
    return p.read_text(encoding="utf-8", errors="replace")


NO_ROUTE_MARKER = "<!-- no-route -->"  # deprecated; routing-coverage only, still honored
SUPPRESS_RE = re.compile(r"<!--\s*check-docs:\s*ignore\s+([\w-]+)\s*-->")
PLACEHOLDER = ("<", "*", "..", "path/to", "YYYY", "{", "|")
PATH_LIKE = re.compile(r"^[\w][\w.\- ]*(/[\w][\w.\- ]*)+$")
BANNER_WORDS = ("Superseded", "Archived", "Disposition")
FIELD_RE_TMPL = r"{}:\s*(.*?)(?=\s+\S+:|$)"


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

    def is_exempt(self, p):
        return any(d in p.parents or d == p for d in self.exempt_dirs)


def living_docs(ctx):
    files = [ctx.root / name for name in ctx.config["living_roots"] if (ctx.root / name).exists()]
    if ctx.docs:
        files += [p for p in ctx.docs.rglob("*.md") if not ctx.is_exempt(p)]
    return files


def top_level_names(ctx):
    names = {p.name for p in ctx.root.iterdir()}
    names |= set(ctx.config["living_roots"])
    return names


def candidate_path(ctx, span, known_roots):
    """Normalize a raw text span to a repo-relative path to check, or None to skip it."""
    cfg = ctx.config
    s = span.strip().strip("\"'")
    for pre in cfg["path_cmd_prefixes"]:
        if s.startswith(pre):
            s = s[len(pre):]
    if "/" not in s or any(x in s for x in PLACEHOLDER):
        return None
    if s.startswith(("http://", "https://")):
        return None
    s = re.sub(r":\d+(-\d+)?$", "", s.rstrip(":,.\"'()"))
    if s.startswith(tuple(cfg["path_suppressed_prefixes"])) or not PATH_LIKE.match(s):
        return None
    if s.split("/", 1)[0] not in known_roots:
        return None
    return s


def _bare_path_tokens(root, line):
    # Bare (non-backtick) whitespace-split tokens containing a "/". Some repos have real
    # filenames with a space; if a token doesn't exist but merging with the next word does,
    # prefer the merged form so those don't false-positive as missing.
    words = line.split()
    tokens = []
    skip_next = False
    for idx, w in enumerate(words):
        if skip_next:
            skip_next = False
            continue
        if "/" not in w:
            continue
        if idx + 1 < len(words):
            merged = w + " " + words[idx + 1]
            if (root / merged.rstrip(").,:;\"'")).exists():
                tokens.append(merged)
                skip_next = True
                continue
        tokens.append(w)
    return tokens


def scan_line_for_paths(ctx, errors, p, i, line, label, known_roots, rule_id):
    """Flag an outside-repo path and any non-existent repo-relative path on one line."""
    cfg = ctx.config
    if line_ignored(line, rule_id):
        return
    outside_re = cfg["outside_path_re"]
    if outside_re and re.search(outside_re, line):
        errors.append(f"{p.relative_to(ctx.root)}:{i}: outside-repo path in {label}")
    spans = re.findall(r"`([^`]+)`", line) + _bare_path_tokens(ctx.root, line)
    seen = set()
    for span in spans:
        s = candidate_path(ctx, span, known_roots)
        if s is None or s in seen:
            continue
        seen.add(s)
        if not (ctx.root / s).exists():
            errors.append(f"{p.relative_to(ctx.root)}:{i}: path does not exist in {label}: {s}")


# ---------------------------------------------------------------------------
# Generic rules
# ---------------------------------------------------------------------------

def check_decisions_integrity(ctx, errors):
    cfg = ctx.config
    if not cfg["decisions_file"]:
        return set()
    p = ctx.root / cfg["decisions_file"]
    if not p.exists():
        errors.append(f"{cfg['decisions_file']}: file does not exist")
        return set()
    prefix = re.escape(cfg["id_prefix"])
    id_re = re.compile(prefix + r"\d+")
    text = read_doc(p)
    entries = re.split(rf"(?=^## {prefix}\d+)", text, flags=re.M)[1:]
    status_re = re.compile(FIELD_RE_TMPL.format("Status"), re.M)
    verdict_re = re.compile(FIELD_RE_TMPL.format("Verdict"), re.M)
    ids, superseded_by, supersedes = {}, {}, {}
    for e in entries:
        m = re.match(rf"## ({prefix}\d+)", e)
        eid = m.group(1)
        if eid in ids:
            errors.append(f"{cfg['decisions_file']}: duplicate id {eid}")
        ids[eid] = e
        status_m = status_re.search(e)
        verdict_m = verdict_re.search(e)
        status = status_m.group(1).strip() if status_m else None
        verdict = verdict_m.group(1).strip() if verdict_m else None
        if status not in cfg["status_vocab"]:
            errors.append(f"{cfg['decisions_file']}: {eid} bad/missing Status")
        if verdict not in cfg["verdict_vocab"]:
            errors.append(f"{cfg['decisions_file']}: {eid} bad/missing Verdict")
        if status == "superseded" and not re.search(rf"Superseded-by:\s*{id_re.pattern}", e):
            errors.append(f"{cfg['decisions_file']}: {eid} is superseded but names no Superseded-by target")
        sb = re.search(rf"Superseded-by:\s*({id_re.pattern})", e)
        sp = re.search(rf"Supersedes:\s*({id_re.pattern})", e)
        if sb:
            superseded_by[eid] = sb.group(1)
        if sp:
            supersedes[eid] = sp.group(1)
    for eid, target in superseded_by.items():
        if target not in ids:
            errors.append(f"{cfg['decisions_file']}: {eid} Superseded-by dangles at {target}")
        elif supersedes.get(target) != eid:
            errors.append(f"{cfg['decisions_file']}: {eid}<->{target} supersession is not symmetric")
    for eid, target in supersedes.items():
        if target not in ids:
            errors.append(f"{cfg['decisions_file']}: {eid} Supersedes dangles at {target}")
    return set(ids)


def check_log_fields_resolve(ctx, errors, decision_ids):
    cfg = ctx.config
    if not cfg["log_dir"]:
        return
    log_dir = ctx.root / cfg["log_dir"]
    if not log_dir.exists():
        return
    prefix = re.escape(cfg["id_prefix"])
    id_re = re.compile(prefix + r"\d+")
    for log in sorted(log_dir.glob("*.md")):
        text = read_doc(log)
        if decision_ids is not None:
            for m in re.finditer(r"^Decisions:\s*(.+)$", text, flags=re.M):
                for d in id_re.findall(m.group(1)):
                    if d not in decision_ids:
                        errors.append(f"{log.name}: Decisions: references unknown {d}")
        for m in re.finditer(r"^Docs:\s*(.+)$", text, flags=re.M):
            for path in re.findall(r"[\w./-]+\.\w+", m.group(1)):
                if not (ctx.root / path).exists():
                    errors.append(f"{log.name}: Docs: references missing {path}")


DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def check_date_stamped_filenames(ctx, errors):
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
    for p in docs:
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
            for span in re.findall(r"`([^`]+)`", line):
                s = candidate_path(ctx, span, known_roots)
                if s is not None and not (ctx.root / s).exists():
                    errors.append(f"{p.relative_to(ctx.root)}:{i}: path does not exist: {s}")


def check_banned_headers(ctx, errors, docs):
    header_re = ctx.config["banned_header_re"]
    if not header_re:
        return
    pat = re.compile(header_re, re.I)
    decisions_name = Path(ctx.config["decisions_file"]).name if ctx.config["decisions_file"] else None
    for p in docs:
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


def check_diary_grammar(ctx, errors):
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
        for m in DIARY_HEADING_LINE_RE.finditer(text):
            heading = m.group(0)
            lineno = text[:m.start()].count("\n") + 1
            if not DIARY_HEADING_GRAMMAR_RE.match(heading):
                errors.append(f"{log.name}:{lineno}: diary heading grammar violated: {heading.strip()}")
            hm = DIARY_HEAD_START_RE.match(heading)
            key = (hm.group(1), hm.group(2) or "")
            if key in seen_keys:
                errors.append(f"{log.name}:{lineno}: duplicate diary heading date+N {key}")
            seen_keys.add(key)

        entries = re.split(r"(?=^## \d{4}-\d{2}-\d{2})", text, flags=re.M)[1:]
        for e in entries:
            head = e.splitlines()[0].strip()
            if not re.search(r"^Decisions:", e, re.M):
                errors.append(f"{log.name}: entry '{head}' missing a Decisions: line")
            if not re.search(r"^Docs:", e, re.M):
                errors.append(f"{log.name}: entry '{head}' missing a Docs: line")
        if entries:
            last = entries[-1]
            head = last.splitlines()[0].strip()
            sm = re.search(r"^State:\s*(.*)$", last, re.M)
            if not sm or not sm.group(1).strip():
                errors.append(f"{log.name}: last entry '{head}' missing a non-empty State: line")


def check_archive_banner_paths(ctx, errors):
    if not ctx.archive_dir or not ctx.archive_dir.exists():
        return
    known_roots = top_level_names(ctx)
    for p in sorted(ctx.archive_dir.glob("*.md")):
        for i, line in enumerate(read_doc(p).splitlines(), 1):
            if any(w in line for w in BANNER_WORDS):
                scan_line_for_paths(ctx, errors, p, i, line, "archive disposition banner", known_roots,
                                     "archive-banner-paths")


def check_open_questions_sync(ctx, errors):
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

    status_re = re.compile(FIELD_RE_TMPL.format("Status"), re.M)
    entries = re.split(rf"(?=^## {prefix}\d+)", text, flags=re.M)[1:]
    open_ids = set()
    for e in entries:
        eid = re.match(rf"## ({id_re})", e).group(1)
        status_m = status_re.search(e)
        if status_m and status_m.group(1).strip() == "open":
            open_ids.add(eid)
            if not re.search(r"Revisit:\s*\S", e):
                errors.append(f"{cfg['decisions_file']}: {eid} is Status: open but has no Revisit: trigger")

    for eid in sorted(open_ids - table_ids):
        errors.append(f"{cfg['decisions_file']}: {eid} is Status: open but missing from the Open questions table")
    for eid in sorted(table_ids - open_ids):
        errors.append(f"{cfg['decisions_file']}: {eid} is in the Open questions table but is not Status: open")


def check_routing_coverage(ctx, errors):
    cfg = ctx.config
    if not cfg["routing_file"] or not ctx.docs:
        return
    routing_path = ctx.root / cfg["routing_file"]
    if not routing_path.exists():
        errors.append(f"{cfg['routing_file']}: file does not exist")
        return
    routing_text = read_doc(routing_path)
    routed = set(re.findall(r"`([^`]+)`", routing_text))
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
                errors.append(f"{rel_posix}: not routed in {cfg['routing_file']}'s table "
                               f"(no {NO_ROUTE_MARKER} or check-docs:ignore marker either)")


def check_file_map_cap(ctx, errors):
    cfg = ctx.config
    if not cfg["file_map"] or not cfg["file_map_cap"]:
        return
    p = ctx.root / cfg["file_map"]
    if not p.exists():
        return
    n = len(read_doc(p).splitlines())
    if n > cfg["file_map_cap"]:
        errors.append(f"{cfg['file_map']}: {n} lines, over the {cfg['file_map_cap']}-line cap")


GENERIC_RULES = (
    "decisions-integrity", "log-fields-resolve", "date-stamped-filenames", "outside-repo-paths",
    "paths-exist", "banned-headers", "diary-grammar", "archive-banner-paths", "open-questions-sync",
    "routing-coverage", "file-map-cap",
)


def run_generic_rules(ctx, errors):
    docs = living_docs(ctx)
    docs_plus_log = list(docs)
    if ctx.config["log_dir"]:
        log_dir = ctx.root / ctx.config["log_dir"]
        if log_dir.exists():
            docs_plus_log += sorted(log_dir.glob("*.md"))
    decision_ids = check_decisions_integrity(ctx, errors)
    check_log_fields_resolve(ctx, errors, decision_ids if ctx.config["decisions_file"] else None)
    check_date_stamped_filenames(ctx, errors)
    check_outside_repo_paths(ctx, errors, docs_plus_log)
    check_paths_exist(ctx, errors, docs)
    check_banned_headers(ctx, errors, docs_plus_log)
    check_diary_grammar(ctx, errors)
    check_archive_banner_paths(ctx, errors)
    check_open_questions_sync(ctx, errors)
    check_routing_coverage(ctx, errors)
    check_file_map_cap(ctx, errors)


# ---------------------------------------------------------------------------
# Local extension loading
# ---------------------------------------------------------------------------

def load_local_module(ctx, internal_errors, local_dir=None):
    """Import check_docs_local.py from local_dir (default: this script's own directory,
    i.e. the installed scripts/tools/ layout) and apply its CONFIG overrides to ctx.config
    in place, before any rule runs - local CONFIG overrides must be visible to the generic
    rules too (e.g. a lowered file_map_cap). Returns the module, or None if there is no
    local file or it failed to import (either way, safe to skip check() after)."""
    local_dir = local_dir or Path(__file__).resolve().parent
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
overrides still make sense against the new defaults; a mismatch is reported as a finding,
not a crash.

Four ways to suppress a false positive - pick the narrowest one that fits:
  1. CONFIG["exempt_dirs"] (core CONFIG key, override below) - a whole directory (e.g. a
     vendored subtree) should never be treated as a living doc at all.
  2. CONFIG["routing_exempt_topdirs"] - a whole docs/<topdir> is fine unrouted (evidence,
     history) but should still be checked by every other rule.
  3. CONFIG["<rule-id>"] = None below - the rule itself doesn't apply to this repo (e.g. no
     decision register: CONFIG["decisions_file"] = None disables decisions-integrity and
     open-questions-sync).
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
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip())


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if "--version" in argv:
        print(f"CORE_VERSION {CORE_VERSION} (CONFIG_VERSION {CONFIG_VERSION})")
        return 0

    if "--init-config" in argv:
        root = _resolve_root(argv)
        if root is None:
            return 2
        target = Path(__file__).resolve().parent / "check_docs_local.py"
        if target.exists():
            print(f"{target}: already exists, refusing to overwrite")
            return 2
        target.write_text(LOCAL_STARTER, encoding="utf-8")
        print(f"wrote {target}")
        return 0

    root = _resolve_root(argv)
    if root is None:
        return 2

    errors = []
    internal_errors = []
    ctx = Ctx(root, dict(CONFIG))
    mod = load_local_module(ctx, internal_errors)
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
    return 0


def _resolve_root(argv):
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("--root requires a path argument")
            return None
        root = Path(argv[i + 1]).resolve()
        if not root.exists():
            print(f"--root {root}: does not exist")
            return None
        return root
    try:
        return git_root()
    except Exception as exc:
        print(f"could not resolve repo root via git rev-parse --show-toplevel: {exc!r}")
        return None


# ---------------------------------------------------------------------------
# Selfcheck
# ---------------------------------------------------------------------------

def _selfcheck():
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs" / "log").mkdir(parents=True)
    (tmp / "docs" / "archive").mkdir(parents=True)
    (tmp / "docs" / "research").mkdir(parents=True)
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
        "Status: open Verdict: unresolved\n",  # single-space fields must still parse
        encoding="utf-8",
    )
    (tmp / "docs" / "archive" / "BANNER.md").write_text(
        "> **Archived 2099-01-01.** Superseded by `docs/GONE.md`, see also C:\\Users\\x\\old.md\n",
        encoding="utf-8",
    )
    (tmp / "CLAUDE.md").write_text(
        "See `docs/DOES_NOT_EXIST.md` and `C:\\Users\\x\\.claude\\plans\\p.md`.\n"
        "and a unix one `/home/me/notes.md`.\n"
        "## TODO later\n"
        "`docs/SUPPRESSED_MISSING.md` should not fire. <!-- check-docs: ignore paths-exist -->\n",
        encoding="utf-8",
    )
    (tmp / "README.md").write_text("fine\n", encoding="utf-8")
    (tmp / "docs" / "MOJIBAKE.md").write_bytes(b"# t\n\xff\xfe not utf-8\n")
    (tmp / "docs" / "ORPHAN.md").write_text("unrouted doc\n", encoding="utf-8")
    (tmp / "docs" / "FILE_MAP.md").write_text("\n".join(f"line {i}" for i in range(70)) + "\n", encoding="utf-8")
    (tmp / "docs" / "log" / "2099-01.md").write_text("Decisions: D-999\nDocs: nope.md\n", encoding="utf-8")
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

    assert any("bad/missing Verdict" in e for e in found), found
    assert any("Docs:" in e for e in found), found
    assert any("date-stamped" in e for e in found), found
    assert any("absolute/outside-repo path in a living doc" in e for e in found), found
    assert any("does not exist" in e and "SUPPRESSED_MISSING" not in e for e in found), found
    assert not any("SUPPRESSED_MISSING" in e for e in found), found
    assert any("banned section" in e for e in found), found
    assert any("missing a Decisions:" in e for e in found), found
    assert any("missing a Docs:" in e for e in found), found
    assert any("missing a non-empty State:" in e for e in found), found
    assert any("diary heading grammar violated" in e for e in found), found
    assert any("duplicate diary heading" in e for e in found), found
    assert any("'###' dated heading appears after" in e for e in found), found
    assert any("in archive disposition banner" in e for e in found), found
    assert any("missing from the Open questions table" in e or "is not Status: open" in e for e in found), found
    assert any("no Revisit:" in e for e in found), found
    assert any("not routed in" in e for e in found), found
    assert any("over the 5-line cap" in e for e in found), found  # local CONFIG override fired
    assert any("LOCAL: fixture finding" in e for e in found), found
    assert any("Decisions: references unknown" in e for e in found), found
    assert any("CLAUDE.md:2: absolute/outside-repo path" in e for e in found), found  # unix absolute path, not just Windows
    assert not any("D-003 bad/missing" in e for e in found), found  # single-space fields parse

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

    shutil.rmtree(tmp)
    shutil.rmtree(tmp2)
    shutil.rmtree(tmp3)
    total = len(found) + len(found2) + len(found3)
    print(f"selfcheck ok, {total} findings")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        sys.exit(_selfcheck())
    sys.exit(main(sys.argv[1:]))
