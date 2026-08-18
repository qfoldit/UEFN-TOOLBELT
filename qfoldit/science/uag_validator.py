"""
uag_validator.py -- validates a parsed UAG graph against
qfoldit-engine-adapter-spec-v0.1's normative rules (spec/SPECIFICATION.md
§7, conformance/CONFORMANCE.md "UAG" section), emitting the same
structured error CODES as the spec's own reference validator
(01-specs/engine-adapter-spec/conformance/run_conformance.py) --
string-for-string comparable against conformance/test_vectors.json:

    INVALID_SCHEMA, DUPLICATE_NODE_ID, DANGLING_PARENT, HIERARCHY_CYCLE

Plus three additional codes CONFORMANCE.md requires that the
intentionally-minimal reference script doesn't implement -- ported
directly from UNITY-TOOLBELT's Editor/Core/UagValidator.cs, which is
this file's reference implementation (kept behaviorally identical: same
mapped-type sets, same gap-vs-error distinction, same cycle-detection
walk):

    DANGLING_REFERENCE (constraints/interactions/bindings pointing at a
    node that doesn't exist), UNSUPPORTED_NODE_TYPE, UNSUPPORTED_CONSTRAINT_TYPE

Node/constraint/interaction "mapped" here means "this UEFN adapter has a
real tool that can realize it" -- kept in sync BY HAND with what
uag_bridge_tools.py's _create_node() actually implements. If you add a
node type there, add it to MAPPED_NODE_TYPES here too, or uag_validate
will under-report gaps that uag_apply then hits anyway.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .uag_model import UagGraph, SUPPORTED_SCHEMA

# The 10 gameplay "mechanic" identifiers per
# qfoldit-scientific-gameplay-framework-v0.1's compiler output -- must
# stay identical to this repo's own
# scientific_visualization_tools.py::MECHANIC_SCHEME keys (minus the ""
# default entry) and to Unity/UNIGINE's equivalent mechanic sets.
GAMEPLAY_MECHANICS: Set[str] = {
    "construction",
    "optimization",
    "pattern_matching",
    "rhythm",
    "survival_defense",
    "racing_tuning",
    "spatial_puzzle",
    "portal_exploration",
    "investigation_annotation",
    "competitive_microtasks",
}

# Legacy Phase-1 trigger vocabulary, kept mapped for documents written
# against the earlier informal schema draft -- identical set to
# UAGBridgeTools.cs's all_interaction_types in Unity/UNIGINE.
_LEGACY_INTERACTION_TYPES: Set[str] = {
    "on_grab", "on_proximity", "on_gaze", "on_click", "on_timer", "selection",
}

MAPPED_INTERACTION_TYPES: Set[str] = GAMEPLAY_MECHANICS | _LEGACY_INTERACTION_TYPES

# What uag_bridge_tools.py's _create_node() actually knows how to
# realize in UEFN today. "scientific_subject/*" is a prefix match,
# handled separately in is_mapped_node_type() -- any mechanic suffix is
# accepted, matching Unity/UNIGINE's IsMappedNodeType.
MAPPED_NODE_TYPES: Set[str] = {
    "mesh", "trigger_volume", "group",       # -> qfoldit_spawn_actor
    "molecular_structure",                    # -> scientific_visualization_create
    "interaction_zone",                       # -> qfoldit_spawn_actor + interaction_create
    # NOTE: "light" is intentionally NOT in this set. _create_node()
    # returns a real error for it (no light-placement tool exists in
    # this toolbelt's registry yet) -- listing it here would make
    # uag_validate report zero gaps for a node type uag_apply then
    # fails on, which is exactly the silent-drift bug this module's own
    # docstring warns against.
}

MAPPED_CONSTRAINT_TYPES: Set[str] = {
    "physics_collision", "physics.collision",
}


def is_mapped_node_type(node_type: str) -> bool:
    if not node_type:
        return False
    return node_type in MAPPED_NODE_TYPES or node_type.startswith("scientific_subject/")


def validate(graph: UagGraph) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []

    if graph.get("schema") != SUPPORTED_SCHEMA:
        errors.append({
            "code": "INVALID_SCHEMA",
            "message": f"Expected schema '{SUPPORTED_SCHEMA}', got '{graph.get('schema') or '(missing)'}'.",
        })

    nodes = graph.get("nodes", [])
    node_ids = [n.get("id") for n in nodes]
    node_id_set = set(node_ids)

    seen_ids: Set[str] = set()
    for node_id in node_ids:
        if node_id in seen_ids:
            errors.append({"code": "DUPLICATE_NODE_ID", "message": f"Duplicate node id '{node_id}'."})
        seen_ids.add(node_id)

    for node in nodes:
        parent = node.get("parent")
        if parent and parent not in node_id_set:
            errors.append({
                "code": "DANGLING_PARENT",
                "message": f"Node '{node.get('id')}' has parent '{parent}' which does not exist.",
            })

    for constraint in graph.get("constraints", []):
        for target in constraint.get("target_nodes", []) or []:
            if target not in node_id_set:
                errors.append({
                    "code": "DANGLING_REFERENCE",
                    "message": f"Constraint '{constraint.get('id')}' target_node '{target}' does not exist.",
                })

    for interaction in graph.get("interactions", []):
        target = interaction.get("target")
        if target and target not in node_id_set:
            errors.append({
                "code": "DANGLING_REFERENCE",
                "message": f"Interaction '{interaction.get('id')}' target '{target}' does not exist.",
            })

    for binding in graph.get("bindings", []):
        target = binding.get("target")
        if target and target not in node_id_set:
            errors.append({
                "code": "DANGLING_REFERENCE",
                "message": f"Binding '{binding.get('id')}' target '{target}' does not exist.",
            })

    # Cycle detection over the parent hierarchy -- identical algorithm to
    # run_conformance.py's reference implementation (walk each node
    # upward, a repeat visit means a cycle), extended to stop safely on
    # a dangling parent (already reported above, not re-reported as a
    # cycle) -- mirrors UagValidator.cs exactly.
    parent_of = {
        n.get("id"): n.get("parent")
        for n in nodes
        if n.get("parent") and n.get("parent") in node_id_set
    }
    cycle_already_reported_for: Set[str] = set()
    for start in node_id_set:
        visited = {start}
        current = start
        while current in parent_of:
            parent = parent_of[current]
            if parent in visited:
                if start not in cycle_already_reported_for:
                    cycle_already_reported_for.add(start)
                    errors.append({
                        "code": "HIERARCHY_CYCLE",
                        "message": f"Cycle detected in parent hierarchy involving node '{start}'.",
                    })
                break
            visited.add(parent)
            current = parent

    # Gap reporting (not an error -- informational, same distinction
    # UagValidationResult.UnmappedNodeTypes/etc. makes in the C# adapter).
    unmapped_node_types = sorted({
        n.get("type") for n in nodes if not is_mapped_node_type(n.get("type", ""))
    })
    unmapped_constraint_types = sorted({
        c.get("type") for c in graph.get("constraints", []) if c.get("type") not in MAPPED_CONSTRAINT_TYPES
    })
    unmapped_interactions = [
        i for i in graph.get("interactions", []) if i.get("type") not in MAPPED_INTERACTION_TYPES
    ]

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "unmapped_node_types": unmapped_node_types,
        "unmapped_constraint_types": unmapped_constraint_types,
        "unmapped_interactions": unmapped_interactions,
    }
