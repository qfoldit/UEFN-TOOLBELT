"""
UEFN Toolbelt — Interaction Tools (qFoldIT UAG bridge)
=========================================================
The concrete "adapter"-level realization behind the `interaction`
capability in qfoldit.adapter.json — the UEFN counterpart to
UNITY-TOOLBELT's Runtime/QFoldITInteractable.cs and UNIGINE-TOOLBELT's
InteractionTools.cs.

Design choice specific to UEFN: persistence uses the actor's own native
`tags` array (a real Unreal Engine actor property, already used elsewhere
in this codebase — see selection_utils.py / integration_test.py) instead
of a side JSON registry file. This is a deliberately *more* native
mechanism than either C# adapter uses: tags are saved with the level
itself, so `interaction_get`/`interaction_list` reading them back is
querying real, persistent level state, not an external file that could
drift out of sync with it.

Honest scope, matching this repo's own established pattern (see
UNIGINE-TOOLBELT's InteractionTools.cs docstring for the same caveat):
this does NOT wire a live click-to-callback. UEFN/Fortnite's native
interaction model is Verse Devices (Button Device, Trigger Device, etc.)
driven by generated Verse code, not a Python-attachable event handler —
Python can tag an actor (this file does), but cannot itself bind a live
callback the way a compiled MonoBehaviour can in Unity. A human (or a
follow-up Verse-authoring pass, using this toolbelt's existing
verse_snippet_generator.py) wires a generated stub to an actual Device in
the level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import unreal

from ..core import log_error, log_info, undo_transaction
from ..registry import register_tool

TAG_PREFIX = "qfoldit:interaction:"


def _actor_subsystem():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _find_actor_by_label(label: str) -> Optional[unreal.Actor]:
    """
    No existing find-by-label helper was found elsewhere in this codebase
    (selection_utils.py's select_in_radius matches by class, not label) —
    this is a small, new, focused addition, following the same pattern
    UNITY-TOOLBELT/UNIGINE-TOOLBELT used when a needed primitive was
    missing (e.g. spawn_group_node).
    """
    for actor in _actor_subsystem().get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    return None


def _interaction_tag(interaction_type: str) -> str:
    return f"{TAG_PREFIX}{interaction_type}"


def _get_interaction_type_from_tags(actor: unreal.Actor) -> Optional[str]:
    for tag in actor.tags or []:
        tag_str = str(tag)
        if tag_str.startswith(TAG_PREFIX):
            return tag_str[len(TAG_PREFIX):]
    return None


@register_tool(
    name="interaction_create",
    category="qFoldIT UAG Bridge",
    description=(
        "Makes an actor interactable: tags it with its UAG interaction type "
        "(qfoldit:interaction:<type>, a real, persistent actor tag — not a side "
        "file). Does NOT wire a live click callback — see this module's docstring."
    ),
    tags=["qfoldit", "uag", "interaction"],
    example='tb.run("interaction_create", actor_label="Subject", interaction_type="construction")',
)
def interaction_create(actor_label: str = "", interaction_type: str = "", **kwargs) -> Dict[str, Any]:
    if not actor_label:
        return {"status": "error", "error": "actor_label is required."}
    if not interaction_type:
        return {"status": "error", "error": "interaction_type is required."}

    actor = _find_actor_by_label(actor_label)
    if actor is None:
        return {"status": "error", "error": f"No actor with label '{actor_label}' found in the level."}

    with undo_transaction("qFoldIT: Create Interaction"):
        tags = list(actor.tags or [])
        # Replace any existing qfoldit:interaction:* tag rather than stacking duplicates.
        tags = [t for t in tags if not str(t).startswith(TAG_PREFIX)]
        tags.append(_interaction_tag(interaction_type))
        actor.set_editor_property("tags", tags)

    log_info(f"[qFoldIT] '{actor_label}' tagged interactable: {interaction_type}")

    return {
        "status": "success",
        "actor_label": actor_label,
        "interaction_type": interaction_type,
        "tag": _interaction_tag(interaction_type),
    }


@register_tool(
    name="interaction_get",
    category="qFoldIT UAG Bridge",
    description="Reads back the interaction type tagged on an actor by interaction_create, if any.",
    tags=["qfoldit", "uag", "interaction"],
    example='tb.run("interaction_get", actor_label="Subject")',
)
def interaction_get(actor_label: str = "", **kwargs) -> Dict[str, Any]:
    actor = _find_actor_by_label(actor_label)
    if actor is None:
        return {"status": "error", "error": f"No actor with label '{actor_label}' found."}

    interaction_type = _get_interaction_type_from_tags(actor)
    if interaction_type is None:
        return {"status": "error", "error": f"No interaction tag recorded on '{actor_label}'."}

    return {"status": "success", "actor_label": actor_label, "interaction_type": interaction_type}


@register_tool(
    name="interaction_list",
    category="qFoldIT UAG Bridge",
    description="Lists every actor in the level with a recorded qFoldIT interaction tag.",
    tags=["qfoldit", "uag", "interaction"],
    example='tb.run("interaction_list")',
)
def interaction_list(**kwargs) -> Dict[str, Any]:
    results: List[Dict[str, str]] = []
    for actor in _actor_subsystem().get_all_level_actors():
        interaction_type = _get_interaction_type_from_tags(actor)
        if interaction_type is not None:
            results.append({"actor_label": actor.get_actor_label(), "interaction_type": interaction_type})

    return {"status": "success", "count": len(results), "interactions": results}
