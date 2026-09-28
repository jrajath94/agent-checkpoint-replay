"""Zero-dependency mock tools with real semantics.

Tools are pure functions of (args) plus an explicitly passed store for kv.
No module-level randomness, no wall-clock reads: nondeterminism enters only
through the caller's RNG, whose state the agent logs per step.
"""
import os
import re


def kv(store, op, key=None, value=None):
    """In-memory key-value get/put/delete. store is a plain dict owned by the runner."""
    if op == "get":
        return store.get(key)
    if op == "put":
        store[key] = value
        return "ok"
    if op == "delete":
        store.pop(key, None)
        return "ok"
    raise ValueError("unknown kv op: %r" % (op,))


def calc(op, a, b):
    """Deterministic arithmetic."""
    if op == "add":
        return a + b
    if op == "mul":
        return a * b
    if op == "sub":
        return a - b
    if op == "div":
        if b == 0:
            return {"error": "division by zero"}
        return a / b
    raise ValueError("unknown calc op: %r" % (op,))


def search(path, pattern):
    """Grep a file or directory for a regex. Returns matches in deterministic order.

    Files are visited in sorted order, lines in file order. If the pattern has
    a capture group, the group's text is returned, else the whole match.
    """
    rx = re.compile(pattern)
    if os.path.isdir(path):
        files = sorted(os.path.join(path, name) for name in os.listdir(path))
    else:
        files = [path]
    hits = []
    for fp in files:
        if not os.path.isfile(fp):
            continue
        with open(fp) as f:
            for line in f:
                m = rx.search(line)
                if m:
                    hits.append(m.group(1) if m.groups() else m.group(0))
    return hits
