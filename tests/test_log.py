"""Log tests: append records -> fsck clean; corruptions -> fsck flags each."""
from checkpoint_replay import log as logmod
from checkpoint_replay.log import EventLog, fsck, iter_records


def _write_lines(path, lines):
    with open(path, "w") as f:
        f.writelines(lines)


def test_append_then_fsck_clean(tmp_path):
    p = str(tmp_path / "run.jsonl")
    elog = EventLog(p)
    elog.append({"type": "step", "seq": 0, "tool": "calc",
                 "args": {"op": "add", "a": 1, "b": 2}, "rng_state": [1, 2]})
    elog.append({"type": "result", "seq": 1, "tool": "calc", "output": 3})
    elog.append({"type": "checkpoint", "seq": 2, "snapshot": {"pc": 1}})
    elog.close()
    assert fsck(p) == []
    recs = list(iter_records(p))
    assert [r["type"] for r in recs] == ["step", "result", "checkpoint"]
    assert recs[0]["args"] == {"op": "add", "a": 1, "b": 2}


def test_fsck_flags_bad_json(tmp_path):
    p = str(tmp_path / "run.jsonl")
    _write_lines(p, ['{"type": "step", "seq": 0, "tool": "x", "args": {}, "rng_state": []}\n',
                     'NOT JSON AT ALL\n'])
    problems = fsck(p)
    assert problems, "fsck should flag the bad line"
    assert any("line 2" in pr for pr in problems)


def test_fsck_flags_skipped_seq(tmp_path):
    p = str(tmp_path / "run.jsonl")
    _write_lines(p, ['{"type": "step", "seq": 0, "tool": "x", "args": {}, "rng_state": []}\n',
                     '{"type": "result", "seq": 1, "tool": "x", "output": 1}\n',
                     '{"type": "step", "seq": 3, "tool": "x", "args": {}, "rng_state": []}\n'])
    problems = fsck(p)
    assert any("seq" in pr and "3" in pr for pr in problems), problems


def test_fsck_flags_result_without_step(tmp_path):
    p = str(tmp_path / "run.jsonl")
    _write_lines(p, ['{"type": "result", "seq": 0, "tool": "calc", "output": 3}\n'])
    problems = fsck(p)
    assert any("without matching" in pr for pr in problems), problems


def test_fsck_reports_torn_tail_and_iter_drops_it(tmp_path):
    p = str(tmp_path / "run.jsonl")
    with open(p, "w") as f:
        f.write('{"type": "step", "seq": 0, "tool": "x", "args": {}, "rng_state": []}\n')
        f.write('{"type": "result", "seq": 1, "tool": "x", "output":')
    problems = fsck(p)
    assert any("torn" in pr for pr in problems), problems
    recs = list(iter_records(p, drop_torn_tail=True))
    assert len(recs) == 1
    assert recs[0]["type"] == "step"


def test_every_append_is_fsynced(tmp_path, monkeypatch):
    p = str(tmp_path / "run.jsonl")
    calls = []
    real_fsync = logmod.os.fsync

    def spy(fd):
        calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(logmod.os, "fsync", spy)
    elog = EventLog(p)
    elog.append({"type": "step", "seq": 0, "tool": "x", "args": {}, "rng_state": []})
    elog.append({"type": "result", "seq": 1, "tool": "x", "output": 1})
    elog.close()
    assert len(calls) == 2, "every append must fsync, durability is the point"
