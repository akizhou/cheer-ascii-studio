#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge a "welcome back" cheer after idle.

Measures wall-clock time since the previous prompt. If the user has been away
longer than the threshold, injects a short context note asking Claude to greet
them back with one braille portrait (the Cheer Me Up output style). Claude
paints the portrait inline -- the hook itself never writes to the transcript
(hooks can't), it only nudges.

Threshold defaults to 15 minutes; override with CHEER_IDLE_SECONDS.
State is a single timestamp file under the user cache dir (not chezmoi-managed).
Fails open and silent: any error just exits 0 so the prompt is never blocked.
"""

import json
import os
import sys
import time

THRESHOLD = int(os.environ.get("CHEER_IDLE_SECONDS", "900"))  # 15 min

STATE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "claude-code-cheer",
    "last-prompt-ts",
)


def main() -> None:
    # Drain stdin so CC doesn't see a broken pipe; payload is unused.
    try:
        sys.stdin.read()
    except Exception:
        pass

    now = time.time()
    prev = None
    try:
        with open(STATE) as f:
            prev = float(f.read().strip())
    except Exception:
        prev = None

    # Record this prompt's time for next round.
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w") as f:
            f.write(str(now))
    except Exception:
        pass

    # No prior prompt (fresh session) or still within threshold -> stay quiet.
    if prev is None or (now - prev) < THRESHOLD:
        sys.exit(0)

    mins = int(round((now - prev) / 60))
    note = (
        "[cheer-me-up] The user is sending their first message after being away "
        f"~{mins} minutes. This is a 'first reply after a while' beat: if the "
        "Cheer Me Up output style is active, open with a warm welcome-back line "
        "in the subject's voice and include exactly one braille portrait (run the "
        "gallery picker, paste it inline). Answer their actual request first. If "
        "that style is not active, ignore this note."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": note,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
