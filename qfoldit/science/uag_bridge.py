"""
uag_bridge.py -- deterministic bridge between this package's own
`gamedesign.generate_game_design()` output and the `.claude/skills/
game-designer` skill's input contract.

WHAT THIS IS AND IS NOT
------------------------
`game-designer` is an LLM-driven skill: given a scene concept, it
designs nodes/connections/constraints/interactions and produces a full
Universal Assembly Graph (UAG). This module is NOT a replacement for
that reasoning -- it is a small, deterministic (no LLM, sha256-seeded,
same as gamedesign.py itself) piece of plumbing that does two things:

1. `to_source_context(doc)` -- formats a GameDesignDocument dict into
   the exact one-line `source_context` string the skill's own workflow
   (SKILL.md step 1) asks for, so a caller doesn't have to hand-write
   it or guess the shape.
2. `to_uag_seed(doc)` -- produces a minimal, already-VALID UAG (one
   `group` node per level, named after that level's title, with the
   par/checkpoint/star data preserved in `properties` for traceability)
   that the game-designer skill can extend rather than start from
   nothing. This is explicitly a SKELETON, not a finished scene -- it
   has no meshes, lights, or interactions, because inventing those
   would be exactly the kind of inventing-parameters-that-should-come-
   from-elsewhere behavior game-designer's own SKILL.md warns against.
   Treat every node here as "level N exists and needs real content",
   not as a finished level.

VALIDATION
----------
`to_uag_seed()`'s output is checked with a local copy of the same
`validate()` logic that lives in
`.claude/skills/game-designer/scripts/uag_validate.py`. The logic is
duplicated on purpose, not imported from `.claude/`: skills under
`.claude/skills/` are Claude Code's own tooling area (meant to be
read/executed by an agent, not guaranteed to be on the Python import
path of every deployment of this package), while `qfoldit/` is a
regular importable package with its own test suite. If you change the
validation rules, update both copies -- `tests/
test_qfoldit_uag_bridge.py` cross-checks the two files stay in sync
structurally (same known-type sets) so this doesn't silently drift.
"""

from __future__ import annotations

from typing import Any

# Kept identical to .claude/skills/game-designer/scripts/uag_validate.py
# on purpose -- see module docstring.
KNOWN_NODE_TYPES = {
    "mesh", "light", "camera", "trigger_volume",
    "ui_panel", "particle_emitter", "audio_source", "group", "custom",
}


def to_source_context(doc: dict[str, Any]) -> str:
    """Format a gamedesign.generate_game_design() output dict into the
    one-line source_context string game-designer's SKILL.md step 1
    expects ('e.g. "plant-growth skill, result for NPK-deficit K"')."""
    seed = doc.get("seed", "unknown")
    kind = doc.get("source_kind", "unknown")
    n_levels = len(doc.get("levels", []))
    n_achievements = len(doc.get("achievements", []))
    return (
        f"qfoldit_generate_game_design output, source_kind={kind}, "
        f"seed={seed}, {n_levels} level(s), {n_achievements} achievement(s), "
        f"total_score={doc.get('total_score', 0)}"
    )


def to_uag_seed(doc: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal, already-valid UAG skeleton (uag_version 0.1) --
    one 'group' node per level in `doc`, no meshes/lights/interactions.
    Meant to be handed to the game-designer skill as a starting point,
    not used directly as a finished scene."""
    levels = doc.get("levels", [])
    nodes: list[dict[str, Any]] = []
    for lvl in levels:
        n = lvl.get("level_number", len(nodes) + 1)
        nodes.append({
            "id": f"level_{n}_group",
            "type": "group",
            "transform": {
                "position": [0.0, float(n) * 500.0, 0.0],  # simple linear layout placeholder -- game-designer should replace this with real scene composition
                "rotation_euler_deg": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "properties": {
                "notes": (
                    f"SKELETON: level '{lvl.get('title')}' needs real "
                    f"content (meshes/lights/interactions) designed by the "
                    f"game-designer skill -- this is a placeholder group, "
                    f"not a finished level."
                ),
                "par_score": lvl.get("par_score"),
                "checkpoint_energy": lvl.get("checkpoint_energy"),
                "stars": lvl.get("stars"),
            },
            "parent_id": None,
        })

    return {
        "uag_version": "0.1",
        "metadata": {
            "name": doc.get("title", "qFoldIT scene"),
            "description": doc.get("tagline", ""),
            "source_context": to_source_context(doc),
        },
        "nodes": nodes,
        "connections": [],
        "constraints": [],
        "interactions": [],
    }


def validate_uag_seed(uag: dict[str, Any]) -> dict[str, Any]:
    """Lightweight structural check (unique ids, valid parent_id refs,
    no cycles) -- same rules as uag_validate.py's validate(), scoped to
    what to_uag_seed() can actually produce (nodes + parent_id only;
    a seed never has connections/constraints/interactions)."""
    errors: list[str] = []
    warnings: list[str] = []

    nodes = uag.get("nodes", [])
    if not isinstance(nodes, list):
        return {"valid": False, "errors": ["'nodes' must be a list."], "warnings": []}

    node_ids: set[str] = set()
    for i, node in enumerate(nodes):
        nid = node.get("id")
        if not nid:
            errors.append(f"nodes[{i}]: missing 'id'.")
            continue
        if nid in node_ids:
            errors.append(f"nodes[{i}]: duplicate id '{nid}'.")
        node_ids.add(nid)
        if node.get("type") not in KNOWN_NODE_TYPES:
            warnings.append(f"node '{nid}': type '{node.get('type')}' is not in the known set {sorted(KNOWN_NODE_TYPES)}.")

    parent_of: dict[str, str] = {}
    for node in nodes:
        nid = node.get("id")
        pid = node.get("parent_id")
        if pid is not None:
            if pid not in node_ids:
                errors.append(f"node '{nid}': parent_id '{pid}' does not exist among nodes.")
            else:
                parent_of[nid] = pid

    for start in list(parent_of.keys()):
        seen: set[str] = set()
        cur = start
        while cur in parent_of:
            if cur in seen:
                errors.append(f"Cycle detected in parent_child hierarchy involving node '{start}'.")
                break
            seen.add(cur)
            cur = parent_of[cur]

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "node_count": len(node_ids)}
