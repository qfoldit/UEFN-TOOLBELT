"""
Tests for qFoldIT Trust & Compliance Runtime.
Run with: python3 -m pytest test_trust_runtime.py -v
(or just: python3 test_trust_runtime.py — falls back to a plain runner)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit_trust_runtime import TrustRuntime  # noqa: E402


def _fresh_runtime(engine_version="UE5", manifest_path="license_manifest.json"):
    audit_fd, audit_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(audit_fd)
    return TrustRuntime(
        manifest_path=manifest_path,
        engine_version=engine_version,
        audit_log_path=audit_path,
    )


def test_default_deny_no_manifest():
    """No manifest at all -> unlisted brand terms are blocked."""
    t = _fresh_runtime(manifest_path="does_not_exist.json")
    d = t.evaluate("execute_python", {"code": 'import_asset("/Game/Custom/batman_mesh.uasset")'})
    assert d.allowed is False, "Unlicensed brand term must be blocked with an empty manifest"


def test_unrelated_call_passes():
    t = _fresh_runtime()
    d = t.evaluate("material_apply_preset", {"preset": "chrome"})
    assert d.allowed is True
    assert d.matched_terms == []


def test_lego_manifest_entry_passes_with_conditions():
    t = _fresh_runtime()
    d = t.evaluate("execute_python", {"code": 'spawn_lego_style("minifig")'})
    assert d.allowed is True
    assert d.manifest_entry == "lego"
    assert any("royalty" in c.lower() for c in d.conditions), "LEGO conditions must surface the royalty term"


def test_unlicensed_brand_blocked_even_with_manifest_present():
    """Marvel/DC/Rick and Morty terms must stay blocked even though the
    manifest file exists and has other real entries — presence of a
    manifest file does not mean everything in it is covered."""
    t = _fresh_runtime()
    d = t.evaluate("execute_python", {"code": 'spawn_character("rick sanchez")'})
    assert d.allowed is False
    assert "rick sanchez" in d.matched_terms


def test_epic_native_reference_bypasses_manifest_requirement():
    t = _fresh_runtime()
    d = t.evaluate("run_toolbelt_tool", {
        "tool_name": "spawn_gallery_item",
        "kwargs": {"path": "/FortniteGame/Galleries/LegoStyle/asset01"},
    })
    assert d.allowed is True
    assert "Epic-owned" in d.reason


def test_stale_engine_version_blocks_previously_valid_entry():
    """Manifest entries verified only for UE5 must NOT silently carry over to UE6."""
    t_ue6 = _fresh_runtime(engine_version="UE6")
    d = t_ue6.evaluate("execute_python", {"code": 'spawn_lego_style("minifig")'})
    assert d.allowed is False
    assert d.stale_engine_version is True


def test_matcher_ignores_punctuation_and_case_variants():
    t = _fresh_runtime()
    variants = [
        'import_asset("/Game/Custom/spiderman_mesh.uasset")',
        'import_asset("/Game/Custom/Spider-Man_Mesh.uasset")',
        'import_asset("/Game/Custom/SPIDER_MAN_mesh.uasset")',
    ]
    for code in variants:
        d = t.evaluate("execute_python", {"code": code})
        assert d.allowed is False, f"Should have been caught: {code}"
        assert "spider-man" in d.matched_terms


def test_describe_returns_no_entry_message_for_unlicensed_term():
    t = _fresh_runtime()
    out = t.describe("marvel")
    assert "No manifest entry" in out or "Blocked by default" in out


def test_describe_returns_conditions_for_licensed_term():
    t = _fresh_runtime()
    out = t.describe("tmnt")
    assert "Paramount" in out
    assert "Royalty: 15.0%" in out or "royalty" in out.lower()


def test_audit_log_records_every_decision():
    t = _fresh_runtime()
    t.evaluate("material_apply_preset", {"preset": "chrome"})
    t.evaluate("execute_python", {"code": 'spawn_character("batman")'})
    with open(t.audit_log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2


def _fresh_runtime_with_engine(asset_metadata_fn, engine_version="UE5"):
    audit_fd, audit_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(audit_fd)
    return TrustRuntime(
        manifest_path="license_manifest.json",
        engine_version=engine_version,
        audit_log_path=audit_path,
        asset_metadata_fn=asset_metadata_fn,
    )


def test_no_engine_hook_falls_back_to_text_heuristic():
    """Unchanged behavior when no asset_metadata_fn is wired: text match only."""
    t = _fresh_runtime()
    d = t.evaluate("execute_python", {"code": 'spawn("/EpicContent/StarWars/Grogu")'})
    assert d.allowed is True
    assert d.provenance_method == "text_heuristic"


def test_engine_hook_confirms_real_epic_native_asset():
    """A path that IS genuinely Epic-native per the engine -> allowed, engine_verified."""
    def fake_engine(ref):
        return {"resolved_path": "/EpicContent/StarWars/Grogu", "plugin_id": "epic.starwars"}

    t = _fresh_runtime_with_engine(fake_engine)
    d = t.evaluate("execute_python", {"code": 'spawn("/EpicContent/StarWars/Grogu")'})
    assert d.allowed is True
    assert d.provenance_method == "engine_verified"


def test_engine_hook_catches_spoofed_epic_native_path():
    """Text LOOKS Epic-native, but the engine says the asset actually lives
    somewhere else (a custom/imported asset with a misleading path string).
    Must be blocked, not trusted on text alone."""
    def fake_engine(ref):
        return {"resolved_path": "/Game/CustomImports/batman_suit", "plugin_id": "user.custom"}

    t = _fresh_runtime_with_engine(fake_engine)
    d = t.evaluate("execute_python", {"code": 'spawn("/EpicContent/DC/batman_suit")'})
    assert d.allowed is False
    assert d.provenance_method == "engine_mismatch"


def test_engine_hook_treats_unresolvable_ref_as_non_native():
    """Text claims an Epic-native path for a watchlisted brand, but the
    engine doesn't recognize the ref at all -> spoofing, blocked."""
    def fake_engine(ref):
        return None

    t = _fresh_runtime_with_engine(fake_engine)
    d = t.evaluate("execute_python", {"code": 'spawn("/EpicContent/StarWars/Nonexistent_grogu")'})
    assert d.allowed is False
    assert d.provenance_method == "engine_mismatch"


