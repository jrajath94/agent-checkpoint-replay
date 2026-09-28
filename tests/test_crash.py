"""Crash recovery: real SIGKILL on a real subprocess mid-run, then resume in
a fresh process. Final kv state must equal the uninterrupted reference run,
and the final log's action sequence must be identical (no tool re-executed,
none skipped)."""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from checkpoint_replay import log as logmod
from checkpoint_replay import runner
from checkpoint_replay.replay import action_sequence_from_log

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _step_seqs(path):
    seqs = []
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        return seqs
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # torn tail line: unreadable by design
        if rec.get("type") == "step":
            seqs.append(rec["seq"])
    return seqs


def test_crash_resume_matches_reference(tmp_path):
    # Uninterrupted reference run, in-process.
    ref_log = str(tmp_path / "ref.jsonl")
    ref = runner.run(ref_log, checkpoint_every=5)
    ref_actions = action_sequence_from_log(ref_log)
    assert len(ref_actions) == 20
    assert ref["kv"]["answer"] is not None

    # Victim run: real subprocess, --slow so we can kill it mid-run.
    victim_log = str(tmp_path / "victim.jsonl")
    proc = subprocess.Popen(
        [sys.executable, "-m", "checkpoint_replay.runner",
         victim_log, "--slow", "--checkpoint-every", "5"],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if any(s >= 10 for s in _step_seqs(victim_log)):
                break
            if proc.poll() is not None:
                pytest.fail("victim exited before reaching step seq 10")
            time.sleep(0.05)
        else:
            pytest.fail("victim never reached step seq 10 in 60s")
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    # Resume in a FRESH process.
    resumed = subprocess.run(
        [sys.executable, "-m", "checkpoint_replay.runner",
         victim_log, "--resume"],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    assert resumed.returncode == 0, "resume failed:\n" + resumed.stderr

    # The recovered log must be fully valid...
    assert logmod.fsck(victim_log) == []
    # ...with exactly the reference action sequence: every tool ran once,
    # none re-executed after the crash, none skipped.
    final_actions = action_sequence_from_log(victim_log)
    assert final_actions == ref_actions
    # ...and the final kv state must equal the uninterrupted run.
    final_kv = runner.store_from_log(victim_log)
    assert final_kv == ref["kv"]
    assert final_kv["answer"] == ref["kv"]["answer"]


def test_resume_on_completed_log_is_noop(tmp_path):
    p = str(tmp_path / "run.jsonl")
    runner.run(p, checkpoint_every=5)
    before = open(p).read()
    out = subprocess.run(
        [sys.executable, "-m", "checkpoint_replay.runner", p, "--resume"],
        cwd=REPO, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert open(p).read() == before, "resuming a finished run must not append"
