"""Deterministic replay: walk the log from seq 0, feed RECORDED tool outputs
to agent.apply, never call a tool. Returns the action sequence, which must
equal the sequence extracted from the original log's step records."""
from . import agent
from . import log as logmod


def replay(log_path):
    state = agent.initial_state()
    actions = []
    pending = None
    for rec in logmod.iter_records(log_path):
        if rec["type"] == "step":
            # fixtures_dir travels inside the recorded search args, so replay
            # needs no filesystem assumptions of its own.
            if (state["scratch"].get("fixtures_dir") is None
                    and rec["tool"] == "search"):
                state["scratch"]["fixtures_dir"] = rec["args"]["path"]
            tool, args = agent.next_action(state)
            actions.append((tool, args))
            pending = rec
        elif rec["type"] == "result" and pending is not None:
            state = agent.apply(state, pending["tool"], pending["args"],
                                rec["output"])
            pending = None
    return actions


def action_sequence_from_log(log_path):
    """The original action sequence, straight from the log's step records."""
    return [(r["tool"], r["args"]) for r in logmod.iter_records(log_path)
            if r["type"] == "step"]
