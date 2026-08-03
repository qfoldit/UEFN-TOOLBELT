"""
Tests for qfoldit/science/uag_bridge.py.
Run with: python3 tests/test_qfoldit_uag_bridge.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.science.gamedesign import generate_game_design  # noqa: E402
from qfoldit.science.uag_bridge import (  # noqa: E402
    KNOWN_NODE_TYPES,
    to_source_context,
    to_uag_seed,
    validate_uag_seed,
)

_SKILL_VALIDATOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "skills", "game-designer", "scripts", "uag_validate.py",
)

_QUANTUM_WALK_SAMPLE = {
    "sequence": "ACDEFGHIK",
    "energy_trace": [10.0, 7.5, 5.2, 3.1, 2.4, 1.9],
    "final_energy": 1.9,
    "acceptance_ratio": 0.55,
}


def test_to_source_context_format():
    doc = generate_game_design(_QUANTUM_WALK_SAMPLE)
    ctx = to_source_context(doc)
    assert "source_kind=quantum_walk_fold" in ctx
    assert f"seed={doc['seed']}" in ctx
    assert isinstance(ctx, str) and len(ctx) < 300


def test_to_uag_seed_produces_one_group_per_level():
    doc = generate_game_design(_QUANTUM_WALK_SAMPLE)
    uag = to_uag_seed(doc)
    assert uag["uag_version"] == "0.1"
    assert len(uag["nodes"]) == len(doc["levels"])
    assert all(n["type"] == "group" for n in uag["nodes"])
    assert uag["connections"] == []
    assert uag["constraints"] == []
    assert uag["interactions"] == []


def test_to_uag_seed_preserves_traceable_metrics():
    doc = generate_game_design(_QUANTUM_WALK_SAMPLE)
    uag = to_uag_seed(doc)
    first_level = doc["levels"][0]
    first_node = uag["nodes"][0]
    assert first_node["properties"]["par_score"] == first_level["par_score"]
    assert first_node["properties"]["checkpoint_energy"] == first_level["checkpoint_energy"]
    assert first_node["properties"]["stars"] == first_level["stars"]


def test_to_uag_seed_is_deterministic():
    doc1 = generate_game_design(_QUANTUM_WALK_SAMPLE)
    doc2 = generate_game_design(_QUANTUM_WALK_SAMPLE)
    assert to_uag_seed(doc1) == to_uag_seed(doc2)


def test_validate_uag_seed_passes_on_own_output():
    doc = generate_game_design(_QUANTUM_WALK_SAMPLE)
    uag = to_uag_seed(doc)
    result = validate_uag_seed(uag)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_uag_seed_catches_duplicate_ids():
    uag = {
        "nodes": [
            {"id": "x", "type": "group", "parent_id": None},
            {"id": "x", "type": "group", "parent_id": None},
        ]
    }
    result = validate_uag_seed(uag)
    assert result["valid"] is False
    assert any("duplicate id" in e for e in result["errors"])


def test_validate_uag_seed_catches_cycles():
    uag = {
        "nodes": [
            {"id": "a", "type": "group", "parent_id": "b"},
            {"id": "b", "type": "group", "parent_id": "a"},
        ]
    }
    result = validate_uag_seed(uag)
    assert result["valid"] is False
    assert any("Cycle detected" in e for e in result["errors"])


def test_empty_levels_produces_empty_but_valid_uag():
    """admet_profile source kind has no levels -- must not crash, must
    still produce a structurally valid (if empty) UAG."""
    doc = generate_game_design({"endpoints": {"herg": {"status": "ok", "score": 0.2}}})
    uag = to_uag_seed(doc)
    assert uag["nodes"] == []
    result = validate_uag_seed(uag)
    assert result["valid"] is True


def test_known_node_types_match_skill_validator():
    """KNOWN_NODE_TYPES in this module is intentionally a duplicate (not
    an import) of the same set in the game-designer skill's own
    uag_validate.py -- see uag_bridge.py's module docstring for why.
    This test is the guardrail that keeps the two from silently
    drifting apart if one gets edited without the other."""
    if not os.path.isfile(_SKILL_VALIDATOR_PATH):
        print(f"SKIP test_known_node_types_match_skill_validator: "
              f"{_SKILL_VALIDATOR_PATH} not found in this checkout")
        return
    skill_source = open(_SKILL_VALIDATOR_PATH, encoding="utf-8").read()
    match = re.search(r"KNOWN_NODE_TYPES\s*=\s*\{([^}]*)\}", skill_source)
    assert match, "Could not find KNOWN_NODE_TYPES in the skill's uag_validate.py"
    skill_types = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert skill_types == KNOWN_NODE_TYPES, (
        f"Drift detected between uag_bridge.KNOWN_NODE_TYPES and the skill's "
        f"uag_validate.py: bridge has {KNOWN_NODE_TYPES}, skill has {skill_types}"
    )


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {test.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
