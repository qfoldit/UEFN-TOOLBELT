#!/usr/bin/env python3
"""
Validator for the Universal Assembly Graph (UAG). Used by game-designer
when creating a graph, and by EVERY engine-specific skill
(unreal-world-builder, unity-experience-builder,
unigine-simulation-engineer, openusd-architect, apple-spatial-designer,
threejs-web-designer) before export — don't export an invalid graph; run
it through this script first.

Checks:
1. Required fields / basic structure.
2. That all ids in nodes are unique.
3. That all references (parent_id, from_node, to_node, target_nodes,
   target_node) point to an existing node id.
4. No cycles in the parent_child hierarchy.
5. (warning, not an error) node types/triggers with no known engine
   mapping -- printed as a warning, does not block.
"""

import argparse
import json
import sys

KNOWN_NODE_TYPES = {
    "mesh", "light", "camera", "trigger_volume",
    "ui_panel", "particle_emitter", "audio_source", "group", "custom",
}
KNOWN_CONNECTION_TYPES = {
    "parent_child", "joint_fixed", "joint_hinge", "joint_slider", "data_link",
}
KNOWN_CONSTRAINT_TYPES = {
    "physics_collision", "interaction_grabbable", "animation_trigger", "logic_rule",
}
KNOWN_TRIGGERS = {"on_grab", "on_proximity", "on_gaze", "on_click", "on_timer"}


def validate(uag: dict) -> dict:
    errors = []
    warnings = []

    if "nodes" not in uag or not isinstance(uag["nodes"], list):
        errors.append("Missing or malformed 'nodes' field (must be a list).")
        return {"valid": False, "errors": errors, "warnings": warnings}

    node_ids = set()
    for i, node in enumerate(uag["nodes"]):
        nid = node.get("id")
        if not nid:
            errors.append(f"nodes[{i}]: missing 'id'.")
            continue
        if nid in node_ids:
            errors.append(f"nodes[{i}]: duplicate id '{nid}'.")
        node_ids.add(nid)
        if node.get("type") not in KNOWN_NODE_TYPES:
            warnings.append(
                f"node '{nid}': type '{node.get('type')}' is not in the known list "
                f"({sorted(KNOWN_NODE_TYPES)}) -- the engine-specific skill must "
                f"explicitly tell the user that this type has no defined mapping, "
                f"rather than silently skipping it."
            )

    # Validate parent_id + collect hierarchy edges for cycle detection.
    parent_of = {}
    for node in uag["nodes"]:
        nid = node.get("id")
        pid = node.get("parent_id")
        if pid is not None:
            if pid not in node_ids:
                errors.append(f"node '{nid}': parent_id '{pid}' does not exist among nodes.")
            else:
                parent_of[nid] = pid

    # Cycle detection in parent_child.
    for start in list(parent_of.keys()):
        seen = set()
        cur = start
        while cur in parent_of:
            if cur in seen:
                errors.append(f"Cycle detected in the parent_child hierarchy, involving node '{start}'.")
                break
            seen.add(cur)
            cur = parent_of[cur]

    # connections
    for i, conn in enumerate(uag.get("connections", [])):
        ctype = conn.get("type")
        if ctype not in KNOWN_CONNECTION_TYPES:
            warnings.append(f"connections[{i}]: unknown type '{ctype}'.")
        for field in ("from_node", "to_node"):
            ref = conn.get(field)
            if ref is not None and ref not in node_ids:
                errors.append(f"connections[{i}]: {field} '{ref}' does not exist among nodes.")

    # constraints
    for i, constr in enumerate(uag.get("constraints", [])):
        ctype = constr.get("type")
        if ctype not in KNOWN_CONSTRAINT_TYPES:
            warnings.append(f"constraints[{i}]: unknown type '{ctype}'.")
        for ref in constr.get("target_nodes", []):
            if ref not in node_ids:
                errors.append(f"constraints[{i}]: target_nodes contains a nonexistent id '{ref}'.")

    # interactions
    for i, inter in enumerate(uag.get("interactions", [])):
        trig = inter.get("trigger")
        if trig not in KNOWN_TRIGGERS:
            warnings.append(f"interactions[{i}]: unknown trigger '{trig}'.")
        ref = inter.get("target_node")
        if ref is not None and ref not in node_ids:
            errors.append(f"interactions[{i}]: target_node '{ref}' does not exist among nodes.")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "node_count": len(node_ids)}


def main():
    parser = argparse.ArgumentParser(description="Validate a Universal Assembly Graph (UAG)")
    parser.add_argument("uag_file", help="Path to the UAG JSON file")
    args = parser.parse_args()

    with open(args.uag_file, "r", encoding="utf-8") as f:
        uag = json.load(f)

    result = validate(uag)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
