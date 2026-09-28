#!/usr/bin/env python3
"""Run the agent to completion, replay the trace, print both action
sequences side by side and assert they are identical. Exits non-zero on
mismatch."""
import contextlib
import io
import os
import sys
import tempfile

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.getcwd())

from checkpoint_replay import runner
from checkpoint_replay.replay import replay, action_sequence_from_log


def main():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = tmp + "/run.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):  # hide STEP chatter
            result = runner.run(log_path, checkpoint_every=5)
        original = action_sequence_from_log(log_path)
        replayed = replay(log_path)

    print("original (%d actions) vs replayed (%d actions):"
          % (len(original), len(replayed)))
    for i, (o, r) in enumerate(zip(original, replayed)):
        mark = "OK " if o == r else "DIFF"
        print("%2d [%s] %-40s | %s" % (i, mark, "%s %s" % o, "%s %s" % r))
    assert replayed == original, "replay diverged from the original run"
    print("assertion passed: replayed sequence is identical")
    print("final answer:", result["kv"]["answer"])


if __name__ == "__main__":
    main()
