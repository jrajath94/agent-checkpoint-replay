"""Explicit state-machine agent. No LLM, no hidden state.

State = {"pc": int, "scratch": dict, "rng_state": list}.
pc is a program counter over a fixed plan of NSTEPS tool calls:
  0.            search fixtures/ for numbers          (1 step)
  1..12.        calc mul each pair, kv put product    (12 steps)
  13.           kv get p0 to seed the total           (1 step)
  14..18.       calc add running total + next pair    (5 steps)
  19.           kv put the final answer               (1 step)

The pair order is shuffled with the agent RNG (seed 1234) so the run is
deterministic but not trivially ordered. rng_state is stored as a JSON-safe
list and restored with random.setstate.
"""
import random

SEED = 1234
NPAIRS = 6
NSTEPS = 3 * NPAIRS + 2  # 20


def initial_state():
    rng = random.Random(SEED)
    return {"pc": 0, "scratch": {}, "rng_state": _rng_to(rng)}


def _rng_to(rng):
    version, internal, gauss = rng.getstate()
    return [version, list(internal), gauss]


def _rng_from(state):
    version, internal, gauss = state["rng_state"]
    rng = random.Random()
    rng.setstate((version, tuple(internal), gauss))
    return rng


def next_action(state):
    """Return (tool, args) for the current pc, or ("DONE", {}) when finished."""
    pc = state["pc"]
    s = state["scratch"]
    if pc >= NSTEPS:
        return ("DONE", {})
    if pc == 0:
        return ("search", {"path": s["fixtures_dir"],
                           "pattern": r"value:\s*(\d+)"})
    if 1 <= pc <= 2 * NPAIRS:
        i = (pc - 1) // 2
        if pc % 2 == 1:
            a, b = s["order"][2 * i], s["order"][2 * i + 1]
            return ("calc", {"op": "mul", "a": a, "b": b})
        return ("kv", {"op": "put", "key": "p%d" % i, "value": s["p%d" % i]})
    if pc == 2 * NPAIRS + 1:
        return ("kv", {"op": "get", "key": "p0"})
    if 2 * NPAIRS + 2 <= pc <= 3 * NPAIRS:
        i = pc - (2 * NPAIRS + 1)
        return ("calc", {"op": "add", "a": s["total"], "b": s["p%d" % i]})
    return ("kv", {"op": "put", "key": "answer", "value": s["total"]})


def apply(state, tool, args, output):
    """Advance state with a tool output. Returns a NEW state dict."""
    new = {"pc": state["pc"] + 1,
           "scratch": dict(state["scratch"]),
           "rng_state": list(state["rng_state"])}
    s = new["scratch"]
    pc = state["pc"]
    if pc == 0:
        # search results in, shuffle the pair order with the agent RNG
        nums = [int(x) for x in output]
        rng = _rng_from(new)
        order = nums[:]
        rng.shuffle(order)
        new["rng_state"] = _rng_to(rng)
        s["numbers"] = nums
        s["order"] = order
    elif 1 <= pc <= 2 * NPAIRS and pc % 2 == 1:
        s["p%d" % ((pc - 1) // 2)] = output
    elif pc == 2 * NPAIRS + 1:
        s["total"] = output
    elif 2 * NPAIRS + 2 <= pc <= 3 * NPAIRS:
        s["total"] = output
    # kv put steps need no state change: the runner owns the store
    return new
