"""
Tests for qFoldIT Trust & Compliance Runtime.
Run with: python3 -m pytest test_trust_runtime.py -v
(or just: python3 test_trust_runtime.py — falls back to a plain runner)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.compliance.trust_runtime import TrustRuntime  # noqa: E402


def _fresh_runtime(engine_version="UE5", manifest_path="qfoldit/compliance/license_manifest.json"):
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
        manifest_path="qfoldit/compliance/license_manifest.json",
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


def test_alias_resolves_to_canonical_manifest_entry():
    """A match on an alias (e.g. an alternate spelling/transliteration of
    a brand name) must resolve to the SAME manifest entry as the
    canonical English term — not fall through as a phantom unmatched
    term just because a different spelling was used. 'brikko' here is a
    synthetic stand-in alias, not a real brand spelling."""
    t = _fresh_runtime()
    t.aliases = {"brikko": "lego"}
    d = t.evaluate("execute_python", {"code": 'spawn_prop("assemble a brikko minifigure")'})
    assert d.allowed is True
    assert d.manifest_entry == "lego"


def test_alias_blocks_unlicensed_brand_same_as_canonical_would():
    t = _fresh_runtime()
    t.watchlist = t.watchlist + ["tesla motors"]
    t.aliases = {"teslamotorz": "tesla motors"}
    d = t.evaluate("execute_python", {"code": 'spawn_prop("teslamotorz model for the garage")'})
    assert d.allowed is False
    assert "tesla motors" in d.matched_terms


def test_unrelated_text_with_an_alias_configured_passes_cleanly():
    t = _fresh_runtime()
    t.aliases = {"brikko": "lego"}
    d = t.evaluate("execute_python", {"code": 'spawn_prop("an ordinary laboratory flask")'})
    assert d.allowed is True
    assert d.matched_terms == []


def test_extended_watchlist_alias_resolves_through_real_loader():
    """End-to-end: with_extended_watchlist() must thread its alias_map
    into TrustRuntime so a documented alias (e.g. 'kamaz-54901') would
    resolve to its canonical term 'kamaz' if that brand ever gets a real
    manifest entry -- verifies the fix to the latent flatten_enabled_terms
    bug, not just the aliases= constructor kwarg in isolation."""
    t = TrustRuntime.with_extended_watchlist(
        manifest_path="does_not_exist.json",
        audit_log_path=tempfile.mkstemp(suffix=".jsonl")[1],
    )
    assert t.aliases.get("kamaz-54901") == "kamaz"
    d = t.evaluate("execute_python", {"code": 'import_asset("kamaz-54901_truck_mesh")'})
    assert d.allowed is False
    assert "kamaz" in d.matched_terms


def test_manifest_entry_is_canonical_even_when_alias_is_also_a_flattened_watchlist_term():
    """Regression test: an extension watchlist's aliases get added to
    BOTH the flat watchlist AND the alias map by
    flatten_enabled_terms/build_extended_watchlist -- so a literal match
    on the alias text must still canonicalize before it becomes
    `manifest_entry`, not just when the alias is matched via the
    self.aliases loop alone. Without this, manifest_entry would surface
    the raw alias string where a license_manifest.json key ('lego') is
    expected, breaking every downstream royalty/conditions lookup for
    exactly the aliased-brand case this mechanism exists to support.
    Uses a synthetic in-memory extension (not a real watchlist file) so
    this test doesn't depend on which aliases happen to ship in
    watchlists/*.json."""
    from qfoldit.compliance.watchlist_loader import flatten_enabled_terms

    fake_extension = {"lego": {"aliases": ["brikko"], "enabled": True}}
    terms, alias_map = flatten_enabled_terms(fake_extension)
    t = TrustRuntime.with_extended_watchlist(audit_log_path=tempfile.mkstemp(suffix=".jsonl")[1])
    t.watchlist = list(dict.fromkeys([*t.watchlist, *terms]))
    t.aliases = {**t.aliases, **alias_map}
    assert "brikko" in t.watchlist  # the alias really is flattened into the literal term list
    assert t.aliases.get("brikko") == "lego"  # and also recorded as an alias
    d = t.evaluate("execute_python", {"code": 'spawn_prop("assemble a brikko minifigure")'})
    assert d.allowed is True
    assert d.manifest_entry == "lego"  # canonical manifest key, never the raw alias text
    assert d.matched_terms == ["lego"]  # deduplicated to the canonical form only


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
