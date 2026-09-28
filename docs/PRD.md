# PRD: agent-checkpoint-replay

## Problem
Long-running tool-calling agent runs die. The process gets OOM-killed, the VM restarts, a deploy rolls over the pod. When that happens the work done so far is gone: the agent re-runs from scratch, re-calls tools it already called (writes side effects twice), or waits for a human to paste it back to where it was. This is the standard failure story for any agent that runs longer than a few minutes.

## What this is
A minimal, runnable demo of the three primitives that fix this:

1. **Checkpoint**: durably record full agent state + log offset, so a fresh process can pick up exactly where the old one died.
2. **Restore**: load that snapshot and continue from the recorded offset, without re-executing completed tool calls.
3. **Replay**: re-execute a finished run from its trace, returning recorded tool outputs instead of calling tools, and assert the action sequence is identical. This is how you prove determinism and debug a run after the fact.

## Non-goals
Not a framework. Not a production runtime. No network, no LLM calls, no dependencies beyond the Python standard library. The whole thing should be readable in one sitting, roughly 300 lines of library code.

## Demo scenario
A worker agent runs a multi-step task (about 15 to 30 tool calls) against mock tools: a key-value store, a calculator, and a file search over a fixture directory. Mid-run, the test harness kill -9s the worker process. A fresh process restores the latest checkpoint and finishes the run. Then the trace is replayed deterministically and the two action sequences are asserted identical.

## Success criteria
- `pytest` is green on a fresh machine with no setup beyond Python 3.10+.
- `scripts/demo_crash.sh` kills the worker with SIGKILL mid-run, resumes in a fresh process, and the run completes with correct final state.
- `scripts/demo_replay.py` prints two identical action sequences and exits 0.
- The README shows a real sample trace inline.
- No test asserts a fake: the crash test uses a real SIGKILL on a real subprocess.

## Users
- Rajath, for demonstrating post-training/infra-adjacent craft in interviews: "Built checkpoint/restore/replay for long-running agent runs with deterministic replay from traces."
- Any engineer who wants to see the pattern in an afternoon.
