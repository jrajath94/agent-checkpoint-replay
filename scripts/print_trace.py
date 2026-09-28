#!/usr/bin/env python3
"""Print a compact, commented sample trace of a short run for the README.

Regenerate the README quote from this if the record format changes.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.getcwd())

from checkpoint_replay import runner  # noqa: E402

COMMENTS = {
    "step":       "# INTENT (write-ahead): what the agent decided, BEFORE the tool runs",
    "result":     "# OBSERVATION: the tool output, AFTER the tool returns",
    "checkpoint": "# CHECKPOINT: full agent state snapshot, safe to resume from here",
    "done":       "# DONE: terminal marker, the run finished",
}

with tempfile.TemporaryDirectory() as tmp:
    log_path = os.path.join(tmp, "run.jsonl")
    with contextlib.redirect_stdout(io.StringIO()):  # hide STEP chatter
        runner.run(log_path, checkpoint_every=5)
    lines = open(log_path).read().splitlines()

REPO = os.getcwd() + os.sep  # shorten machine-specific paths for display

print("sample trace (%d records, 20 tool steps):" % len(lines))
seen = set()
for line in lines:
    rec = json.loads(line)
    kind = rec["type"]
    if kind not in seen:
        print(COMMENTS[kind])
        seen.add(kind)
    if kind == "step":
        args_s = json.dumps(rec["args"], sort_keys=True).replace(REPO, "")
        print("seq=%-2d step       %-6s %s" % (rec["seq"], rec["tool"], args_s))
    elif kind == "result":
        out = rec["output"]
        out_s = json.dumps(out, sort_keys=True)
        print("seq=%-2d result     %-6s -> %s" % (rec["seq"], rec["tool"], out_s))
    elif kind == "checkpoint":
        snap = rec["snapshot"]
        print("seq=%-2d checkpoint pc=%d scratch_keys=%s"
              % (rec["seq"], snap["pc"], sorted(snap["scratch"].keys())))
    else:
        print("seq=%-2d done" % rec["seq"])
