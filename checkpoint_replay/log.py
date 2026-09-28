"""Append-only JSONL event log with per-record fsync.

Record types:
  step       {seq, tool, args, rng_state}  written BEFORE the tool runs (write-ahead)
  result     {seq, tool, output}            written AFTER the tool returns
  checkpoint {seq, snapshot}               snapshot is the JSON agent state
  done       {seq}                         terminal marker for a finished run

All record types share one seq namespace: seq starts at 0 and increases by
exactly 1 per line. That makes "no gaps" trivially checkable by fsck.
"""
import json
import os

RECORD_TYPES = ("step", "result", "checkpoint", "done")

_REQUIRED_FIELDS = {
    "step": ("tool", "args", "rng_state"),
    "result": ("tool", "output"),
    "checkpoint": ("snapshot",),
    "done": (),
}


class EventLog:
    """Single-writer append-only log. Every append is flushed and fsynced."""

    def __init__(self, path):
        self.path = path
        self._f = open(path, "a")

    def append(self, record):
        self._f.write(json.dumps(record, sort_keys=True) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def iter_records(path, drop_torn_tail=True):
    """Yield parsed records in file order.

    With drop_torn_tail, a final line that is not complete JSON (a write torn
    by a crash) is silently dropped: resume treats it as never written.
    """
    with open(path) as f:
        lines = f.read().splitlines()
    if drop_torn_tail and lines:
        try:
            json.loads(lines[-1])
        except ValueError:
            lines = lines[:-1]
    for line in lines:
        if line.strip():
            yield json.loads(line)


def iter_pairs(records):
    """Yield (step, result) tuples for completed pairs, in log order.

    A step with no following result (crash before the result landed) is
    skipped: its intent never completed, so it must not affect recovery.
    """
    pending = None
    for rec in records:
        if rec["type"] == "step":
            pending = rec
        elif rec["type"] == "result" and pending is not None:
            yield pending, rec
            pending = None


def fsck(path):
    """Verify the log. Returns a list of problem strings, empty when clean."""
    problems = []
    if not os.path.exists(path):
        return ["log file not found: %s" % path]
    with open(path) as f:
        lines = f.read().splitlines()
    expected_seq = 0
    last_step = None  # (seq, tool) of the most recent step awaiting its result
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            problems.append("line %d: blank line" % lineno)
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            if lineno == len(lines):
                problems.append("line %d: invalid JSON at end of file "
                                "(torn tail, possible truncation)" % lineno)
            else:
                problems.append("line %d: invalid JSON" % lineno)
            continue
        if not isinstance(rec, dict):
            problems.append("line %d: record is not a JSON object" % lineno)
            continue
        rtype = rec.get("type")
        seq = rec.get("seq")
        if rtype not in RECORD_TYPES:
            problems.append("line %d: unknown record type %r" % (lineno, rtype))
        if not isinstance(seq, int) or isinstance(seq, bool):
            problems.append("line %d: bad seq %r" % (lineno, seq))
            continue
        if seq != expected_seq:
            problems.append("line %d: expected seq %d, got %d"
                            % (lineno, expected_seq, seq))
        expected_seq = seq + 1
        for field in _REQUIRED_FIELDS.get(rtype, ()):
            if field not in rec:
                problems.append("line %d: %s record missing field %r"
                                % (lineno, rtype, field))
        if rtype == "step":
            last_step = (seq, rec.get("tool"))
        elif rtype == "result":
            if (last_step is None or last_step[0] != seq - 1
                    or last_step[1] != rec.get("tool")):
                problems.append("line %d: result without matching preceding step"
                                % lineno)
            last_step = None
    return problems
