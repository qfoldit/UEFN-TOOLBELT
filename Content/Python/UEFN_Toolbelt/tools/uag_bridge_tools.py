"""
UEFN Toolbelt — UAG Bridge Tools (qFoldIT)
=============================================
The piece that actually connects UEFN-TOOLBELT to the rest of the
qFoldIT stack (SOS -> SKG -> SEM -> UAG -> UWI -> MCP) as *in-Editor,
callable-by-name* tools — the UEFN counterpart to UNITY-TOOLBELT's and
UNIGINE-TOOLBELT's UAGBridgeTools.cs.

Design principle carried over unchanged from the C# adapters: this file
never re-implements a primitive. Every node/constraint/interaction/binding
it can realize, it realizes by calling this toolbelt's own already-
registered tools via get_registry().execute(name, **kwargs) — the exact
internal-call convention project_setup.py and verse_device_graph.py
already use elsewhere in this codebase, and the exact same architectural
choice UNIGINE-TOOLBELT's UAGBridgeTools.cs made (dispatch through the
registry by name, not direct calls) specifically so this adapter has no
special access any other caller lacks.

The pure-Python parsing/validation logic lives in qfoldit/science/
uag_model.py and uag_validator.py (repo root, zero `unreal` dependency,
importable and testable without the Editor — see tests/test_uag_model.py
and tests/test_uag_validator.py) — this file is the thin, `unreal`-
dependent realization layer on top of them.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import unreal

from ..core import log_error, log_info
from ..registry import register_tool, get_registry

# ── Cross-package import: qfoldit/ lives at the repo root, alongside
# Content/. Editor Python's sys.path doesn't include it by default (only
# Content/Python/ and the custom-plugins dir are added at startup — see
# UEFN_Toolbelt/__init__.py's register()), so add it defensively here,
# the same sys.path.insert pattern already used in this codebase for the
# custom-plugins dir and for smoke_test.py's dynamic import. ──
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from qfoldit.science.uag_model import parse_uag, UagParseError
    from qfoldit.science.uag_validator import validate as validate_uag, is_mapped_node_type, GAMEPLAY_MECHANICS
    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # noqa: BLE001 — reported via the tool's own return value, not a hard import crash
    _IMPORT_ERROR = str(exc)

ADAPTER_ID = "qfoldit-uefn-toolbelt"
ADAPTER_VERSION = "0.1.0"
ENGINE_ID = "uefn"


def _run(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    NOTE: get_registry().execute() catches internal exceptions and returns
    None on failure (see registry.py's own docstring) rather than
    re-raising — project_setup.py's equivalent helper treats that None as
    "ok", which would silently misreport real tool failures as success in
    an execution report whose entire point is honest status reporting.
    Deliberately NOT copying that here: None is treated as an error.
    """
    try:
        result = get_registry().execute(tool_name, **kwargs)
    except Exception as exc:  # noqa: BLE001 — belt-and-braces; execute() shouldn't raise per its own contract, but don't trust that blindly
        log_error(f"[qFoldIT UAG] step '{tool_name}' raised: {exc}")
        return {"status": "error", "error": str(exc)}

    if result is None:
        return {"status": "error", "error": f"Tool '{tool_name}' failed (registry.execute() returned None — see the Editor log for the underlying exception)."}
    return result if isinstance(result, dict) else {"status": "success"}


@register_tool(
    name="uag_validate",
    category="qFoldIT UAG Bridge",
    description=(
        "Validates a UAG document against this engine's adapter: schema id, "
        "duplicate/dangling references, hierarchy cycles, and which node/"
        "constraint/interaction types this adapter can and cannot realize. "
        "Makes no changes to the level. Errors are {code, message} objects "
        "matching qfoldit-engine-adapter-spec-v0.1's conformance vectors."
    ),
    tags=["qfoldit", "uag", "validate"],
    example='tb.run("uag_validate", uag_json=open("scene.uag.json").read())',
)
def uag_validate(uag_json: str = "", **kwargs) -> Dict[str, Any]:
    if _IMPORT_ERROR:
        return {"status": "error", "error": f"qfoldit.science import failed: {_IMPORT_ERROR}"}
    try:
        graph = parse_uag(uag_json)
    except UagParseError as exc:
        return {"status": "error", "error": f"Could not parse UAG JSON: {exc}"}

    result = validate_uag(graph)
    return {
        "status": "success",
        "is_valid": result["is_valid"],
        "errors": result["errors"],
        "unmapped_node_types": result["unmapped_node_types"],
        "unmapped_constraint_types": result["unmapped_constraint_types"],
        "unmapped_interactions": result["unmapped_interactions"],
        "node_count": len(graph["nodes"]),
        "constraint_count": len(graph["constraints"]),
        "interaction_count": len(graph["interactions"]),
        "binding_count": len(graph["bindings"]),
    }


