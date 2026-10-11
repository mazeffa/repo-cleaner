#!/usr/bin/env bash
# Launcher for every hook: run.sh <hook> <plugin root>. Finds a Python 3.8+ and execs the hook;
# with none, says so (a hook that does nothing silently is a bug) and exits 0.
for py in "py -3" python python3; do  # python3 last: on Windows it is often the Store stub
  # $py is unquoted on purpose, so "py -3" splits into a command and a flag
  if $py -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec $py "$2/hooks/$1.py"
  fi
done
echo 'repo-clean: no Python 3.8+ found on PATH; hooks disabled'
exit 0
