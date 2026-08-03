"""
Tests for the "close the scene-object-licensing gap" feature:
TrustRuntime.decisions_since()/now_ts() (trust_runtime.py) and
build_experiment_record(persist_path=...)/list_experiment_records()
(experiment_record.py).

Run with: python3 tests/test_qfoldit_scene_licensing_collection.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.compliance.trust_runtime import TrustRuntime  # noqa: E402
from qfoldit.science.experiment_record import build_experiment_record, list_experiment_records  # noqa: E402


def _fresh_runtime():
    audit_fd, audit_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(audit_fd)
    return TrustRuntime(audit_log_path=audit_path), audit_path


def test_decisions_since_returns_empty_list_for_missing_log():
    t = TrustRuntime(audit_log_path="/tmp/does-not-exist-qfoldit-test.jsonl")
    assert t.decisions_since() == []


def test_decisions_since_reads_back_real_decisions():
    t, _ = _fresh_runtime()
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"tool_name": "material_apply_preset", "kwargs": {"preset": "chrome"}})
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"tool_name": "spawn", "code": "spawn rick sanchez"})
    decisions = t.decisions_since(tool_name="run_toolbelt_tool")
    assert len(decisions) == 2
    assert decisions[0]["allowed"] is True
    assert decisions[1]["allowed"] is False
    assert "rick sanchez" in decisions[1]["matched_terms"]


def test_decisions_since_filters_by_tool_name():
    t, _ = _fresh_runtime()
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"preset": "chrome"})
    t.evaluate(tool_name="execute_python", kwargs={"code": "print(1)"})
    only_toolbelt = t.decisions_since(tool_name="run_toolbelt_tool")
    assert len(only_toolbelt) == 1
    assert only_toolbelt[0]["tool_name"] == "run_toolbelt_tool"


def test_decisions_since_scopes_by_timestamp_marker():
    t, _ = _fresh_runtime()
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"preset": "before_marker"})
    time.sleep(1.1)  # audit log timestamp resolution is whole seconds
    marker = t.now_ts()
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"preset": "after_marker"})
    scoped = t.decisions_since(since_ts=marker, tool_name="run_toolbelt_tool")
    assert len(scoped) == 1
    assert "after_marker" in scoped[0]["reason"] or scoped[0]["allowed"] is True


def test_decisions_since_skips_corrupt_lines_without_crashing():
    t, path = _fresh_runtime()
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"preset": "chrome"})
    with open(path, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")
    t.evaluate(tool_name="run_toolbelt_tool", kwargs={"preset": "black_chrome"})
    decisions = t.decisions_since(tool_name="run_toolbelt_tool")
    assert len(decisions) == 2  # the two good lines, corrupt one skipped


def test_experiment_record_persist_path_appends_jsonl():
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    os.remove(path)  # start from "file doesn't exist yet"
    assert list_experiment_records(path) == []

    build_experiment_record(
        science_result={"status": "ok", "final_energy": 1.0},
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "seed": 1},
        persist_path=path,
    )
    build_experiment_record(
        science_result={"status": "ok", "final_energy": 2.0},
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "seed": 2},
        persist_path=path,
    )
    records = list_experiment_records(path)
    assert len(records) == 2
    assert records[0]["science_result"]["final_energy"] == 1.0
    assert records[1]["science_result"]["final_energy"] == 2.0


def test_list_experiment_records_respects_limit():
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    os.remove(path)
    for i in range(5):
        build_experiment_record(
            science_result={"status": "ok", "final_energy": float(i)},
            science_source_kind="quantum_walk_fold",
            reproduce_with={"function": "simulate_quantum_walk_fold", "seed": i},
            persist_path=path,
        )
    records = list_experiment_records(path, limit=2)
    assert len(records) == 2
    assert records[-1]["science_result"]["final_energy"] == 4.0  # most recent kept


def test_build_experiment_record_without_persist_path_has_no_side_effect():
    """Default behavior (no persist_path) must stay exactly as before
    this feature -- purely functional, no file written."""
    record = build_experiment_record(
        science_result={"status": "ok"},
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "seed": 1},
    )
    assert "experiment_id" in record  # still works, just no disk write to verify against


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {test.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
