"""
uag_model.py -- Universal Assembly Graph data model for the UEFN adapter.

Python port of UNITY-TOOLBELT's Editor/Core/UagModel.cs, kept
field-for-field identical on purpose: both conform to the same formal,
normative schema shipped in qfoldit-engine-adapter-spec-v0.1
(schemas/uag.schema.json). See that C# file's header comment for the
schema-vs-informal-draft history; not repeated here.

This module is intentionally pure Python (zero `unreal` dependency,
zero third-party dependency) so it is importable and unit-testable
without the Editor -- the same design principle uag_bridge_tools.py's
own docstring describes for this package. It does NOT replace or modify
qfoldit/science/uag_bridge.py, which solves a different, unrelated
problem (game-designer skill plumbing); this module is the general UAG
parser/graph shape, named uag_model.py to match what
uag_bridge_tools.py already expects to import.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, TypedDict


class UagParseError(Exception):
    """Raised when a string is not valid UAG JSON (bad JSON, or not an object)."""


class UagNode(TypedDict, total=False):
    id: str
    type: str
    parent: Optional[str]
    transform: Dict[str, Any]
    properties: Dict[str, Any]
    metadata: Dict[str, Any]


class UagConstraint(TypedDict, total=False):
    id: str
    type: str
    target_nodes: List[str]
    properties: Dict[str, Any]


class UagInteraction(TypedDict, total=False):
    id: str
    type: str
    target: Optional[str]
    properties: Dict[str, Any]


class UagBinding(TypedDict, total=False):
    id: str
    source: str
    target: Optional[str]
    properties: Dict[str, Any]


class UagGraph(TypedDict, total=False):
    schema: str
    scene: Dict[str, Any]
    nodes: List[UagNode]
    constraints: List[UagConstraint]
    interactions: List[UagInteraction]
    bindings: List[UagBinding]
    metadata: Dict[str, Any]


SUPPORTED_SCHEMA = "qfoldit.uag/0.1"


def _position(node: Dict[str, Any]) -> tuple:
    """Convenience accessor over the loosely-typed 'transform' object --
    the formal schema only requires it to be an object, but every known
    producer (reference/compiler.py included) uses 'position': [x, y, z].
    Mirrors UagModel.cs's UagNode.Position."""
    transform = node.get("transform") or {}
    pos = transform.get("position")
    if isinstance(pos, list) and len(pos) == 3:
        return tuple(pos)
    return (0.0, 0.0, 0.0)


def parse_uag(uag_json: str) -> UagGraph:
    """Parses a UAG JSON string into the graph dict shape above, filling
    in every array/object field with a safe default so callers (this
    package's tool files) never need defensive .get(..., []) calls of
    their own. Raises UagParseError on invalid JSON or a non-object
    top level -- mirrors UagGraph.Parse's null-coalescing behavior in
    the C# adapter, but explicit rather than silently returning an
    empty graph."""
    try:
        doc = json.loads(uag_json)
    except json.JSONDecodeError as exc:
        raise UagParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise UagParseError(f"Expected a JSON object at the top level, got {type(doc).__name__}.")

    graph: UagGraph = {
        "schema": doc.get("schema"),
        "scene": doc.get("scene") or {},
        "nodes": doc.get("nodes") or [],
        "constraints": doc.get("constraints") or [],
        "interactions": doc.get("interactions") or [],
        "bindings": doc.get("bindings") or [],
        "metadata": doc.get("metadata") or {},
    }

    # Attach position/rotation/scale as plain tuples on each node's
    # 'properties' bag is deliberately NOT done here -- unlike the C#
    # adapter's convenience properties, this package's tool files
    # (_create_node in uag_bridge_tools.py) read node["position"]
    # directly via a small local unpack, so normalize position onto the
    # node dict itself instead of leaving callers to reach into
    # 'transform' every time.
    for node in graph["nodes"]:
        node["position"] = _position(node)
        node.setdefault("properties", node.get("properties") or {})
        node.setdefault("parent", node.get("parent"))

    return graph
