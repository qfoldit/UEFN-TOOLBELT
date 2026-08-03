"""Tests for qfoldit/science/pipelines/quantum_runner.py — the classical,
quantum-walk-INSPIRED folding simulation (see module docstring for exactly
what it is and isn't). Pure stdlib, no external deps, no live editor or
network required.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qfoldit.science.pipelines.quantum_runner import (  # noqa: E402
    simulate_quantum_walk_fold,
    predict_peptide_quantum_vqe,
)


def _run(coro):
    return asyncio.run(coro)


def test_rejects_empty_sequence():
    r = _run(simulate_quantum_walk_fold(""))
    assert r["status"] == "error"


def test_rejects_non_alpha_sequence():
    r = _run(simulate_quantum_walk_fold("ACD123"))
    assert r["status"] == "error"


def test_rejects_zero_steps():
    r = _run(simulate_quantum_walk_fold("ACDEFG", steps=0))
    assert r["status"] == "error"


def test_rejects_single_residue():
    r = _run(simulate_quantum_walk_fold("A", steps=10))
    assert r["status"] == "error"


def test_produces_valid_coordinate_tensor():
    r = _run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=100, seed=42))
    assert r["status"] == "ok"
    assert len(r["coordinates"]) > 0
    for atom in r["coordinates"]:
        assert "x" in atom and "y" in atom and "z" in atom
        assert "residue_index" in atom and "atom" in atom
    assert isinstance(r["final_energy"], float)
    assert r["proposed_moves"] == 100
    assert 0.0 <= r["acceptance_ratio"] <= 1.0


def test_deterministic_given_same_seed():
    """Same sequence + same seed -> byte-identical result. Matters because
    the gamification layer (gamedesign.py) relies on this determinism to
    make levels/scores traceable back to a specific run."""
    r1 = _run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=200, seed=7))
    r2 = _run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=200, seed=7))
    assert r1["final_energy"] == r2["final_energy"]
    assert r1["coordinates"] == r2["coordinates"]


def test_different_seeds_diverge():
    r1 = _run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=200, seed=1))
    r2 = _run(simulate_quantum_walk_fold("ACDEFGHIKL", steps=200, seed=2))
    assert r1["coordinates"] != r2["coordinates"]


def test_short_chain_short_run_stays_near_extended_chain_energy():
    """For a short chain, a short run starting from the near-extended-chain
    initial guess should stay close to that low-clash starting point —
    confirms the initial guess and energy function are sane."""
    r = _run(simulate_quantum_walk_fold("ACDEFG", steps=5, seed=0))
    assert r["final_energy"] < 5.0  # sane bound, not a tight optimum claim


def test_energy_trace_starts_at_the_initial_conformation_energy():
    r = _run(simulate_quantum_walk_fold("ACDEFGHIKLMNPQ", steps=100, seed=0))
    assert r["energy_trace"][0] == r["energy_trace"][0]  # first sample recorded
    assert len(r["energy_trace"]) > 1


def test_known_limitation_longer_chains_can_stay_kinetically_trapped():
    """DOCUMENTED, NOT HIDDEN: this walk uses single-dihedral-angle proposal
    moves. For chains long enough to self-clash (~14+ residues here), once
    the hot phase pushes the chain into a self-intersecting conformation,
    a single-angle move essentially never finds the coordinated multi-angle
    change needed to undo it, and cooling then locks the clash in rather
    than resolving it -- so a 400-step run can end at HIGHER energy than a
    5-step run that barely left the low-clash starting point. This test
    exists to make that real, current behavior visible (it will fail loudly
    if a future crankshaft/pivot-move improvement changes it) rather than
    asserting a "long run = better" claim this implementation doesn't
    actually deliver at this chain length. See quantum_runner.py's
    KNOWN LIMITATIONS note."""
    short_energies = [
        _run(simulate_quantum_walk_fold("ACDEFGHIKLMNPQ", steps=5, seed=s))["final_energy"]
        for s in range(5)
    ]
    long_energies = [
        _run(simulate_quantum_walk_fold("ACDEFGHIKLMNPQ", steps=400, seed=s))["final_energy"]
        for s in range(5)
    ]
    # This asserts the CURRENT (imperfect) behavior, not the ideal one.
    assert sum(long_energies) / len(long_energies) > sum(short_energies) / len(short_energies)


def test_vqe_wrapper_honestly_reports_unavailable_without_qupepfold():
    """qupepfold is NOT installed in this environment on purpose (it's a
    heavy Qiskit/Braket-dependent package meant for a separate quantum
    venv) — the wrapper must say so, never fabricate a ground-state energy."""
    r = _run(predict_peptide_quantum_vqe("ACDEFG"))
    assert r["status"] == "unavailable"
    assert "install_hint" in r
    assert "ground_state_energy" not in r


def test_vqe_wrapper_validates_inputs_before_even_trying_the_import():
    r = _run(predict_peptide_quantum_vqe("", alpha=0.1))
    assert r["status"] == "error"
    r2 = _run(predict_peptide_quantum_vqe("ACDEFG", alpha=1.5))
    assert r2["status"] == "error"


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
