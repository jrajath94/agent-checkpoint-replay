"""Run the agent with write-ahead logging, checkpoints, and crash resume.

Fresh run:   run(log_path)
Resume:      run(log_path, resume=True)  -- fsck, drop torn tail, restore the
             latest checkpoint snapshot, continue from the next seq. A tool
             whose result is already logged is never re-executed: the snapshot
             already includes its applied result, so the loop just continues.
"""
import argparse
import json
import os
import time

from . import agent
from . import log as logmod
from . import tools

DEFAULT_CHECKPOINT_EVERY = 5
SLOW_DELAY = 0.3  # seconds per step in --slow mode, so a demo can kill mid-run


def _default_fixtures_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures"))


def call_tool(tool, args, store):
    """Dispatch one tool call. store is the runner-owned kv dict."""
    if tool == "kv":
        return tools.kv(store, **args)
    if tool == "calc":
        return tools.calc(**args)
    if tool == "search":
        return tools.search(**args)
    raise ValueError("unknown tool: %r" % (tool,))


def store_from_log(path):
    """Rebuild the kv store from completed (step, result) pairs in the log.

    Only pairs with a logged result count: a step with no result never
    completed, so its intent must not leak into recovered state.
    """
    store = {}
    for step, _result in logmod.iter_pairs(logmod.iter_records(path)):
        if step["tool"] != "kv":
            continue
        args = step["args"]
        if args["op"] == "put":
            store[args["key"]] = args["value"]
        elif args["op"] == "delete":
            store.pop(args["key"], None)
    return store


def _truncate_to_valid_prefix(path):
    """Cut the file back to the last complete record.

    Drops a torn tail line (partial JSON from a SIGKILL mid-write) and a
    trailing step with no result (write-ahead intent that never completed).
    Truncating to a valid prefix is standard WAL recovery.
    """
    with open(path) as f:
        content = f.read()
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except ValueError:
            parsed.append(None)
    cut = len(parsed)
    while cut > 0 and parsed[cut - 1] is None:
        cut -= 1  # torn tail
    if cut > 0 and parsed[cut - 1]["type"] == "step":
        cut -= 1  # orphan step: intent logged, result never landed
    with open(path, "w") as f:
        for line in lines[:cut]:
            f.write(line + "\n")
    return [r for r in parsed[:cut]]


def _recover(log_path):
    records = _truncate_to_valid_prefix(log_path)
    problems = logmod.fsck(log_path)
    if problems:
        raise RuntimeError("cannot resume, log failed fsck: " + "; ".join(problems))
    return records


def run(log_path, resume=False, checkpoint_every=DEFAULT_CHECKPOINT_EVERY,
        slow=False, fixtures_dir=None):
    fixtures_dir = os.path.abspath(fixtures_dir or _default_fixtures_dir())
    records = []
    if resume and os.path.exists(log_path) and os.path.getsize(log_path) > 0:
        records = _recover(log_path)

    elog = logmod.EventLog(log_path)
    if records:
        print("RESUME from seq %d (%d records)"
              % (records[-1]["seq"], len(records)), flush=True)
        ckpts = [r for r in records if r["type"] == "checkpoint"]
        state = ckpts[-1]["snapshot"] if ckpts else agent.initial_state()
        # The log tail may hold completed results beyond the latest
        # checkpoint. Apply them forward with RECORDED outputs (never call
        # tools) so state matches the log; otherwise we would re-execute
        # an already-logged tool call.
        ckpt_seq = ckpts[-1]["seq"] if ckpts else -1
        for step, result in logmod.iter_pairs(
                r for r in records if r["seq"] > ckpt_seq):
            state = agent.apply(state, step["tool"], step["args"],
                                result["output"])
        if records[-1]["type"] == "done":
            elog.close()
            print("log already complete, nothing to do", flush=True)
            return {"state": state, "kv": store_from_log(log_path),
                    "actions": [], "steps": 0}
        seq = records[-1]["seq"] + 1
        step_count = sum(1 for r in records if r["type"] == "step")
        store = store_from_log(log_path)
    else:
        state = agent.initial_state()
        seq = 0
        step_count = 0
        store = {}
    state["scratch"]["fixtures_dir"] = fixtures_dir
    actions = []

    while True:
        tool, args = agent.next_action(state)
        if tool == "DONE":
            break
        elog.append({"type": "step", "seq": seq, "tool": tool,
                     "args": args, "rng_state": state["rng_state"]})
        seq += 1
        output = call_tool(tool, args, store)
        elog.append({"type": "result", "seq": seq, "tool": tool, "output": output})
        seq += 1
        state = agent.apply(state, tool, args, output)
        actions.append((tool, args))
        step_count += 1
        print("STEP %d %s %s" % (step_count, tool, json.dumps(args, sort_keys=True)),
              flush=True)
        if step_count % checkpoint_every == 0 and agent.next_action(state)[0] != "DONE":
            elog.append({"type": "checkpoint", "seq": seq, "snapshot": state})
            print("CHECKPOINT seq=%d" % seq, flush=True)
            seq += 1
        if slow:
            time.sleep(SLOW_DELAY)

    elog.append({"type": "checkpoint", "seq": seq, "snapshot": state})
    seq += 1
    elog.append({"type": "done", "seq": seq})
    elog.close()
    print("DONE steps=%d answer=%r" % (step_count, store.get("answer")), flush=True)
    return {"state": state, "kv": dict(store), "actions": actions,
            "steps": step_count}


def main(argv=None):
    ap = argparse.ArgumentParser(description="checkpoint/replay demo runner")
    ap.add_argument("log", help="path to the JSONL event log")
    ap.add_argument("--resume", action="store_true",
                    help="resume from the latest checkpoint in the log")
    ap.add_argument("--checkpoint-every", type=int, default=DEFAULT_CHECKPOINT_EVERY)
    ap.add_argument("--slow", action="store_true",
                    help="sleep 0.3s per step so a crash demo can kill mid-run")
    args = ap.parse_args(argv)
    run(args.log, resume=args.resume,
        checkpoint_every=args.checkpoint_every, slow=args.slow)


if __name__ == "__main__":
    main()
