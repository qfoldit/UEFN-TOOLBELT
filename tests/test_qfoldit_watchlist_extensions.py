"""
Tests for the qFoldIT watchlist extensions (scientific equipment, vehicles)
and their integration with TrustRuntime.
Run with: python3 tests/test_qfoldit_watchlist_extensions.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qfoldit.compliance.trust_runtime import TrustRuntime, DEFAULT_WATCHLIST  # noqa: E402
from qfoldit.compliance.watchlist_loader import (  # noqa: E402
    load_all_watchlist_extensions,
    flatten_enabled_terms,
    build_extended_watchlist,
)


def _fresh_extended_runtime():
    audit_fd, audit_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(audit_fd)
    return TrustRuntime.with_extended_watchlist(audit_log_path=audit_path)


def test_extensions_load_without_error():
    ext = load_all_watchlist_extensions()
    assert "thermo fisher scientific" in ext
    assert "caterpillar" in ext
    assert "_readme" not in ext, "_README documentation key must be skipped"


def test_disabled_generic_terms_excluded_from_flattened_list():
    ext = load_all_watchlist_extensions()
    terms, alias_map = flatten_enabled_terms(ext)
    # "sever boats" (Russian for "north") is explicitly enabled=false due to false-positive risk
    assert "sever boats" not in terms
    # "cat" bare form was never added as a term/alias at all (only "caterpillar")
    assert "cat" not in terms
    assert "caterpillar" in terms


def test_build_extended_watchlist_merges_with_base():
    merged, meta, alias_map = build_extended_watchlist(DEFAULT_WATCHLIST)
    assert "lego" in merged, "base entertainment-IP watchlist must still be present"
    assert "agilent" in merged
    assert "sherp" in merged
    assert meta["agilent"]["category"] == "scientific_equipment_trademark"
    # kamaz-54901 is a documented alias of "kamaz" -> must resolve back to
    # the canonical term, not sit as an orphaned unmapped alias string.
    assert alias_map.get("kamaz-54901") == "kamaz"


def test_scientific_equipment_term_blocked_by_default():
    t = _fresh_extended_runtime()
    d = t.evaluate("execute_python", {"code": 'import_asset("/Game/Custom/agilent_hplc_mesh.uasset")'})
    assert d.allowed is False
    assert "agilent" in d.matched_terms
    assert "scientific_equipment_trademark" in d.reason


def test_vehicle_term_blocked_by_default():
    t = _fresh_extended_runtime()
    d = t.evaluate("execute_python", {"code": 'spawn_vehicle("Caterpillar D11 replica")'})
    assert d.allowed is False
    assert "caterpillar" in d.matched_terms
    assert "vehicle_trademark" in d.reason


def test_unrelated_call_still_passes_with_extended_watchlist():
    t = _fresh_extended_runtime()
    d = t.evaluate("material_apply_preset", {"preset": "chrome"})
    assert d.allowed is True
    assert d.matched_terms == []


def test_base_entertainment_ip_still_blocked_with_extended_watchlist():
    """Extending the watchlist must not weaken the existing LEGO/Marvel/etc. behavior."""
    t = _fresh_extended_runtime()
    d = t.evaluate("execute_python", {"code": 'spawn_character("rick sanchez")'})
    assert d.allowed is False
    assert "rick sanchez" in d.matched_terms


def test_default_trust_runtime_unaffected_when_extension_not_opted_in():
    """Plain TrustRuntime() (no with_extended_watchlist) must behave exactly
    as before this feature existed -- scientific/vehicle terms are NOT
    watchlisted unless explicitly opted in."""
    audit_fd, audit_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(audit_fd)
    t = TrustRuntime(audit_log_path=audit_path)
    d = t.evaluate("execute_python", {"code": 'import_asset("/Game/Custom/agilent_hplc_mesh.uasset")'})
    assert d.allowed is True, "Unextended TrustRuntime must not watchlist 'agilent'"


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
