"""
UEFN Toolbelt — Scientific Visualization Tools (qFoldIT UAG bridge)
=======================================================================
The concrete "adapter"-level realization behind the
`scientific.visualization` capability — the UEFN counterpart to
UNITY-TOOLBELT's ScientificVisualizationTools.cs and UNIGINE-TOOLBELT's
ScientificVisualizationTools.cs.

Never re-implements a primitive: spawning goes through
core.spawn_static_mesh_actor (the same helper arena_generator.py already
uses, including its /Engine/BasicShapes/* fallback convention), and
material differentiation goes through the *existing*, real
`material_apply_preset` tool via get_registry().execute(...) — the exact
internal-call convention project_setup.py and verse_device_graph.py
already use elsewhere in this codebase.

Honest scope: no floating 3D label (matching UNIGINE-TOOLBELT's decision
here, for the same reason — no verified UEFN/Fortnite 3D-text-actor API
was found in this codebase to build on, so it isn't attempted rather than
guessed at). Scientific-state bindings are recorded as actor tags
(qfoldit:binding_source:<uri>), the same native, persistent mechanism
interaction_tools.py uses.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import unreal

from ..core import log_error, log_info, spawn_static_mesh_actor, undo_transaction
from ..registry import register_tool, get_registry

BINDING_TAG_PREFIX = "qfoldit:binding_source:"

# Same /Engine/BasicShapes/* convention arena_generator.py already
# establishes as this codebase's fallback-primitive mesh path.
MECHANIC_SCHEME = {
    "construction":              ("/Engine/BasicShapes/Cube",     "carbon_fiber"),
    "optimization":              ("/Engine/BasicShapes/Sphere",   "neon"),
    "pattern_matching":          ("/Engine/BasicShapes/Cylinder", "chrome"),
    "rhythm":                    ("/Engine/BasicShapes/Sphere",   "plasma"),
    "survival_defense":          ("/Engine/BasicShapes/Cone",     "rusty_metal"),
    "racing_tuning":             ("/Engine/BasicShapes/Cylinder", "gold"),
    "spatial_puzzle":            ("/Engine/BasicShapes/Cube",     "ice"),
    "portal_exploration":        ("/Engine/BasicShapes/Sphere",   "hologram"),
    "investigation_annotation":  ("/Engine/BasicShapes/Cone",     "jade"),
    "competitive_microtasks":    ("/Engine/BasicShapes/Cube",     "team_red"),
    "":                          ("/Engine/BasicShapes/Sphere",   "chrome"),  # default / molecular_structure
}


def _actor_subsystem():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _find_actor_by_label(label: str) -> Optional[unreal.Actor]:
    for actor in _actor_subsystem().get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    return None


def _run_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Same deliberate departure from project_setup.py's helper as
    uag_bridge_tools.py's _run(): registry.execute() returns None on an
    internally-caught exception, which must be treated as failure, not
    success, for this file's own status reporting to be trustworthy.
    """
    try:
        result = get_registry().execute(tool_name, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log_error(f"[qFoldIT] step '{tool_name}' raised: {exc}")
        return {"status": "error", "message": str(exc)}

    if result is None:
        return {"status": "error", "message": f"Tool '{tool_name}' failed (registry.execute() returned None)."}
    return result if isinstance(result, dict) else {"status": "success"}


@register_tool(
    name="qfoldit_spawn_actor",
    category="qFoldIT UAG Bridge",
    description=(
        "Spawns a StaticMeshActor at an exact world position with a given actor "
        "label. Generic primitive filling a gap in this toolbelt's existing "
        "registry — zone_spawn only spawns at camera position, and no other "
        "registered tool takes an explicit x/y/z. Defaults to /Engine/BasicShapes/Cube "
        "(the same fallback arena_generator.py already uses) if mesh_path is omitted."
    ),
    tags=["qfoldit", "uag", "spawn"],
    example='tb.run("qfoldit_spawn_actor", actor_label="Node1", x=0, y=0, z=100)',
)
def qfoldit_spawn_actor(actor_label: str = "", mesh_path: str = "", x: float = 0.0, y: float = 0.0, z: float = 0.0, **kwargs) -> Dict[str, Any]:
    if not actor_label:
        return {"status": "error", "error": "actor_label is required."}

    with undo_transaction("qFoldIT: Spawn Actor"):
        actor = spawn_static_mesh_actor(mesh_path or "/Engine/BasicShapes/Cube", unreal.Vector(x, y, z))
        if actor is None:
            return {"status": "error", "error": f"spawn_static_mesh_actor failed for mesh '{mesh_path}'."}
        actor.set_actor_label(actor_label)

    return {"status": "success", "actor_label": actor_label}


@register_tool(
    name="scientific_visualization_create",
    category="qFoldIT UAG Bridge",
    description=(
        "Creates a real, mechanic-differentiated visualization anchor for a UAG "
        "'scientific_subject/<mechanic>' node: a shaped, material-preset-colored "
        "actor at the given world position, plus a real binding tag if a source "
        "URI is given."
    ),
    tags=["qfoldit", "uag", "scientific"],
    example='tb.run("scientific_visualization_create", actor_label="Subject", mechanic="construction", x=0, y=0, z=100)',
)
def scientific_visualization_create(
    actor_label: str = "",
    mechanic: str = "",
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    source_uri: str = "",
    **kwargs,
) -> Dict[str, Any]:
    if not actor_label:
        return {"status": "error", "error": "actor_label is required."}

    mesh_path, preset = MECHANIC_SCHEME.get(mechanic, MECHANIC_SCHEME[""])

    with undo_transaction("qFoldIT: Create Scientific Visualization"):
        actor = spawn_static_mesh_actor(mesh_path, unreal.Vector(x, y, z))
        if actor is None:
            return {"status": "error", "error": f"spawn_static_mesh_actor failed for mesh '{mesh_path}'."}
        actor.set_actor_label(actor_label)

        # material_apply_preset (existing, real tool) operates on the
        # current selection — set it to just this actor first, matching
        # how a human would use the tool interactively.
        _actor_subsystem().set_selected_level_actors([actor])
        preset_result = _run_tool("material_apply_preset", preset=preset)

        bound = False
        if source_uri:
            bind_result = scientific_binding_create(actor_label=actor_label, source_uri=source_uri)
            bound = bind_result.get("status") == "success"

    log_info(f"[qFoldIT] Scientific visualization '{actor_label}' created (mechanic={mechanic or '(none)'}, preset={preset}).")

    return {
        "status": "success",
        "actor_label": actor_label,
        "mechanic": mechanic,
        "mesh_path": mesh_path,
        "material_preset": preset,
        "material_apply_status": preset_result.get("status"),
        "bound": bound,
    }


@register_tool(
    name="scientific_binding_create",
    category="qFoldIT UAG Bridge",
    description=(
        "Records a UAG bindings[] entry (actor -> scientific-state:// URI) as a "
        "real, persistent actor tag (qfoldit:binding_source:<uri>), instead of "
        "accepting-and-discarding it."
    ),
    tags=["qfoldit", "uag", "scientific"],
    example='tb.run("scientific_binding_create", actor_label="Subject", source_uri="scientific-state://protein_design_mcp/x")',
)
def scientific_binding_create(actor_label: str = "", source_uri: str = "", **kwargs) -> Dict[str, Any]:
    if not actor_label:
        return {"status": "error", "error": "actor_label is required."}
    if not source_uri:
        return {"status": "error", "error": "source_uri is required."}

    actor = _find_actor_by_label(actor_label)
    if actor is None:
        return {"status": "error", "error": f"No actor with label '{actor_label}' found."}

    with undo_transaction("qFoldIT: Create Scientific Binding"):
        tags = list(actor.tags or [])
        tags = [t for t in tags if not str(t).startswith(BINDING_TAG_PREFIX)]
        tags.append(f"{BINDING_TAG_PREFIX}{source_uri}")
        actor.set_editor_property("tags", tags)

    return {"status": "success", "actor_label": actor_label, "source_uri": source_uri}


@register_tool(
    name="scientific_binding_get",
    category="qFoldIT UAG Bridge",
    description="Reads back the scientific-state binding recorded on an actor by scientific_binding_create, if any.",
    tags=["qfoldit", "uag", "scientific"],
    example='tb.run("scientific_binding_get", actor_label="Subject")',
)
def scientific_binding_get(actor_label: str = "", **kwargs) -> Dict[str, Any]:
    actor = _find_actor_by_label(actor_label)
    if actor is None:
        return {"status": "error", "error": f"No actor with label '{actor_label}' found."}

    for tag in actor.tags or []:
        tag_str = str(tag)
        if tag_str.startswith(BINDING_TAG_PREFIX):
            return {"status": "success", "actor_label": actor_label, "source_uri": tag_str[len(BINDING_TAG_PREFIX):]}

    return {"status": "error", "error": f"No binding recorded on '{actor_label}'."}
