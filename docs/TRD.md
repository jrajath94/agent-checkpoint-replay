# TRD: agent-checkpoint-replay

## First-principles design

An agent run is a sequence of actions. Each action is: decide what to do (from state), call a tool, observe the result, update state. The two things that make this hard to resume are tool side effects (you must not call a tool twice) and nondeterminism (an RNG draw or a timestamp changes the plan).

The fix is an old one, write-ahead logging. Before the run mutates anything, it appends a record of intent to a durable log. Every completed tool call is also recorded with its result. A checkpoint is a snapshot of agent state plus the log offset it corresponds to. Recovery is then mechanical:

- **Crash**: replay nothing, just load the latest checkpoint and continue appending from its offset. Tool calls that finished are in the log with their results, so they are never re-executed.
- **Replay**: walk the log from offset zero and return recorded tool outputs instead of calling tools. The agent logic is deterministic given the same inputs, so it must emit the same action sequence. Assert it.

## Components

### 1. EventLog (`checkpoint_replay/log.py`)
Append-only JSONL file. Record types:

- `step`: an action the agent decided to take: `{seq, tool, args, rng_state}`. Appended before the tool executes (write-ahead).
- `result`: the tool output: `{seq, tool, output}`. Appended after the tool returns.
- `checkpoint`: `{seq, snapshot}` where snapshot is a JSON blob of agent state.

Every append is followed by `file.flush()` + `os.fsync()`. Durability is the whole point; without fsync a "durable" log is a hope.

`fsck(path)` re-reads the log and verifies: valid JSON on every line, `seq` strictly increasing by 1 per record type order, no `result` without a matching preceding `step`, no gaps. Returns a list of problems. Truncates are detected because the last line must be complete JSON.

### 2. Tools (`checkpoint_replay/tools.py`)
Zero-dependency mocks with real semantics:

- `kv`: in-memory key-value store (`get`, `put`, `delete`). The task writes intermediate results here.
- `calc`: arithmetic evaluator (`add`, `mul`, ...). Deterministic by construction.
- `search`: greps a fixture directory for a pattern. Reads only, but slow enough to matter and proves tools are recorded not re-run.

Tools are pure functions of `(args)` plus a caller-supplied RNG for any randomness. No hidden state, no wall-clock reads: nondeterminism enters only through the RNG, whose state is logged per step. That is the entire determinism story.

### 3. Agent (`checkpoint_replay/agent.py`)
A small explicit state machine, not an LLM. State = `{pc, scratch, rng_state}` where `pc` is a program counter over a fixed plan and `scratch` holds intermediate values. `next_action(state)` returns the next tool call or `DONE`. `apply(state, action, tool_output)` advances state. Because the plan is explicit, replay determinism is checkable: same logged inputs must yield the same action sequence.

The demo plan: search fixtures for numbers, multiply pairs with calc, accumulate into kv, ~20 steps.

### 4. Runner (`checkpoint_replay/runner.py`)
`run(log_path, resume=False, checkpoint_every=N)`:

1. Open the log. If `resume`, `fsck` it, load the latest `checkpoint` record, restore `state` and continue from `seq + 1`.
2. Loop: append `step`, call tool, append `result`, update state, every N steps append `checkpoint` (snapshot = state JSON).
3. On normal finish, append a final checkpoint + `done` marker.

Resume never re-executes a tool whose `result` is already in the log: the checkpoint snapshot already includes the applied result, so the loop continues with the next `step`.

### 5. Replay (`checkpoint_replay/replay.py`)
`replay(log_path)` walks `step`/`result` records from zero, feeds recorded outputs to `agent.apply`, collects the action sequence, and returns it. The test asserts it equals the action sequence extracted from the original log.

## Concurrency and crash model
Single writer. The crash test kills the writer with SIGKILL between steps. Because every record is fsynced, the log is always a prefix of complete records. fsck on resume tolerates a torn last line by treating it as absent (a partially written last line is dropped before resume).

## What we are deliberately not building
No distributed consensus, no multi-writer, no log compaction, no encryption, no remote storage. Those are real problems and they would each double the code. This repo shows the core pattern honestly.

## Test plan (red-green)
1. Log append + fsck: write records, assert fsck clean; corrupt a line, assert fsck reports it. RED first.
2. Checkpoint/restore round-trip: run N steps, checkpoint, load into fresh agent, assert state equality. RED first.
3. Replay determinism: run to completion, replay, assert identical action sequences. RED first.
4. Crash recovery: real SIGKILL mid-run, fresh process resumes, final state equals uninterrupted run. RED first.

All four green before delivery. No mocks of the thing under test.
