"""Replay: full run -> replay from log -> identical action sequences.
Negative test: tamper one recorded output -> sequences diverge."""
import json

from checkpoint_replay import runner
from checkpoint_replay.replay import replay, action_sequence_from_log


def _full_run(tmp_path, name="run.jsonl"):
    p = str(tmp_path / name)
    runner.run(p, checkpoint_every=5)
    return p


def test_replay_matches_original_sequence(tmp_path, capsys):
    p = _full_run(tmp_path)
    with capsys.disabled():
        pass
    original = action_sequence_from_log(p)
    assert len(original) == 20
    assert replay(p) == original


def test_replay_never_calls_tools(tmp_path, monkeypatch):
    """Replay must not touch the tools: point search at a missing dir and
    replay must still succeed using only recorded outputs."""
    p = _full_run(tmp_path)
    import checkpoint_replay.tools as tools

    def boom(*a, **k):
        raise AssertionError("replay called a tool")

    monkeypatch.setattr(tools, "kv", boom)
    monkeypatch.setattr(tools, "calc", boom)
    monkeypatch.setattr(tools, "search", boom)
    assert replay(p) == action_sequence_from_log(p)


def test_tampered_output_diverges(tmp_path):
    """Flip one recorded tool output; the replayed sequence must change.
    This proves the equality assertion is not vacuous."""
    p = _full_run(tmp_path)
    original = action_sequence_from_log(p)
    recs = [json.loads(line) for line in open(p).read().splitlines()]
    for r in recs:
        if r["type"] == "result" and r["tool"] == "calc":
            assert isinstance(r["output"], (int, float))
            r["output"] = r["output"] + 1
            break
    else:
        raise AssertionError("no calc result found to tamper")
    bad = str(tmp_path / "tampered.jsonl")
    with open(bad, "w") as f:
        for r in recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    assert replay(bad) != original
