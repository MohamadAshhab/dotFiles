#!/usr/bin/env python3
"""Play Clawd's animations in the terminal: curls (working) then flex (idle)."""
import importlib.util, os, sys, time
os.environ.setdefault("COLORTERM", "truecolor")
spec = importlib.util.spec_from_file_location("sl", os.path.expanduser("~/.claude/statusline.py"))
sl = importlib.util.module_from_spec(spec); spec.loader.exec_module(sl)
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
try:
    for busy, label in ((True, "WORKING  - curls"), (False, "IDLE  - flex pose")):
        for t in range(secs):
            rows = sl.animate(t, busy)
            sys.stdout.write("\033[2J\033[H  %s\n\n" % label + "\n".join("  " + r for r in rows) + "\n")
            sys.stdout.flush(); time.sleep(0.5)
except KeyboardInterrupt:
    pass
