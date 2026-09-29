# agent-checkpoint-replay

A minimal, honest checkpoint / restore / replay demo for long-running
tool-calling agent runs. Python 3.10+, standard library only, no network,
no LLM. Under 500 lines of library code, readable in one sitting.

## The problem

Long-running agent runs die: OOM-kill, VM restart, deploy rolling the pod.
When that happens the work is gone, or worse, the agent re-runs from scratch
and calls tools twice. This repo demonstrates the three primitives that fix
it, against mock tools (a key-value store, a calculator, a file search):

1. **Checkpoint** - durably record full agent state plus the log offset, so a
   fresh process picks up exactly where the old one died.
2. **Restore** - load the snapshot and continue from the recorded offset,
   without re-executing completed tool calls.
3. **Replay** - re-execute a finished run from its trace, returning recorded
   tool outputs instead of calling tools, and assert the action sequence is
   identical. This is how you prove determinism and debug a run after the fact.

The core trick is old: **write-ahead logging**. Every intended tool call is
appended to a JSONL log (with `fsync`) *before* the tool runs; every result
is appended after. A checkpoint is a snapshot of agent state. Recovery is
mechanical: truncate any torn tail, load the latest checkpoint, apply forward
any logged results past the checkpoint, and continue. A tool whose result is
already logged is never re-executed.

## Try it

```bash
python3 -m pytest tests/ -q          # all green, stdlib only (+ pytest)
bash scripts/demo_crash.sh           # kill -9 mid-run, resume, verify
python3 scripts/demo_replay.py       # replay the trace, assert identical
python3 scripts/print_trace.py       # the sample trace quoted below
```

## Verified results (locally run, self-reported)

- Real kill -9 crash demo: process SIGKILLed mid-run, resumed from the
  checkpoint, final state byte-identical to an uninterrupted run (20/20
  tool steps, no tool call re-executed).
- Deterministic replay: re-executing a finished run from its trace returns
  recorded tool outputs and asserts an identical action sequence.
- Tests: 14/14 green (`python3 -m pytest tests/ -q`), standard library only.

## Layout

- `checkpoint_replay/log.py` - append-only JSONL log, fsync per record, `fsck`
- `checkpoint_replay/tools.py` - mock tools: `kv`, `calc`, `search`
- `checkpoint_replay/agent.py` - explicit state-machine agent, no LLM
- `checkpoint_replay/runner.py` - run / resume loop, CLI
- `checkpoint_replay/replay.py` - deterministic replay from the trace
- `docs/` - PRD, TRD, and the build log (EXECUTION.md)

## Sample trace

Real output of `scripts/print_trace.py` (45 records, 20 tool steps):

```
    sample trace (45 records, 20 tool steps):
    # INTENT (write-ahead): what the agent decided, BEFORE the tool runs
    seq=0  step       search {"path": "fixtures", "pattern": "value:\\s*(\\d+)"}
    # OBSERVATION: the tool output, AFTER the tool returns
    seq=1  result     search -> ["12", "7", "5", "9", "23", "4", "11", "6", "18", "3", "14", "10"]
    seq=2  step       calc   {"a": 5, "b": 9, "op": "mul"}
    seq=3  result     calc   -> 45
    seq=4  step       kv     {"key": "p0", "op": "put", "value": 45}
    seq=5  result     kv     -> "ok"
    seq=6  step       calc   {"a": 18, "b": 23, "op": "mul"}
    seq=7  result     calc   -> 414
    seq=8  step       kv     {"key": "p1", "op": "put", "value": 414}
    seq=9  result     kv     -> "ok"
    # CHECKPOINT: full agent state snapshot, safe to resume from here
    seq=10 checkpoint pc=5 scratch_keys=['fixtures_dir', 'numbers', 'order', 'p0', 'p1']
    seq=11 step       calc   {"a": 10, "b": 11, "op": "mul"}
    seq=12 result     calc   -> 110
    seq=13 step       kv     {"key": "p2", "op": "put", "value": 110}
    seq=14 result     kv     -> "ok"
    seq=15 step       calc   {"a": 4, "b": 3, "op": "mul"}
    seq=16 result     calc   -> 12
    seq=17 step       kv     {"key": "p3", "op": "put", "value": 12}
    seq=18 result     kv     -> "ok"
    seq=19 step       calc   {"a": 14, "b": 12, "op": "mul"}
    seq=20 result     calc   -> 168
    seq=21 checkpoint pc=10 scratch_keys=['fixtures_dir', 'numbers', 'order', 'p0', 'p1', 'p2', 'p3', 'p4']
    seq=22 step       kv     {"key": "p4", "op": "put", "value": 168}
    seq=23 result     kv     -> "ok"
    seq=24 step       calc   {"a": 7, "b": 6, "op": "mul"}
    seq=25 result     calc   -> 42
    seq=26 step       kv     {"key": "p5", "op": "put", "value": 42}
    seq=27 result     kv     -> "ok"
    seq=28 step       kv     {"key": "p0", "op": "get"}
    seq=29 result     kv     -> 45
    seq=30 step       calc   {"a": 45, "b": 414, "op": "add"}
    seq=31 result     calc   -> 459
    seq=32 checkpoint pc=15 scratch_keys=['fixtures_dir', 'numbers', 'order', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'total']
    seq=33 step       calc   {"a": 459, "b": 110, "op": "add"}
    seq=34 result     calc   -> 569
    seq=35 step       calc   {"a": 569, "b": 12, "op": "add"}
    seq=36 result     calc   -> 581
    seq=37 step       calc   {"a": 581, "b": 168, "op": "add"}
    seq=38 result     calc   -> 749
    seq=39 step       calc   {"a": 749, "b": 42, "op": "add"}
    seq=40 result     calc   -> 791
    seq=41 step       kv     {"key": "answer", "op": "put", "value": 791}
    seq=42 result     kv     -> "ok"
    seq=43 checkpoint pc=20 scratch_keys=['fixtures_dir', 'numbers', 'order', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'total']
    # DONE: terminal marker, the run finished
    seq=44 done
```
