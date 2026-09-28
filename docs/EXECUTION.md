# EXECUTION.md: agent-checkpoint-replay

How this was built, in order. Kept as a record so the process is auditable.

## Phase 1: Docs (done first, in one pass)
PRD.md, TRD.md, this file. Written before any code so the design was agreed with itself. Kept short on purpose: a design doc nobody reads is padding.

## Phase 2: Red-green TDD
One failing test at a time, then the smallest code that makes it pass, then refactor. Order:

1. `test_log.py`: append three records, fsck clean. Then corrupt the file (bad JSON, skipped seq, result without step) and assert fsck flags each. Failing first: `fsck` did not exist.
2. `test_checkpoint.py`: run agent 8 steps, write checkpoint, build a fresh agent, restore, assert `state == state` and next action identical. Failing first: no snapshot format.
3. `test_replay.py`: full run to DONE, replay from log, assert action sequences identical. Failing first: no replay function. Also a negative test: flip one recorded output and assert the action sequence diverges (proves the assertion is not vacuous).
4. `test_crash.py`: spawn the runner as a subprocess, wait until the log shows step >= 10, SIGKILL it, then run the runner with `resume=True` in a fresh process. Assert final kv state equals the uninterrupted reference run and every tool was called at most once (count invocations via the log: one `step` per call). Failing first: no runner CLI.

Rule: never write a line of library code without a failing test that needs it. Tests use `tmp_path`, never the repo directory.

## Phase 3: Demo scripts
- `scripts/demo_crash.sh`: runs the crash scenario end to end and prints progress. This is the headline demo; it must work on a cold machine.
- `scripts/demo_replay.py`: runs a full pass, replays, prints both action sequences side by side and the assertion result.
- Both scripts exit non-zero on failure so CI-style checks work.

## Phase 4: Sample trace for the README
`scripts/print_trace.py`: runs a short pass and prints a compact, commented sample trace. The README quotes this verbatim. Regenerate it if the record format changes.

## Phase 5: QA pass
- Full `pytest` on a clean checkout (delete `__pycache__`, fresh venv not needed, stdlib only).
- `demo_crash.sh` run three times in a row; all must pass (flakiness in the crash test is a bug, not noise).
- `demo_replay.py` run; sequences must match.
- Line count check: library under ~350 lines. If it grew, cut.
- `wm_clean.py` Layer A over README.md and docs/.
- Kill-switch check: no network calls anywhere (`grep -r "urllib\|requests\|socket" checkpoint_replay/` must be empty).

## Phase 6: Publish
- `gh_publish.py check`, `create-repo agent-checkpoint-replay` (private), `push-dir`.
- Verify the repo page shows README, docs/, tests, fixtures.
- Real commit timestamps. No backdating, ever.

## Risks and how they were handled
- Torn writes on SIGKILL: fsync per record + fsck drops a torn tail. Tested by killing mid-run repeatedly.
- Replay divergence from dict ordering: snapshot uses `json.dumps(sort_keys=True)`; tests cover it.
- RNG nondeterminism: `random.Random` seeded from the log's initial seed, state saved per step. No `random.random()` module-level calls anywhere.