def test_manifest_entry_engine_verified_when_plugin_id_matches():
    """A manifest-covered brand whose content_plugin_ids includes the engine's
    reported plugin id for the referenced asset -> allowed, engine_verified."""
    def fake_engine(ref):
        return {"resolved_path": "/Game/LEGO/Minifig_01", "plugin_id": "epic.lego.official"}

    t = _fresh_runtime_with_engine(fake_engine)
    # LEGO entry ships with content_plugin_ids=[] by default (not yet
    # captured from a real inspection) -- inject one for this test to
    # simulate the manifest having been filled in with a real plugin id.
    t.manifest["lego"].content_plugin_ids = ["epic.lego.official"]
    d = t.evaluate("run_toolbelt_tool", {"tool_name": "import_asset", "path": "/Game/LEGO/Minifig_01"})
    assert d.allowed is True
    assert d.provenance_method == "engine_verified"


def test_manifest_entry_blocked_when_plugin_id_does_not_match():
    """Text says 'lego', but the engine's plugin id for the resolved asset
    isn't in this brand's documented content_plugin_ids -> blocked."""
    def fake_engine(ref):
        return {"resolved_path": "/Game/CustomImports/fake_lego_mesh", "plugin_id": "user.custom"}

    t = _fresh_runtime_with_engine(fake_engine)
    t.manifest["lego"].content_plugin_ids = ["epic.lego.official"]
    d = t.evaluate("run_toolbelt_tool", {"tool_name": "import_asset", "path": "/Game/CustomImports/fake_lego_mesh"})
    assert d.allowed is False
    assert d.provenance_method == "engine_mismatch"


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
