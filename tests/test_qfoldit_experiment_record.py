"""
Tests for qfoldit/science/experiment_record.py.
Run with: python3 tests/test_qfoldit_experiment_record.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.science.experiment_record import build_experiment_record  # noqa: E402
from qfoldit.science.pipelines.quantum_runner import simulate_quantum_walk_fold  # noqa: E402


def _minimal_walk_result():
    return {
        "status": "ok", "sequence": "ACDE", "final_energy": 1.23,
        "accepted_moves": 40, "proposed_moves": 100, "acceptance_ratio": 0.4,
        "energy_trace": [5.0, 3.0, 1.23], "continuous_space": True,
    }


def test_classical_source_never_labeled_as_quantum():
    record = build_experiment_record(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
    )
    text = record["methods_section"]
    assert "NOT a quantum computation" in text
    assert "classical" in text.lower()


def test_real_vqe_source_carries_verification_caveat():
    record = build_experiment_record(
        science_result={"status": "ok", "ground_state_energy": -3.1, "backend": "sim", "alpha": 0.2, "shots": 100},
        science_source_kind="quantum_vqe",
        reproduce_with={"function": "predict_peptide_quantum_vqe", "sequence": "ACDE", "alpha": 0.2, "shots": 100},
    )
    text = record["methods_section"]
    assert "NOT independently verified" in text
    assert "CVaR" in text


def test_unrecognized_kind_never_fabricates_a_citation():
    record = build_experiment_record(
        science_result={"foo": "bar"},
        science_source_kind="some_future_pipeline",
        reproduce_with={"function": "unknown"},
    )
    assert "UNRECOGNIZED SOURCE KIND" in record["methods_section"]
    assert record["publication_checklist"]["science_kind_recognized"] is False
    assert record["publication_checklist"]["publication_ready"] is False


def test_publication_ready_when_everything_clears():
    record = build_experiment_record(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
        licensing_decisions=[{"tool_name": "run_toolbelt_tool", "allowed": True, "matched_terms": [], "reason": "no watchlist match"}],
    )
    assert record["publication_checklist"]["publication_ready"] is True
    assert "blocked_licensing_details" not in record["publication_checklist"]


def test_blocked_licensing_flags_not_publication_ready():
    record = build_experiment_record(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
        licensing_decisions=[
            {"tool_name": "run_toolbelt_tool", "allowed": False, "matched_terms": ["lego"], "reason": "blocked: no manifest entry"},
        ],
    )
    checks = record["publication_checklist"]
    assert checks["publication_ready"] is False
    assert checks["licensing_all_cleared"] is False
    assert len(checks["blocked_licensing_details"]) == 1
    assert checks["blocked_licensing_details"][0]["tool_name"] == "run_toolbelt_tool"


def test_missing_reproduce_with_fails_that_specific_check():
    record = build_experiment_record(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={},
    )
    assert record["publication_checklist"]["deterministic_reproduction_recorded"] is False
    assert record["publication_checklist"]["publication_ready"] is False


def test_experiment_id_deterministic_for_same_inputs():
    kwargs = dict(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
    )
    r1 = build_experiment_record(**kwargs)
    r2 = build_experiment_record(**kwargs)
    assert r1["experiment_id"] == r2["experiment_id"]
    # created_utc is a real timestamp and is allowed to differ between calls;
    # experiment_id must NOT depend on it.
    assert isinstance(r1["created_utc"], str)


def test_experiment_id_changes_when_science_result_changes():
    r1 = build_experiment_record(
        science_result=_minimal_walk_result(),
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
    )
    other = _minimal_walk_result()
    other["final_energy"] = 999.0
    r2 = build_experiment_record(
        science_result=other,
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDE", "steps": 100, "seed": 1},
    )
    assert r1["experiment_id"] != r2["experiment_id"]


def test_end_to_end_real_quantum_runner_result_feeds_experiment_record():
    """Same discipline as test_qfoldit_gamedesign.py's own end-to-end
    test -- no mocking of the science pipeline."""
    result = asyncio.run(simulate_quantum_walk_fold(sequence="ACDEFGH", steps=60, seed=7))
    assert result["status"] == "ok"
    record = build_experiment_record(
        science_result=result,
        science_source_kind="quantum_walk_fold",
        reproduce_with={"function": "simulate_quantum_walk_fold", "sequence": "ACDEFGH", "steps": 60, "seed": 7},
        licensing_decisions=[{"tool_name": "qfoldit_quantum_walk_fold", "allowed": True, "matched_terms": [], "reason": "n/a"}],
    )
    assert record["publication_checklist"]["publication_ready"] is True
    assert "NOT a quantum computation" in record["methods_section"]


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