@register_tool(
    name="uag_apply",
    category="qFoldIT UAG Bridge",
    description=(
        "Realizes a validated UAG document in the current level by calling this "
        "toolbelt's own registered tools. Returns a structured execution report "
        "(status/created/updated/skipped/gaps/warnings/errors) matching "
        "schemas/execution-report.schema.json. Aborts with no level changes if "
        "validation fails."
    ),
    tags=["qfoldit", "uag", "apply"],
    example='tb.run("uag_apply", uag_json=open("scene.uag.json").read())',
)
def uag_apply(uag_json: str = "", **kwargs) -> Dict[str, Any]:
    if _IMPORT_ERROR:
        return _report("failed", errors=[{"code": "IMPORT_ERROR", "message": _IMPORT_ERROR}])

    try:
        graph = parse_uag(uag_json)
    except UagParseError as exc:
        return _report("failed", errors=[{"code": "PARSE_ERROR", "message": str(exc)}])

    validation = validate_uag(graph)
    if not validation["is_valid"]:
        return _report("failed", errors=validation["errors"], provenance=_provenance(graph))

    created: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    gaps: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    unrealized: set = set()

    # ── Pass 1: create every node ──
    for node in graph["nodes"]:
        node_id, node_type = node["id"], node["type"]
        if not is_mapped_node_type(node_type):
            unrealized.add(node_id)
            skipped.append(node_id)
            gaps.append({"element": "node", "id": node_id, "type": node_type, "reason": "unmapped node type"})
            continue

        result = _create_node(node)
        if result.get("status") == "success":
            created.append(node_id)
        else:
            unrealized.add(node_id)
            skipped.append(node_id)
            errors.append({"code": "NODE_CREATE_FAILED", "node_id": node_id, "type": node_type,
                            "message": result.get("error", "unknown error")})

    # ── Pass 2: parent hierarchy ──
    for node in graph["nodes"]:
        node_id, parent = node["id"], node.get("parent")
        if not parent or node_id in unrealized or parent in unrealized:
            continue
        result = _run("actor_attach_to_parent", child_label=node_id, parent_label=parent)
        if result.get("status") == "success" and node_id not in updated:
            updated.append(node_id)
        elif result.get("status") != "success":
            warnings.append({"code": "PARENT_ATTACH_FAILED", "node_id": node_id,
                              "message": result.get("error", "actor_attach_to_parent failed")})

    # ── Pass 3: constraints ──
    for c in graph["constraints"]:
        valid_targets = [t for t in c["target_nodes"] if t not in unrealized]
        if c["type"] in ("physics_collision", "physics.collision"):
            # No dedicated collision-constraint tool was found in this
            # codebase's registry to reuse — UEFN actors get collision from
            # their static mesh by default, so this is a no-op acknowledgment
            # rather than a fabricated call to a tool that doesn't exist.
            for target in valid_targets:
                if target not in updated:
                    updated.append(target)
            warnings.append({"code": "COLLISION_IS_DEFAULT", "constraint_id": c["id"],
                              "message": "UEFN StaticMeshActors have collision from their mesh by default; no explicit physics_collision tool was found to call."})
        else:
            gaps.append({"element": "constraint", "id": c["id"], "type": c["type"], "reason": "unmapped constraint type"})

    # ── Pass 4: interactions — REAL realization via interaction_create ──
    all_interaction_types = GAMEPLAY_MECHANICS | {"on_grab", "on_proximity", "on_gaze", "on_click", "on_timer", "selection"}
    for i in graph["interactions"]:
        target = i.get("target")
        if not target or target in unrealized:
            gaps.append({"element": "interaction", "id": i["id"], "type": i["type"], "reason": "target node was not realized"})
            continue
        if i["type"] not in all_interaction_types:
            gaps.append({"element": "interaction", "id": i["id"], "type": i["type"], "reason": "unmapped interaction type"})
            continue

        _run("interaction_create", actor_label=target, interaction_type=i["type"])
        if target not in updated:
            updated.append(target)
        if i["type"] in GAMEPLAY_MECHANICS:
            warnings.append({
                "code": "INTERACTABLE_TAGGED_NOT_GAMEPLAY_COMPLETE",
                "interaction_id": i["id"],
                "message": (
                    f"'{target}' is now tagged qfoldit:interaction:{i['type']}, but this does NOT wire a "
                    f"live callback — UEFN/Fortnite's native interaction model is Verse Devices, not a "
                    f"Python-attachable event handler. A human (or a follow-up Verse-authoring pass) must "
                    f"wire a Device in the level to this tag. Full '{i['type']}' gameplay logic remains out "
                    f"of scope for a generic adapter regardless."
                ),
            })

    # ── Pass 5: bindings — REAL realization via scientific_binding_create ──
    for b in graph["bindings"]:
        target = b.get("target")
        if not target or target in unrealized:
            gaps.append({"element": "binding", "id": b["id"], "reason": "target node was not realized"})
            continue
        _run("scientific_binding_create", actor_label=target, source_uri=b["source"])
        if target not in updated:
            updated.append(target)

    status = "failed" if errors and not created else ("partial" if (gaps or warnings or errors) else "success")
    return _report(status, created, updated, skipped, gaps, warnings, errors, _provenance(graph))


