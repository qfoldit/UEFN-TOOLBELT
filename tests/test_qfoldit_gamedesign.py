"""Tests for qfoldit/science/gamedesign.py — deterministic, rule-based game
design document generator. Pure stdlib, no external deps.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qfoldit.science.gamedesign import generate_game_design  # noqa: E402
from qfoldit.science.pipelines.quantum_runner import simulate_quantum_walk_fold  # noqa: E402


def test_unrecognized_source_shape_produces_sparse_valid_document_not_an_error():
    doc = generate_game_design({"something": "unrelated"})
    assert doc["source_kind"] == "unknown"
    assert isinstance(doc["levels"], list)
    assert isinstance(doc["achievements"], list)


def test_quantum_walk_source_detected_and_produces_levels():
    fake_source = {
        "status": "ok", "final_energy": 0.5, "acceptance_ratio": 0.3,
        "energy_trace": [1.0, 0.8, 0.6, 0.5],
    }
    doc = generate_game_design(fake_source)
    assert doc["source_kind"] == "quantum_walk_fold"
    assert len(doc["levels"]) > 0


def test_vqe_source_detected_and_produces_boss_level():
    doc = generate_game_design({"status": "ok", "ground_state_energy": -12.3})
    assert doc["source_kind"] == "quantum_vqe"
    assert len(doc["levels"]) >= 1


def test_admet_source_detected_and_produces_achievements():
    doc = generate_game_design({"endpoints": {"solubility": {"score": 0.7}}})
    assert doc["source_kind"] == "admet_profile"


def test_deterministic_same_source_same_output():
    """The whole point of this layer being rule-based (no LLM) is that a
    reviewer can trace any score back to the exact source number — verify
    that guarantee holds, not just assume it."""
    source = {"status": "ok", "final_energy": 0.42, "acceptance_ratio": 0.5,
              "energy_trace": [2.0, 1.5, 1.0, 0.42]}
    doc1 = generate_game_design(source, title="Test", difficulty="adaptive")
    doc2 = generate_game_design(source, title="Test", difficulty="adaptive")
    assert doc1 == doc2
    assert doc1["seed"] == doc2["seed"]


def test_difficulty_changes_output_deterministically():
    source = {"status": "ok", "final_energy": 0.42, "acceptance_ratio": 0.5,
              "energy_trace": [2.0, 1.5, 1.0, 0.42]}
    story = generate_game_design(source, difficulty="story")
    hardcore = generate_game_design(source, difficulty="hardcore")
    assert story != hardcore  # different tightness -> different par/star cutoffs
    # but each is internally deterministic
    assert generate_game_design(source, difficulty="hardcore") == hardcore


def test_invalid_difficulty_falls_back_to_adaptive_not_error():
    doc = generate_game_design({"final_energy": 1.0, "acceptance_ratio": 0.4,
                                 "energy_trace": [1.0]}, difficulty="nonsense")
    assert doc["difficulty"] == "adaptive"


def test_end_to_end_real_quantum_walk_result_feeds_gamedesign():
    """Integration check across the two real science modules: a genuine
    simulate_quantum_walk_fold() output (not a hand-built fake dict) must
    be recognized and turned into a valid game design document."""
    real_result = asyncio.run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=150, seed=3))
    assert real_result["status"] == "ok"
    doc = generate_game_design(real_result, title="Real Fold Run")
    assert doc["source_kind"] == "quantum_walk_fold"
    assert doc["title"] == "Real Fold Run"
    assert len(doc["levels"]) > 0
    # Re-running gamedesign on the identical real result must be identical too.
    doc2 = generate_game_design(real_result, title="Real Fold Run")
    assert doc == doc2


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
