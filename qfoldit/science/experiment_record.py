"""
experiment_record.py -- ties one qFoldIT run into a single, reproducible,
licensing-cleared, publication-honest record.

This is the concrete first piece of the project's stated goal: turn a
gameplay session into a reproducible scientific experiment where every
object/action/computation automatically corresponds to a licensing
decision, a scientific-validity statement, and a publication-readiness
checklist. It does this by ASSEMBLING data this repo's own tools
already produce -- it does not run new science, generate new game
content, or invent a citation.

THREE THINGS THIS RECORD PROVES, NOT JUST ASSERTS
--------------------------------------------------
1. REPRODUCIBILITY -- `reproduce_with` records the exact function name
   and parameters (including any seed) needed to regenerate the
   identical scientific result. Both of this repo's science pipelines
   are already deterministic given a seed (quantum_runner.py's
   `simulate_quantum_walk_fold(seed=...)`) or already report every
   parameter needed to rerun them (`predict_peptide_quantum_vqe`'s
   alpha/shots). `experiment_id` is a sha256 hash over exactly those
   deterministic inputs+outputs -- two records with the same
   experiment_id are, by construction, the same experiment.
2. LICENSING -- `licensing` embeds every TrustRuntime.evaluate()
   Decision that was made while producing this experiment (asset/brand
   checks from trust_runtime.py), verbatim, so the record contains
   EVIDENCE of clearance rather than a claim of it. A record with any
   `allowed=False` entry is automatically flagged not publication-ready
   (see `publication_checklist`).
3. PUBLICATION READINESS -- `methods_section()` generates Methods text
   from a small, hand-curated citation table (`_METHOD_CITATIONS`)
   keyed off the ACTUAL algorithm kind, not the tool's marketing name.
   This is where the classical-vs-quantum honesty that already exists
   in quantum_runner.py's docstrings gets enforced in the OUTPUT text
   too: the classical Metropolis simulation is described as classical
   even though its tool name is "quantum_walk", and the real VQE path
   carries forward its own documented "not independently verified
   against the real qupepfold API" caveat. Both citations were checked
   against quantum_runner.py's own module docstring at authoring time
   -- if that docstring's citations ever change, update
   `_METHOD_CITATIONS` too; don't let the two drift apart.

WHAT THIS DELIBERATELY DOES NOT DO
------------------------------------
- Does not decide "this experiment IS publication ready" -- it reports
  which specific, individually-named checks pass or fail
  (`publication_checklist()`) and leaves the judgment call to a human.
  A dict of booleans is not a peer reviewer.
- Does not fabricate a citation for an unrecognized `science_source_kind`
  -- `methods_section()` returns a visible placeholder instead, so a
  missing citation is loud, not silently absent.
- Does not itself call TrustRuntime, gamedesign, or quantum_runner --
  the caller (typically the MCP tool wrapper in mcp_server.py) is
  responsible for actually running those and passing their real output
  in here.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# Citation table checked against quantum_runner.py's own module
# docstring at authoring time (2026-08-02) -- keep the two in sync.
_METHOD_CITATIONS: dict[str, dict[str, Any]] = {
    "quantum_vqe": {
        "name": "CVaR-optimized Variational Quantum Eigensolver (CVaR-VQE)",
        "citation": "Uttarkar et al., PLOS ONE, 2026 (QuPepFold)",
        "is_actually_quantum": True,
        "verification_caveat": (
            "This wrapper's call into the qupepfold package's public API was "
            "NOT independently verified against a real installed qupepfold "
            "release at authoring time (see quantum_runner.py's "
            "_run_qupepfold_job docstring). Disclose this in any methods "
            "section rather than presenting the call path as confirmed."
        ),
    },
    "quantum_walk_fold": {
        "name": (
            "Classical simulated-annealing Metropolis search over backbone "
            "torsion angles, with a quantum-walk-inspired biased move proposal"
        ),
        "citation": "Inspired by QFold (Casares et al., 2022) -- NOT a quantum computation",
        "is_actually_quantum": False,
        "verification_caveat": (
            "Despite the tool name 'quantum_walk', this ran entirely on "
            "classical hardware as a biased-proposal simulated-annealing "
            "search, not a quantum computation. It also has a documented "
            "kinetic-trapping limitation on chains of roughly 14+ residues "
            "-- disclose this if the sequence used was that long."
        ),
    },
}


@dataclass
class LicensingEntry:
    """One TrustRuntime.evaluate() decision folded into the record,
    kept verbatim (not summarized) so the record is evidence, not a
    paraphrase of evidence."""
    tool_name: str
    allowed: bool
    matched_terms: list[str]
    reason: str


def _methods_section(science_source_kind: str, reproduce_with: dict[str, Any]) -> str:
    info = _METHOD_CITATIONS.get(science_source_kind)
    if info is None:
        return (
            f"[UNRECOGNIZED SOURCE KIND '{science_source_kind}' -- no "
            f"citation-grounded methods text is available for this kind. "
            f"Write the Methods section manually; do not fabricate a "
            f"citation to fill this gap.]"
        )
    return "\n".join([
        f"{info['name']} ({info['citation']}) was used to produce this result.",
        info["verification_caveat"],
        f"Reproducibility: {json.dumps(reproduce_with, sort_keys=True)}",
    ])


def _publication_checklist(
    science_source_kind: str,
    licensing: list[LicensingEntry],
    reproduce_with: dict[str, Any],
) -> dict[str, Any]:
    blocked = [e for e in licensing if not e.allowed]
    info = _METHOD_CITATIONS.get(science_source_kind)
    checks = {
        "licensing_all_cleared": len(blocked) == 0,
        "science_kind_recognized": info is not None,
        "algorithm_correctly_labeled_quantum_vs_classical": info is not None,
        "deterministic_reproduction_recorded": bool(reproduce_with),
        "verification_caveat_disclosed": info is not None and bool(info.get("verification_caveat")),
    }
    checks["publication_ready"] = all(checks.values())
    if blocked:
        checks["blocked_licensing_details"] = [asdict(e) for e in blocked]
    return checks


def build_experiment_record(
    science_result: dict[str, Any],
    science_source_kind: str,
    game_design_seed: str | None = None,
    uag_metadata: dict[str, Any] | None = None,
    licensing_decisions: list[dict[str, Any]] | None = None,
    reproduce_with: dict[str, Any] | None = None,
    persist_path: str | None = None,
) -> dict[str, Any]:
    """
    Assemble an experiment record from pieces this repo's own tools
    already produced -- never fetches or invents anything.

    Args:
        science_result: Raw dict from simulate_quantum_walk_fold() or
            predict_peptide_quantum_vqe().
        science_source_kind: "quantum_walk_fold" or "quantum_vqe"
            (matches gamedesign.py's own `_detect_source_kind` naming
            so the same string can be reused across both modules).
        game_design_seed: Optional seed string from
            gamedesign.generate_game_design()'s output, if this
            experiment also produced a game design document.
        uag_metadata: Optional `uag["metadata"]` dict from
            uag_bridge.to_uag_seed(), if this experiment also produced
            a scene.
        licensing_decisions: Optional list of dicts shaped like
            TrustRuntime.Decision (tool_name/allowed/matched_terms/
            reason) made while producing this experiment. Typically
            supplied via TrustRuntime.decisions_since() so this is a
            read-back of real decisions, not hand-typed data.
        reproduce_with: Dict of the exact function name + parameters
            (including any seed) needed to regenerate `science_result`
            byte-for-byte. Required for `publication_checklist()`'s
            "deterministic_reproduction_recorded" check to pass.
        persist_path: Optional JSONL file path -- if given, the
            assembled record is appended there (one JSON object per
            line, same pattern as trust_runtime.py's own audit log) so
            it survives past the single MCP response that returned it.
            None (the default) keeps this function side-effect-free.

    Returns:
        A JSON-serializable dict with the assembled record plus
        precomputed `methods_section` (str) and `publication_checklist`
        (dict of named boolean checks -- never a bare "yes/no").
    """
    licensing = [
        LicensingEntry(
            tool_name=d.get("tool_name", "unknown"),
            allowed=bool(d.get("allowed", False)),
            matched_terms=list(d.get("matched_terms", [])),
            reason=d.get("reason", ""),
        )
        for d in (licensing_decisions or [])
    ]
    reproduce = reproduce_with or {}

    # experiment_id covers only the deterministic inputs/outputs of the
    # science itself -- NOT created_utc, NOT licensing (a re-run of the
    # exact same computation is the same experiment even if it's
    # re-licensed later or timestamped differently).
    hash_payload = json.dumps(
        {
            "science_source_kind": science_source_kind,
            "science_result": science_result,
            "game_design_seed": game_design_seed,
            "reproduce_with": reproduce,
        },
        sort_keys=True,
        default=str,
    )
    experiment_id = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()[:16]

    record = {
        "experiment_id": experiment_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "science_source_kind": science_source_kind,
        "science_result": science_result,
        "game_design_seed": game_design_seed,
        "uag_metadata": uag_metadata,
        "licensing": [asdict(e) for e in licensing],
        "reproduce_with": reproduce,
        "methods_section": _methods_section(science_source_kind, reproduce),
        "publication_checklist": _publication_checklist(science_source_kind, licensing, reproduce),
    }

    if persist_path:
        with open(persist_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return record


def list_experiment_records(persist_path: str, limit: int = 20) -> list[dict[str, Any]]:
    """Read back the most recent `limit` records written by
    build_experiment_record(persist_path=...). Returns [] (not an
    error) if the file doesn't exist yet -- no records built yet is a
    valid, empty state."""
    if not os.path.isfile(persist_path):
        return []
    records: list[dict[str, Any]] = []
    with open(persist_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a corrupt/partial line rather than fail the whole read
    return records[-limit:]
