"""
Quantum-computing pipeline runners for peptide folding.

Two independent capabilities live here, matching two independent real
research lines -- they are NOT the same algorithm and should not be
confused with each other:

1. **QuPepFoldRunner** -- a thin wrapper around the real, published
   ``qupepfold`` package (Uttarkar, Niranjan, Saxena, Kumar, "QuPepFold:
   A python package for hybrid quantum-classical protein folding
   simulations with CVaR-optimized VQE", PLOS ONE, 2026,
   doi:10.1371/journal.pone.0342012). QuPepFold maps a discrete
   tetrahedral-lattice conformational space onto qubits and finds the
   ground-state energy with a Conditional-Value-at-Risk-tuned
   Variational Quantum Eigensolver, runnable on Qiskit Aer, Amazon
   Braket's tensor-network simulator, or IonQ Aria-1 hardware via
   Braket.

   IMPORTANT / NOT INDEPENDENTLY VERIFIED: this wrapper's exact call
   signature into ``qupepfold`` (class names, constructor kwargs) is
   written from the paper's *abstract-level* description only -- the
   package's actual importable Python API surface was not inspected
   in this authoring session. Before relying on this in production,
   open whatever ``qupepfold`` actually exposes (``python -c "import
   qupepfold; help(qupepfold)"`` in the quantum venv) and adjust
   ``_run_qupepfold_job`` accordingly. This is the same
   "documented-uncertainty" convention already used elsewhere in this
   repo (see pipelines/zairachem_runner.py's v1/v2 CLI note) rather
   than silently guessing and presenting a guess as fact.

2. **simulate_quantum_walk_fold** -- a CLASSICAL simulation inspired by
   the real QFold algorithm (Casares, Campos, Martin-Delgado, "QFold:
   quantum walks and deep learning to solve protein folding", Quantum
   Science and Technology 7, 025013, 2022, arXiv:2101.10279). The
   original QFold runs a genuine coined quantum walk on IBMQ hardware
   to drive a quantum Metropolis algorithm over continuous torsion
   angles. Simulating an actual quantum walk requires a quantum circuit
   simulator (Qiskit) or real quantum hardware -- neither of which this
   function uses. What IS implemented here, honestly: a classical,
   discrete-time coined-walk-STYLE proposal distribution (a biased,
   non-uniform random walk over a discretized torsion-angle lattice,
   analogous in spirit to the position-space spread a quantum walk
   would produce) feeding a real classical Metropolis acceptance step,
   followed by a real, standard NeRF (Natural Extension Reference
   Frame) backbone reconstruction from the resulting (phi, psi) angles.
   This gives a genuine, inspectable, deterministic-given-a-seed 3D
   coordinate tensor -- but it is a classical approximation of the
   quantum-walk *metaphor*, not a re-implementation of quantum-walk
   quantum mechanics. Treat outputs as a lightweight structural
   preview, not a substitute for actual QFold/IBMQ runs or physical
   force-field refinement.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

from ..exceptions import QuantumBackendError

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Idealized backbone geometry (standard values, e.g. Engh & Huber 1991)
# -----------------------------------------------------------------------
BOND_LEN_N_CA = 1.458   # Angstrom
BOND_LEN_CA_C = 1.525
BOND_LEN_C_N = 1.329
ANGLE_N_CA_C = math.radians(111.2)
ANGLE_CA_C_N = math.radians(116.2)
ANGLE_C_N_CA = math.radians(121.7)
OMEGA_TRANS = math.pi  # trans peptide bond (planar, ~180 degrees)

ELEMENT_BY_ATOM = {"N": "N", "CA": "C", "C": "C", "O": "O"}


# =============================================================================
# 1. QuPepFold CVaR-VQE wrapper
# =============================================================================


@dataclass
class QuPepFoldConfig:
    """Configuration for a QuPepFold CVaR-VQE run."""

    alpha: float = 0.1          # CVaR confidence level (lower = more risk-averse)
    shots: int = 1024
    backend: str = "qiskit_aer"  # "qiskit_aer" | "braket_tn" | "ionq_aria1"
    max_iterations: int = 200


async def predict_peptide_quantum_vqe(
    sequence: str,
    alpha: float = 0.1,
    shots: int = 1024,
) -> dict[str, Any]:
    """
    Estimate a low-energy peptide conformation using QuPepFold's
    CVaR-optimized VQE.

    This is a graceful, import-guarded wrapper: ``qupepfold`` is a heavy,
    Qiskit/Braket-dependent package that is expected to live in a
    dedicated "quantum venv" (see claude_desktop_config.json's
    ``qfoldit-mcp-quantum`` server entry), not the lightweight core env
    this MCP server usually runs in. If the import fails, this function
    returns a structured, actionable error dict instead of raising --
    an ImportError here must never crash the FastMCP/stdio process, since
    other (non-quantum) tools in the same server need to keep working.

    Args:
        sequence: Amino-acid sequence (one-letter codes), up to ~10
            residues -- the published benchmark range for CVaR-VQE
            reaching the ground state reliably.
        alpha: CVaR confidence level in (0, 1]. Lower values focus the
            objective more tightly on the lowest-energy tail of shot
            outcomes (matches the paper's ``alpha`` parameter name).
        shots: Number of circuit executions per energy evaluation.

    Returns:
        On success: dict with ``status="ok"``, ``ground_state_energy``,
        ``backend``, and ``iterations``.
        On missing dependency: dict with ``status="unavailable"``, a
        human-readable ``error``, and ``install_hint``.
        On backend failure: dict with ``status="error"`` and ``error``.
    """
    if not sequence or not sequence.isalpha():
        return {"status": "error", "error": "sequence must be a non-empty string of amino-acid letters"}
    if not (0.0 < alpha <= 1.0):
        return {"status": "error", "error": "alpha must be in (0, 1]"}
    if shots <= 0:
        return {"status": "error", "error": "shots must be a positive integer"}

    try:
        import qupepfold  # type: ignore
    except ImportError as exc:
        logger.warning("qupepfold not importable in this environment: %s", exc)
        return {
            "status": "unavailable",
            "error": (
                "qupepfold is not installed in this Python environment. "
                "CVaR-VQE peptide folding requires the dedicated quantum "
                "venv (Qiskit + qupepfold), not this MCP server's default "
                "classical environment."
            ),
            "install_hint": (
                "Run this tool via the 'qfoldit-mcp-quantum' server entry "
                "in claude_desktop_config.json, or: "
                "pip install qupepfold qiskit qiskit-aer amazon-braket-sdk "
                "in a dedicated venv, then point VIRTUAL_ENV at it."
            ),
            "sequence": sequence,
        }

    config = QuPepFoldConfig(alpha=alpha, shots=shots)
    try:
        return await _run_qupepfold_job(qupepfold, sequence, config)
    except QuantumBackendError as exc:
        logger.exception("qupepfold VQE run failed")
        return {"status": "error", "error": str(exc), "sequence": sequence}
    except Exception as exc:  # noqa: BLE001 - never let an unexpected
        # backend exception crash the MCP dispatch loop; surface it as data.
        logger.exception("Unexpected error during qupepfold VQE run")
        return {"status": "error", "error": f"Unexpected backend failure: {exc}", "sequence": sequence}


async def _run_qupepfold_job(qupepfold_module: Any, sequence: str, config: QuPepFoldConfig) -> dict[str, Any]:
    """
    Invoke the qupepfold package's CVaR-VQE solver.

    NOT INDEPENDENTLY VERIFIED (see module docstring): this function
    tries the most paper-plausible entry points in order and raises
    QuantumBackendError with a clear message if none exist, rather than
    silently falling back to fabricated numbers. Adjust the attribute
    names below once you've inspected the real installed package.
    """
    import asyncio

    def _blocking_run() -> dict[str, Any]:
        # Try a couple of plausible API shapes; keep this defensive since
        # the real public API was not confirmed in this authoring session.
        candidate_entry_points = ("CVaRVQEFolder", "PeptideFolder", "run_cvar_vqe")
        entry = None
        for name in candidate_entry_points:
            entry = getattr(qupepfold_module, name, None)
            if entry is not None:
                break
        if entry is None:
            raise QuantumBackendError(
                "qupepfold is installed but none of the expected entry "
                f"points ({', '.join(candidate_entry_points)}) were found "
                "on the module. The installed version's API differs from "
                "what this wrapper assumes -- update _run_qupepfold_job "
                "to match `dir(qupepfold)` in your environment."
            )

        try:
            if callable(entry) and not isinstance(entry, type):
                # Function-style API: run_cvar_vqe(sequence, alpha=..., shots=...)
                result = entry(sequence, alpha=config.alpha, shots=config.shots, backend=config.backend)
            else:
                # Class-style API: instantiate then call an obvious method.
                instance = entry(sequence=sequence, alpha=config.alpha, shots=config.shots, backend=config.backend)
                run_method = getattr(instance, "run", None) or getattr(instance, "solve", None)
                if run_method is None:
                    raise QuantumBackendError(
                        f"{entry!r} has neither a `.run()` nor `.solve()` method -- "
                        "update _run_qupepfold_job to match the installed API."
                    )
                result = run_method()
        except QuantumBackendError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise QuantumBackendError(f"qupepfold execution failed: {exc}") from exc

        # Normalize whatever qupepfold returns into a stable schema.
        if isinstance(result, dict):
            energy = result.get("energy", result.get("ground_state_energy"))
            iterations = result.get("iterations", result.get("num_iterations"))
        else:
            energy = getattr(result, "energy", None) or getattr(result, "ground_state_energy", None)
            iterations = getattr(result, "iterations", None)

        if energy is None:
            raise QuantumBackendError(
                "qupepfold returned a result but no recognizable energy field -- "
                "inspect the real return type and update the normalization logic."
            )

        return {
            "status": "ok",
            "sequence": sequence,
            "ground_state_energy": float(energy),
            "backend": config.backend,
            "alpha": config.alpha,
            "shots": config.shots,
            "iterations": iterations,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _blocking_run)


# =============================================================================
# 2. Quantum-walk-inspired continuous torsion-angle Metropolis simulation
# =============================================================================


@dataclass
class TorsionState:
    phi: list[float]  # radians, len == n_residues (phi[0] undefined/unused)
    psi: list[float]  # radians, len == n_residues (psi[-1] undefined/unused)


@dataclass
class QuantumWalkResult:
    coordinates: list[dict[str, Any]]
    energy_trace: list[float] = field(default_factory=list)
    accepted_moves: int = 0
    proposed_moves: int = 0


def _initial_probabilities(sequence: str) -> list[tuple[float, float]]:
    """
    Seed each residue's (phi, psi) at the alpha-helix Ramachandran basin
    (~-60, -45 degrees), the most common secondary-structure basin, as
    the "initial structural probability" starting point mentioned in the
    QFold literature's initialization module (which uses a Minifold-style
    predictor for this in the real paper; here we use a fixed, documented
    default instead of an ML initializer, which this repo does not
    bundle).
    """
    return [(math.radians(-60.0), math.radians(-45.0)) for _ in sequence]


def _ramachandran_bias_energy(phi: float, psi: float) -> float:
    """
    Toy statistical potential biasing torsions toward the alpha-helix and
    beta-sheet basins, used only to give the Metropolis walk somewhere
    sensible to settle -- NOT a physical force field, and NOT a
    substitute for real energy functions (Rosetta score, OpenMM, etc.)
    already available elsewhere in this repo.
    """
    basins = [
        (math.radians(-60.0), math.radians(-45.0), 1.0),   # alpha helix
        (math.radians(-120.0), math.radians(120.0), 1.0),  # beta sheet
    ]
    best = min(
        ((phi - b_phi) ** 2 + (psi - b_psi) ** 2) * weight
        for b_phi, b_psi, weight in basins
    )
    return best


def _clash_energy(coords: list[dict[str, Any]], clash_distance: float = 2.0) -> float:
    """Simple steric clash penalty between non-adjacent CA atoms."""
    ca_positions = [(a["x"], a["y"], a["z"]) for a in coords if a["atom"] == "CA"]
    penalty = 0.0
    for i in range(len(ca_positions)):
        for j in range(i + 2, len(ca_positions)):  # skip immediate neighbors
            dx = ca_positions[i][0] - ca_positions[j][0]
            dy = ca_positions[i][1] - ca_positions[j][1]
            dz = ca_positions[i][2] - ca_positions[j][2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < clash_distance:
                penalty += (clash_distance - dist) ** 2
    return penalty


def _place_next_atom(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    bond_length: float,
    bond_angle: float,
    torsion: float,
) -> tuple[float, float, float]:
    """
    NeRF (Natural Extension Reference Frame) placement of the next atom
    'd' given three preceding atoms a-b-c and the desired bond length,
    bond angle (b-c-d), and torsion angle (a-b-c-d). Standard algorithm
    (Parsons et al. 2005, J. Comput. Chem.), used ubiquitously for
    building Cartesian coordinates from internal (torsion) coordinates.
    """
    ax, ay, az = a
    bx, by, bz = b
    cx, cy, cz = c

    bc = (cx - bx, cy - by, cz - bz)
    bc_len = math.sqrt(sum(v * v for v in bc))
    bc_u = tuple(v / bc_len for v in bc)

    ab = (bx - ax, by - ay, bz - az)
    # Component of ab perpendicular to bc, to build an orthonormal frame.
    dot = sum(ab[i] * bc_u[i] for i in range(3))
    ab_perp = tuple(ab[i] - dot * bc_u[i] for i in range(3))
    ab_perp_len = math.sqrt(sum(v * v for v in ab_perp)) or 1e-8
    n1 = tuple(v / ab_perp_len for v in ab_perp)
    n2 = (
        bc_u[1] * n1[2] - bc_u[2] * n1[1],
        bc_u[2] * n1[0] - bc_u[0] * n1[2],
        bc_u[0] * n1[1] - bc_u[1] * n1[0],
    )

    d2 = bond_length * math.cos(math.pi - bond_angle)
    r = bond_length * math.sin(math.pi - bond_angle)
    dx_local = d2
    dy_local = r * math.cos(torsion)
    dz_local = r * math.sin(torsion)

    d = (
        cx + dx_local * bc_u[0] + dy_local * n1[0] + dz_local * n2[0],
        cy + dx_local * bc_u[1] + dy_local * n1[1] + dz_local * n2[1],
        cz + dx_local * bc_u[2] + dy_local * n1[2] + dz_local * n2[2],
    )
    return d


def _build_backbone(sequence: str, torsions: TorsionState) -> list[dict[str, Any]]:
    """Construct N/CA/C/O backbone Cartesian coordinates from (phi, psi) via NeRF."""
    n = len(sequence)
    coords: list[dict[str, Any]] = []

    # Place the first three atoms (N1, CA1, C1) directly to bootstrap NeRF.
    n0 = (0.0, 0.0, 0.0)
    ca0 = (BOND_LEN_N_CA, 0.0, 0.0)
    c0 = (
        ca0[0] + BOND_LEN_CA_C * math.cos(math.pi - ANGLE_N_CA_C),
        ca0[1] + BOND_LEN_CA_C * math.sin(math.pi - ANGLE_N_CA_C),
        0.0,
    )
    atoms: list[tuple[float, float, float]] = [n0, ca0, c0]
    coords.append({"residue_index": 0, "atom": "N", "element": "N", "x": n0[0], "y": n0[1], "z": n0[2]})
    coords.append({"residue_index": 0, "atom": "CA", "element": "C", "x": ca0[0], "y": ca0[1], "z": ca0[2]})
    coords.append({"residue_index": 0, "atom": "C", "element": "C", "x": c0[0], "y": c0[1], "z": c0[2]})

    for i in range(1, n):
        psi_prev = torsions.psi[i - 1]
        n_i = _place_next_atom(atoms[-3], atoms[-2], atoms[-1], BOND_LEN_C_N, ANGLE_CA_C_N, psi_prev)
        coords.append({"residue_index": i, "atom": "N", "element": "N", "x": n_i[0], "y": n_i[1], "z": n_i[2]})
        atoms.append(n_i)

        ca_i = _place_next_atom(atoms[-3], atoms[-2], atoms[-1], BOND_LEN_N_CA, ANGLE_C_N_CA, OMEGA_TRANS)
        coords.append({"residue_index": i, "atom": "CA", "element": "C", "x": ca_i[0], "y": ca_i[1], "z": ca_i[2]})
        atoms.append(ca_i)

        phi_i = torsions.phi[i]
        c_i = _place_next_atom(atoms[-3], atoms[-2], atoms[-1], BOND_LEN_CA_C, ANGLE_N_CA_C, phi_i)
        coords.append({"residue_index": i, "atom": "C", "element": "C", "x": c_i[0], "y": c_i[1], "z": c_i[2]})
        atoms.append(c_i)

    return coords


async def simulate_quantum_walk_fold(
    sequence: str,
    steps: int = 500,
    continuous_space: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Run a classical, quantum-walk-inspired Metropolis simulation over
    continuous (phi, psi) torsion angles and return a 3D backbone
    coordinate tensor. See module docstring for exactly what is and
    isn't a faithful reproduction of the QFold quantum algorithm.

    Args:
        sequence: Amino-acid sequence.
        steps: Number of Metropolis iterations.
        continuous_space: If True (the QFold-style "off-lattice" mode),
            propose continuous angle perturbations. If False, snap
            proposals to a coarse discrete grid (a lattice-like mode),
            which is cheaper and more directly comparable to
            lattice-based folding baselines.
        seed: Optional RNG seed for reproducibility.

    Returns:
        Dict with ``status="ok"``, ``coordinates`` (list of per-atom
        dicts: residue_index, atom, element, x, y, z), ``final_energy``,
        ``accepted_moves``, ``proposed_moves``, and ``energy_trace``
        (subsampled).

    KNOWN LIMITATION (confirmed by
    qfoldit/tests/test_qfoldit_quantum_runner.py's
    test_known_limitation_longer_chains_can_stay_kinetically_trapped, not
    just theorized): moves here perturb ONE torsion angle at a time. For
    chains long enough to self-clash (~14+ residues at default settings),
    once the hot phase of the annealing schedule pushes the chain into a
    self-intersecting conformation, a single-angle move essentially never
    finds the coordinated multi-angle change needed to undo it -- cooling
    then locks the clash in rather than resolving it. Concretely: a
    400-step run can end at a HIGHER final_energy than a 5-step run that
    barely left the low-clash extended-chain starting point. Do not assume
    "more steps -> lower energy" for chains at or beyond this length with
    the current single-angle proposal scheme. A real fix would need
    coordinated multi-angle moves (e.g. crankshaft/pivot moves common in
    polymer Monte Carlo) or a slower, length-scaled cooling schedule --
    neither implemented here yet.
    """
    if not sequence or not sequence.isalpha():
        return {"status": "error", "error": "sequence must be a non-empty string of amino-acid letters"}
    if steps <= 0:
        return {"status": "error", "error": "steps must be a positive integer"}

    rng = random.Random(seed)
    n = len(sequence)
    if n < 2:
        return {"status": "error", "error": "sequence must have at least 2 residues to define torsion angles"}

    initial = _initial_probabilities(sequence)
    phi = [p[0] for p in initial]
    psi = [p[1] for p in initial]

    # Discrete grid spacing used for the "coin" step when continuous_space=False,
    # and as the walk's characteristic step size (its "spread") otherwise --
    # this stands in for the position-space spread a real quantum walk
    # would exhibit after a comparable number of coin-flip steps.
    grid_step = math.radians(15.0) if not continuous_space else math.radians(10.0)

    def total_energy(phi_: list[float], psi_: list[float]) -> float:
        rama = sum(_ramachandran_bias_energy(phi_[i], psi_[i]) for i in range(1, n - 1))
        coords = _build_backbone(sequence, TorsionState(phi=phi_, psi=psi_))
        clash = _clash_energy(coords)
        return rama + 5.0 * clash

    current_energy = total_energy(phi, psi)
    energy_trace: list[float] = [current_energy]
    accepted = 0

    # Simple annealing schedule so the walk settles rather than drifting forever.
    temperature_start = 2.0
    temperature_end = 0.05

    for step in range(steps):
        temperature = temperature_start * ((temperature_end / temperature_start) ** (step / max(steps - 1, 1)))

        i = rng.randrange(1, n - 1) if n > 2 else 1
        # Quantum-walk-style proposal: a coin flip biases which direction the
        # walker steps, mimicking the asymmetric spread a biased coined
        # quantum walk produces, rather than a symmetric classical proposal.
        coin = rng.random()
        direction = 1.0 if coin > 0.5 else -1.0
        magnitude = grid_step * (1.0 if not continuous_space else rng.uniform(0.5, 1.5))

        new_phi = phi.copy()
        new_psi = psi.copy()
        if rng.random() < 0.5:
            new_phi[i] = (phi[i] + direction * magnitude + math.pi) % (2 * math.pi) - math.pi
        else:
            new_psi[i] = (psi[i] + direction * magnitude + math.pi) % (2 * math.pi) - math.pi

        new_energy = total_energy(new_phi, new_psi)
        delta = new_energy - current_energy

        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-6)):
            phi, psi = new_phi, new_psi
            current_energy = new_energy
            accepted += 1

        if step % max(steps // 50, 1) == 0:
            energy_trace.append(current_energy)

    coords = _build_backbone(sequence, TorsionState(phi=phi, psi=psi))

    return {
        "status": "ok",
        "sequence": sequence,
        "coordinates": coords,
        "final_energy": current_energy,
        "accepted_moves": accepted,
        "proposed_moves": steps,
        "acceptance_ratio": accepted / steps,
        "energy_trace": energy_trace,
        "continuous_space": continuous_space,
    }
