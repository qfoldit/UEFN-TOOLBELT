"""
gamedesign.py -- the qFoldIT "gamification layer": an automatic game
designer that turns this server's own scientific outputs (folding
trajectories, VQE energies, ADMET profiles) into a structured game
design document -- levels, a scoring/par system, achievements, and a
light narrative wrapper.

SCOPE AND FRAMING (read this before wiring into anything else):

This is qFoldIT's own product layer, not a claim about any of the
upstream science. It is a deterministic, rule-based generator -- no
LLM call, no external API, nothing non-reproducible -- so the same
scientific result always produces the same game design document. That
determinism is a deliberate choice: it keeps this auditable (a
reviewer can trace any level/score/achievement back to the exact
number in the source result that produced it) and keeps it usable
offline in the same dependency-light way as the rest of this package.

It does NOT itself render a game, generate Unity/Unreal assets, or
talk to a game engine. It produces a portable, engine-agnostic JSON
document (see GameDesignDocument below) that a downstream consumer --
a Unity/Unreal importer, another LLM agent, a web frontend -- can turn
into an actual playable experience. Pairing the "levels" output here
with `uag_exporter.export_to_openusd()`'s 3D scene for the same
molecule gives a level backdrop + level structure that both derive
from the same underlying run.

Supported source result shapes (auto-detected by which keys are
present -- see `_detect_source_kind`):
  - `simulate_quantum_walk_fold()` / `predict_structure_quantum_walk`
    output (has `energy_trace`, `final_energy`, `acceptance_ratio`)
    -> becomes the level progression (one level per trajectory
    checkpoint) plus a "Stability Score".
  - `predict_peptide_quantum_vqe()` output (has `ground_state_energy`)
    -> becomes a "Quantum Boss Level" with a par score derived from
    the reported energy.
  - `predict_admet_profile()` output (has `endpoints`) -> becomes a
    set of "Safety Trial" achievements, one per configured endpoint
    that returned a score.
Any other/unrecognized dict still produces a minimal, valid (if
sparse) document rather than raising, so this never blocks a caller
that passes an odd shape.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Difficulty = Literal["story", "adaptive", "hardcore"]

# Multiplier applied to par scores per difficulty -- higher difficulty
# demands a tighter (lower) energy/score margin to earn full stars.
_DIFFICULTY_PAR_TIGHTNESS = {
    "story": 0.6,
    "adaptive": 1.0,
    "hardcore": 1.6,
}


@dataclass
class Achievement:
    id: str
    title: str
    description: str
    unlocked: bool
    source_metric: str  # human-readable pointer back to the exact input value


@dataclass
class GameLevel:
    level_number: int
    title: str
    description: str
    par_score: float
    checkpoint_energy: float
    stars: int  # 1-3, computed from how far below par_score the run finished


@dataclass
class GameDesignDocument:
    title: str
    tagline: str
    difficulty: Difficulty
    seed: str  # deterministic id derived from the source result, for reproducibility
    levels: list[GameLevel]
    achievements: list[Achievement]
    narrative_intro: str
    total_score: float
    source_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_source_kind(source: dict[str, Any]) -> str:
    if "energy_trace" in source and "final_energy" in source:
        return "quantum_walk_fold"
    if "ground_state_energy" in source:
        return "quantum_vqe"
    if "endpoints" in source:
        return "admet_profile"
    return "unknown"


def _seed_from_source(source: dict[str, Any]) -> str:
    """Short, deterministic id so the same input always yields the same document."""
    raw = repr(sorted(source.items(), key=lambda kv: kv[0]))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _stars_from_margin(actual: float, par: float, tightness: float) -> int:
    """3 stars if actual is well below (better than) par*tightness, down to 1 if barely under par."""
    if par == 0:
        return 2
    ratio = actual / par if par > 0 else (par / actual if actual else 1.0)
    threshold = tightness
    if ratio <= threshold * 0.7:
        return 3
    if ratio <= threshold:
        return 2
    return 1


def _levels_from_quantum_walk(source: dict[str, Any], tightness: float) -> list[GameLevel]:
    trace: list[float] = source.get("energy_trace", []) or [source.get("final_energy", 0.0)]
    sequence = source.get("sequence", "")
    n_checkpoints = max(1, min(len(trace), 8))  # cap at 8 levels for playability
    step = max(1, len(trace) // n_checkpoints)
    checkpoints = trace[::step][:n_checkpoints]
    if checkpoints[-1] != trace[-1]:
        checkpoints[-1] = trace[-1]

    levels: list[GameLevel] = []
    prev_energy = checkpoints[0]
    for i, energy in enumerate(checkpoints, start=1):
        par = abs(prev_energy) * tightness if prev_energy else 1.0
        stars = _stars_from_margin(abs(energy), max(par, 1e-6), tightness)
        levels.append(
            GameLevel(
                level_number=i,
                title=f"Fold Stage {i}" + (f" -- {sequence[: min(len(sequence), 6)]}..." if sequence else ""),
                description=(
                    f"Guide the backbone through torsion-angle Metropolis moves until "
                    f"the conformational energy drops to {energy:.3f} or lower."
                ),
                par_score=round(par, 4),
                checkpoint_energy=round(energy, 4),
                stars=stars,
            )
        )
        prev_energy = energy
    return levels


def _boss_level_from_vqe(source: dict[str, Any], tightness: float) -> GameLevel:
    energy = float(source.get("ground_state_energy", 0.0))
    par = abs(energy) * tightness if energy else 1.0
    stars = _stars_from_margin(abs(energy), max(par, 1e-6), tightness)
    return GameLevel(
        level_number=1,
        title="Quantum Boss: Ground State",
        description=(
            f"Beat the CVaR-VQE ground-state energy of {energy:.4f} using "
            f"{source.get('shots', '?')} shots at alpha={source.get('alpha', '?')}."
        ),
        par_score=round(par, 4),
        checkpoint_energy=round(energy, 4),
        stars=stars,
    )


def _achievements_from_quantum_walk(source: dict[str, Any]) -> list[Achievement]:
    achievements: list[Achievement] = []
    acceptance_ratio = source.get("acceptance_ratio")
    if acceptance_ratio is not None:
        achievements.append(
            Achievement(
                id="speed_folder",
                title="Speed Folder",
                description="Accepted more than 40% of proposed Metropolis moves.",
                unlocked=acceptance_ratio > 0.4,
                source_metric=f"acceptance_ratio={acceptance_ratio:.3f}",
            )
        )
    final_energy = source.get("final_energy")
    if final_energy is not None:
        achievements.append(
            Achievement(
                id="genesis_fold",
                title="Genesis Fold",
                description="Completed a full folding trajectory to a final energy checkpoint.",
                unlocked=True,
                source_metric=f"final_energy={final_energy:.4f}",
            )
        )
    return achievements


def _achievements_from_vqe(source: dict[str, Any]) -> list[Achievement]:
    return [
        Achievement(
            id="quantum_pioneer",
            title="Quantum Pioneer",
            description="Ran a peptide through CVaR-optimized VQE on a quantum backend.",
            unlocked=source.get("status") == "ok",
            source_metric=f"backend={source.get('backend', 'unknown')}",
        )
    ]


def _achievements_from_admet(source: dict[str, Any]) -> list[Achievement]:
    achievements: list[Achievement] = []
    endpoints: dict[str, Any] = source.get("endpoints", {})
    for name, result in endpoints.items():
        status = result.get("status")
        score = result.get("score")
        achievements.append(
            Achievement(
                id=f"safety_trial_{name}",
                title=f"Safety Trial: {name.replace('_', ' ').title()}",
                description=f"Cleared the {name.replace('_', ' ')} ZairaChem screening endpoint.",
                unlocked=(status == "ok" and score is not None),
                source_metric=f"status={status}, score={score}",
            )
        )
    return achievements


def generate_game_design(
    source: dict[str, Any],
    title: str | None = None,
    difficulty: Difficulty = "adaptive",
) -> dict[str, Any]:
    """
    Generate a portable game design document from a scientific pipeline
    result (see module docstring for which shapes are recognized).

    Args:
        source: The raw result dict from one of this server's own
            tools (`predict_structure_quantum_walk`,
            `predict_peptide_quantum_vqe`, or `predict_admet_profile`).
        title: Optional display title; defaults to a generic one
            derived from the detected source kind.
        difficulty: "story" (generous par scores), "adaptive"
            (default), or "hardcore" (tight par scores).

    Returns:
        A JSON-serializable dict (see GameDesignDocument.to_dict()).
        Never raises for an unrecognized `source` shape -- returns a
        minimal, valid, sparse document instead so this never blocks
        a caller passing something unexpected.
    """
    if difficulty not in _DIFFICULTY_PAR_TIGHTNESS:
        difficulty = "adaptive"
    tightness = _DIFFICULTY_PAR_TIGHTNESS[difficulty]

    kind = _detect_source_kind(source)
    seed = _seed_from_source(source)

    levels: list[GameLevel]
    achievements: list[Achievement]
    tagline: str

    if kind == "quantum_walk_fold":
        levels = _levels_from_quantum_walk(source, tightness)
        achievements = _achievements_from_quantum_walk(source)
        tagline = "Fold your way from chaos to a stable conformation, one Metropolis move at a time."
    elif kind == "quantum_vqe":
        levels = [_boss_level_from_vqe(source, tightness)]
        achievements = _achievements_from_vqe(source)
        tagline = "Beat the quantum computer to the ground state."
    elif kind == "admet_profile":
        levels = []
        achievements = _achievements_from_admet(source)
        tagline = "Clear every safety trial before your candidate molecule ships."
    else:
        levels = []
        achievements = []
        tagline = "An unrecognized result was supplied -- no levels or achievements could be derived from it."

    total_score = sum(lvl.stars for lvl in levels) + sum(1 for a in achievements if a.unlocked)

    doc = GameDesignDocument(
        title=title or f"qFoldIT: {kind.replace('_', ' ').title()}",
        tagline=tagline,
        difficulty=difficulty,
        seed=seed,
        levels=levels,
        achievements=achievements,
        narrative_intro=(
            f"{tagline} This run is uniquely identified as seed #{seed} -- "
            "replaying the same scientific result always regenerates the same levels."
        ),
        total_score=total_score,
        source_kind=kind,
    )
    return doc.to_dict()


@dataclass
class ChallengeObjective:
    metric: str  # dotted-path to the real metric in the source result, e.g. "final_energy"
    comparison: Literal["below", "above", "equals"]
    threshold: float
    description: str


@dataclass
class TeamRole:
    role_name: str
    responsibility: str


@dataclass
class MultiplayerChallenge:
    title: str
    seed: str
    round_duration_seconds: int
    team_count: int
    objective: ChallengeObjective | None
    team_roles: list[TeamRole]
    source_kind: str
    narrative_intro: str
    placement_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _objective_from_source(source: dict[str, Any], kind: str) -> ChallengeObjective | None:
    """
    Derive a real-metric objective from the source result. Returns None
    (rather than a fabricated objective) if the source doesn't carry a
    metric this function recognizes.
    """
    if kind == "quantum_walk_fold" and "final_energy" in source:
        energy = float(source["final_energy"])
        # Threshold: beat the achieved energy by a further 10% -- a
        # reasonable competitive target derived from the real result,
        # not an arbitrary number.
        threshold = round(energy * 0.9, 4) if energy != 0 else -0.1
        return ChallengeObjective(
            metric="final_energy",
            comparison="below",
            threshold=threshold,
            description=f"Drive the folding energy below {threshold} (the source run reached {energy:.4f}).",
        )
    if kind == "quantum_vqe" and "ground_state_energy" in source:
        energy = float(source["ground_state_energy"])
        threshold = round(energy * 0.9, 4) if energy != 0 else -0.1
        return ChallengeObjective(
            metric="ground_state_energy",
            comparison="below",
            threshold=threshold,
            description=f"Beat the VQE ground-state energy of {threshold} (the source run reached {energy:.4f}).",
        )
    if kind == "admet_profile" and "endpoints" in source:
        endpoints: dict[str, Any] = source.get("endpoints", {})
        configured = [name for name, r in endpoints.items() if r.get("status") != "not_configured"]
        threshold = float(len(configured))
        return ChallengeObjective(
            metric="endpoints_cleared_count",
            comparison="equals",
            threshold=threshold,
            description=f"Clear all {int(threshold)} configured ADMET endpoints before time runs out.",
        )
    return None


def generate_multiplayer_challenge(
    source: dict[str, Any],
    round_duration_seconds: int = 300,
    team_count: int = 2,
) -> dict[str, Any]:
    """
    Generate a round-based multiplayer challenge structure from a
    scientific result -- a timer, a real-metric objective, and team
    roles -- suitable for placement in a live UEFN arena (e.g. via
    UEFN-TOOLBELT's Arena generator feature; see
    claude-skills/skills/uefn-fortnite-world-builder/SKILL.md for that
    feature's own verification status).

    Deterministic like generate_game_design (same sha256-seeded
    approach) -- the same source always regenerates the same
    challenge. Does not invoke anything live; returns a portable JSON
    structure.

    Args:
        source: The raw result dict from predict_structure_quantum_walk,
            predict_peptide_quantum_vqe, or predict_admet_profile.
        round_duration_seconds: Length of the round.
        team_count: Number of competing teams.

    Returns:
        A JSON-serializable dict (MultiplayerChallenge.to_dict()). If
        the source shape isn't recognized, `objective` is None rather
        than a fabricated one -- callers should check for this.
    """
    if round_duration_seconds <= 0:
        round_duration_seconds = 300
    if team_count <= 0:
        team_count = 2

    kind = _detect_source_kind(source)
    seed = _seed_from_source(source)
    objective = _objective_from_source(source, kind)

    team_roles = [
        TeamRole("Operator", "Adjusts the in-game parameter(s) that drive the underlying computation toward the objective."),
        TeamRole("Science Reviewer", "Checks any AI-generated Verse/device wiring before it's used, per uefn-fortnite-world-builder's own scope-limit note -- a real safety practice, gamified as a role rather than skipped."),
    ]

    if objective is not None:
        narrative = (
            f"{objective.description} Seed #{seed} -- replaying the same source result "
            "always regenerates this same challenge."
        )
    else:
        narrative = (
            f"No recognized real-metric objective could be derived from this source (kind={kind}) -- "
            "supply a predict_structure_quantum_walk, predict_peptide_quantum_vqe, or "
            "predict_admet_profile result to get a concrete objective."
        )

    challenge = MultiplayerChallenge(
        title=f"qFoldIT Arena Challenge: {kind.replace('_', ' ').title()}",
        seed=seed,
        round_duration_seconds=round_duration_seconds,
        team_count=team_count,
        objective=objective,
        team_roles=team_roles,
        source_kind=kind,
        narrative_intro=narrative,
        placement_note=(
            "This structure is engine-agnostic JSON, not a live UEFN call. Wiring it into an "
            "actual round (timer, win condition, scoring) requires either a human-authored Verse "
            "script, or -- if using the UEFN-TOOLBELT backend -- its verse_gen_game_skeleton tool "
            "as a starting point, reviewed before deployment."
        ),
    )
    return challenge.to_dict()
