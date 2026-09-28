"""Checkpoint/restore: run 8 steps, checkpoint, restore into a fresh agent,
assert state equality and identical next action."""
import os

from checkpoint_replay import agent, log as logmod
from checkpoint_replay.log import EventLog, fsck, iter_records
from checkpoint_replay.runner import call_tool

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURES = os.path.join(REPO, "fixtures")


def _run_steps(n, log_path):
    elog = EventLog(log_path)
    state = agent.initial_state()
    state["scratch"]["fixtures_dir"] = FIXTURES
    store = {}
    seq = 0
    for _ in range(n):
        tool, args = agent.next_action(state)
        assert tool != "DONE"
        elog.append({"type": "step", "seq": seq, "tool": tool,
                     "args": args, "rng_state": state["rng_state"]})
        seq += 1
        output = call_tool(tool, args, store)
        elog.append({"type": "result", "seq": seq, "tool": tool, "output": output})
        seq += 1
        state = agent.apply(state, tool, args, output)
    elog.append({"type": "checkpoint", "seq": seq, "snapshot": state})
    elog.close()
    return state, store


def test_checkpoint_restore_roundtrip(tmp_path):
    p = str(tmp_path / "run.jsonl")
    state, _store = _run_steps(8, p)

    recs = list(iter_records(p))
    ckpts = [r for r in recs if r["type"] == "checkpoint"]
    assert len(ckpts) == 1
    snap = ckpts[-1]["snapshot"]

    # A fresh agent restores purely from the snapshot JSON (simulates a
    # fresh process after a crash: nothing in memory survives).
    restored = {"pc": snap["pc"],
                "scratch": dict(snap["scratch"]),
                "rng_state": list(snap["rng_state"])}
    assert restored == state
    assert agent.next_action(restored) == agent.next_action(state)
    assert fsck(p) == []


def test_snapshot_survives_json_roundtrip_exactly(tmp_path):
    p = str(tmp_path / "run.jsonl")
    state, _store = _run_steps(8, p)
    import json
    raw = open(p).read().splitlines()
    snap = json.loads(raw[-1])["snapshot"]
    # dict ordering must not matter: sort_keys on write, exact compare here
    assert json.dumps(snap, sort_keys=True) == json.dumps(state, sort_keys=True)


def test_agent_plan_is_twenty_steps():
    state = agent.initial_state()
    state["scratch"]["fixtures_dir"] = FIXTURES
    n = 0
    while True:
        tool, args = agent.next_action(state)
        if tool == "DONE":
            break
        n += 1
        # dummy outputs just to advance pc; real semantics tested elsewhere
        if tool == "search":
            output = ["12", "7", "5", "9", "23", "4", "11", "6", "18", "3", "14", "10"]
        elif tool == "kv" and args.get("op") == "get":
            output = 42
        elif tool == "kv":
            output = "ok"
        else:
            output = 42
        state = agent.apply(state, tool, args, output)
    assert n == 20, "plan should be ~20 steps, got %d" % n
