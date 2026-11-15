#!/usr/bin/env bash
# Marks the session busy/idle for the status line's Clawd animation. Prints nothing.
sid=$(jq -r '.session_id // "default"' 2>/dev/null); [ -z "$sid" ] && sid=default
f="${TMPDIR:-/tmp}/clawd-busy-$sid"
if [ "$1" = busy ]; then touch "$f"; else rm -f "$f"; fi
exit 0