def _create_node(node: Dict[str, Any]) -> Dict[str, Any]:
    node_id, node_type = node["id"], node["type"]
    x, y, z = node["position"]
    properties = node["properties"]

    if node_type.startswith("scientific_subject/"):
        mechanic = node_type[len("scientific_subject/"):]
        return _run("scientific_visualization_create", actor_label=node_id, mechanic=mechanic,
                    x=x, y=y, z=z, source_uri=properties.get("source", ""))

    if node_type == "molecular_structure":
        return _run("scientific_visualization_create", actor_label=node_id, mechanic="",
                    x=x, y=y, z=z, source_uri=properties.get("source", ""))

    if node_type == "interaction_zone":
        result = _run("qfoldit_spawn_actor", actor_label=node_id, x=x, y=y, z=z)
        if result.get("status") == "success":
            _run("interaction_create", actor_label=node_id, interaction_type=properties.get("interaction", "selection"))
        return result

    if node_type in ("mesh", "trigger_volume", "group"):
        # NOTE on "group": Unity/UNIGINE map this to a genuinely empty
        # transform-only container (spawn_group_node / NodeDummy). No
        # equivalent "empty actor with no mesh" spawn was found in this
        # codebase's registry, so "group" gets a small visible cube marker
        # here instead — an honest simplification, not a silent gap.
        mesh_path = properties.get("mesh_ref") or "/Engine/BasicShapes/Cube"
        return _run("qfoldit_spawn_actor", actor_label=node_id, mesh_path=mesh_path, x=x, y=y, z=z)

    if node_type == "light":
        # No dedicated light-placement tool was found in this codebase's
        # registry (unlike Unity/UNIGINE's light_create) to reuse without
        # guessing at a Fortnite light-device class path — reported as a
        # per-node failure rather than a fabricated spawn.
        return {"status": "error", "error": "No light-placement tool found in this toolbelt's registry to reuse for UAG 'light' nodes yet."}

    return {"status": "error", "error": f"No creation handler for node type '{node_type}'."}


def _provenance(graph: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": graph.get("schema"),
        "scene_id": (graph.get("scene") or {}).get("id"),
        "compiler": (graph.get("metadata") or {}).get("compiler"),
    }


def _report(status: str, created=None, updated=None, skipped=None, gaps=None, warnings=None, errors=None, provenance=None) -> Dict[str, Any]:
    return {
        "success": status != "failed",
        "status": status,
        "engine": ENGINE_ID,
        "adapter": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "created": created or [],
        "updated": updated or [],
        "skipped": skipped or [],
        "gaps": gaps or [],
        "warnings": warnings or [],
        "errors": errors or [],
        "provenance": provenance,
    }
