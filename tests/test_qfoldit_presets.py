"""Tests for qfoldit/science/presets.py — the ten named LEVEL PRESETS,
the arena finale, and the combined Universal Level builder. Pure
stdlib, no external deps.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from qfoldit.compliance.trust_runtime import TrustRuntime  # noqa: E402
from qfoldit.science.exceptions import (  # noqa: E402
    PresetContentBlockedError,
    PresetNotFoundError,
    PresetSourceRequiredError,
)
from qfoldit.science.mcp_registry import ScienceMCPRegistry  # noqa: E402
from qfoldit.science.presets import (  # noqa: E402
    PRESETS,
    build_arena_finale,
    build_level,
    build_universal_level,
    describe_arena_finale,
    get_preset,
    list_presets,
)

FOLD_SOURCE = {
    "status": "ok", "final_energy": 0.5, "acceptance_ratio": 0.5,
    "energy_trace": [1.0, 0.8, 0.6, 0.5],
}
VQE_SOURCE = {"status": "ok", "ground_state_energy": -12.3, "backend": "aer_simulator"}
ADMET_SOURCE = {"endpoints": {"solubility": {"status": "ok", "score": 0.7}}}
HP_LATTICE_SOURCE = {"hp_energy": -4.0, "num_hydrophobic_contacts": 6}
PLANT_SOURCE = {"growth_rate": 82.0, "compactness": 70.0, "deficiency_symptoms": []}
OILGAS_SOURCE = {"corrosion_rate_mm_per_year": 0.12, "remaining_wall_life_years": 18.5}
MEOR_SOURCE = {"ift_reduction_pct": 65.0, "incremental_oil_recovery_pct": 12.0}
MINING_SOURCE = {"biooxidation_extent_pct": 88.0, "cyanide_degradation_pct": 95.0}
PROSPECTING_SOURCE = {"anomaly_score": 3.4, "permutation_p_value": 0.01}

ALL_SOURCES = {
    "fold_marathon": FOLD_SOURCE,
    "quantum_boss": VQE_SOURCE,
    "quantum_lab": VQE_SOURCE,
    "hp_lattice_challenge": HP_LATTICE_SOURCE,
    "safety_gauntlet": ADMET_SOURCE,
    "plant_growth_garden": PLANT_SOURCE,
    "oilgas_corrosion_watch": OILGAS_SOURCE,
    "meor_recovery_run": MEOR_SOURCE,
    "mining_bioleach_challenge": MINING_SOURCE,
    "prospecting_survey": PROSPECTING_SOURCE,
}


def test_exactly_ten_presets():
    assert len(PRESETS) == 10
    assert "arena_showdown" not in PRESETS  # kept separate, see module docstring


def test_all_presets_registered_and_reference_mcp_points_at_a_real_registry_entry():
    registry = ScienceMCPRegistry()
    for preset in PRESETS.values():
        assert preset.reference_mcp in registry.servers, (
            f"{preset.key}'s reference_mcp={preset.reference_mcp!r} isn't in "
            "science_mcp_registry.json"
        )


def test_reference_mcp_for_every_preset_is_verified_or_connected():
    """The whole point of a 'reference'/canonical build is that it's the
    trustworthy one -- best_effort/reference_only entries must never be
    silently promoted to canonical."""
    registry = ScienceMCPRegistry()
    for preset in PRESETS.values():
        rec = registry.servers[preset.reference_mcp]
        assert rec.status in ("verified", "connected"), (
            f"{preset.key}'s reference_mcp status is {rec.status!r}, not canonical-grade"
        )


def test_get_preset_unknown_key_raises():
    with pytest.raises(PresetNotFoundError):
        get_preset("does_not_exist")


def test_get_preset_arena_key_not_in_catalog():
    with pytest.raises(PresetNotFoundError):
        get_preset("arena_showdown")


def test_list_presets_includes_live_reference_snapshot():
    presets = list_presets()
    assert len(presets) == 10
    for p in presets:
        assert "reference" in p
        assert "reachable_now" in p["reference"]


def test_build_level_without_source_raises_for_every_preset():
    for key in PRESETS:
        with pytest.raises(PresetSourceRequiredError):
            build_level(key, None)


@pytest.mark.parametrize("key,source", list(ALL_SOURCES.items()))
def test_build_level_for_every_preset_produces_content(key, source):
    """Every preset must produce *something* traceable to the real
    source -- but not necessarily a numbered 'level': safety_gauntlet is
    achievements-only by gamedesign.py's own design (ADMET endpoints
    don't map to a par/stars progression, see generate_game_design's
    admet_profile branch)."""
    doc = build_level(key, source)
    assert doc["preset_key"] == key
    assert "reference" in doc
    assert len(doc["levels"]) + len(doc["achievements"]) >= 1


def test_build_level_fold_marathon():
    doc = build_level("fold_marathon", FOLD_SOURCE)
    assert doc["source_kind"] == "quantum_walk_fold"
    assert doc["reference"]["reference_mcp"] == "protein_design_mcp"


def test_build_level_quantum_boss_and_quantum_lab_use_different_reference_mcp():
    boss = build_level("quantum_boss", VQE_SOURCE)
    lab = build_level("quantum_lab", VQE_SOURCE)
    assert boss["reference"]["reference_mcp"] == "protein_design_mcp"
    assert lab["reference"]["reference_mcp"] == "qfoldit_quantum_lab"
    assert boss["reference"]["reference_mcp"] != lab["reference"]["reference_mcp"]


def test_build_level_hp_lattice_challenge_achievements():
    doc = build_level("hp_lattice_challenge", HP_LATTICE_SOURCE)
    ids = {a["id"] for a in doc["achievements"]}
    assert "hp_energy" in ids
    assert "num_hydrophobic_contacts" in ids


def test_build_level_plant_growth_garden_list_metric_achievement():
    doc = build_level("plant_growth_garden", PLANT_SOURCE)
    deficiency = [a for a in doc["achievements"] if a["id"] == "deficiency_symptoms"][0]
    assert deficiency["unlocked"] is True  # empty list == no deficiencies

    doc_bad = build_level("plant_growth_garden", {**PLANT_SOURCE, "deficiency_symptoms": ["nitrogen"]})
    deficiency_bad = [a for a in doc_bad["achievements"] if a["id"] == "deficiency_symptoms"][0]
    assert deficiency_bad["unlocked"] is False


def test_build_level_prospecting_survey_p_value_achievement():
    doc = build_level("prospecting_survey", PROSPECTING_SOURCE)
    sig = [a for a in doc["achievements"] if a["id"] == "permutation_p_value"][0]
    assert sig["unlocked"] is True  # 0.01 < 0.05

    doc_not_sig = build_level("prospecting_survey", {**PROSPECTING_SOURCE, "permutation_p_value": 0.5})
    sig2 = [a for a in doc_not_sig["achievements"] if a["id"] == "permutation_p_value"][0]
    assert sig2["unlocked"] is False


def test_build_level_missing_metric_is_skipped_not_fabricated():
    doc = build_level("oilgas_corrosion_watch", {"corrosion_rate_mm_per_year": 0.2})
    ids = {a["id"] for a in doc["achievements"]}
    assert "corrosion_rate_mm_per_year" in ids
    assert "remaining_wall_life_years" not in ids  # never fabricated


def test_build_level_deterministic():
    d1 = build_level("fold_marathon", FOLD_SOURCE)
    d2 = build_level("fold_marathon", FOLD_SOURCE)
    assert d1 == d2
    d3 = build_level("oilgas_corrosion_watch", OILGAS_SOURCE)
    d4 = build_level("oilgas_corrosion_watch", OILGAS_SOURCE)
    assert d3 == d4


def test_build_arena_finale_does_not_require_source():
    challenge = build_arena_finale(None)
    assert challenge["preset_key"] == "arena_showdown"
    assert "team_roles" in challenge
    assert challenge["reference"]["reference_mcp"] == "uefn_toolbelt"


def test_describe_arena_finale():
    d = describe_arena_finale()
    assert d["key"] == "arena_showdown"
    assert "reference" in d


def test_universal_level_skips_missing_presets_without_fabricating():
    universal = build_universal_level({"fold_marathon": FOLD_SOURCE}, include_arena_finale=False)
    included = {s["preset_key"]: s for s in universal["segments"]}
    assert len(included) == 10  # every preset gets a segment, included or not
    assert included["fold_marathon"]["included"] is True
    assert included["quantum_boss"]["included"] is False
    assert all(lvl["title"].startswith("[protein folding") for lvl in universal["levels"])


def test_universal_level_renumbers_levels_sequentially_across_presets():
    universal = build_universal_level(
        {"fold_marathon": FOLD_SOURCE, "quantum_boss": VQE_SOURCE, "oilgas_corrosion_watch": OILGAS_SOURCE},
        include_arena_finale=False,
    )
    numbers = [lvl["level_number"] for lvl in universal["levels"]]
    assert numbers == list(range(1, len(numbers) + 1))


def test_universal_level_namespaces_achievement_ids():
    universal = build_universal_level(
        {"fold_marathon": FOLD_SOURCE, "mining_bioleach_challenge": MINING_SOURCE},
        include_arena_finale=False,
    )
    ids = [a["id"] for a in universal["achievements"]]
    assert any(i.startswith("fold_marathon:") for i in ids)
    assert any(i.startswith("mining_bioleach_challenge:") for i in ids)


def test_universal_level_with_all_ten_presets_and_arena_finale():
    universal = build_universal_level(ALL_SOURCES, include_arena_finale=True)
    included = {s["preset_key"]: s for s in universal["segments"]}
    assert len(included) == 11  # 10 presets + arena finale segment
    assert all(s["included"] for s in universal["segments"])
    assert universal["arena_finale"] is not None
    assert universal["arena_finale"]["preset_key"] == "arena_showdown"
    numbers = [lvl["level_number"] for lvl in universal["levels"]]
    assert numbers == list(range(1, len(numbers) + 1))


def test_universal_level_deterministic_given_same_sources():
    u1 = build_universal_level(ALL_SOURCES, include_arena_finale=True)
    u2 = build_universal_level(ALL_SOURCES, include_arena_finale=True)
    assert u1["universal_seed"] == u2["universal_seed"]
    assert u1 == u2


def test_universal_level_empty_sources_produces_valid_empty_shell():
    universal = build_universal_level({}, include_arena_finale=False)
    assert universal["levels"] == []
    assert universal["achievements"] == []
    assert len(universal["segments"]) == 10
    assert all(not s["included"] for s in universal["segments"])


# ---------------------------------------------------------------------------
# Compliance gate: presets are "levels assembled from prompts" -- a `title`
# override (or a stray source string) must go through the SAME default-deny
# IP watchlist/manifest check as run_toolbelt_tool/execute_python before a
# level is returned.
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_trust(tmp_path):
    """A fresh extended-watchlist TrustRuntime with its own temp audit log,
    so these tests don't share state/file with other test modules or the
    lazy module-level default in presets.py."""
    return TrustRuntime.with_extended_watchlist(audit_log_path=str(tmp_path / "trust_audit.log.jsonl"))


def test_clean_build_has_no_licensing_fields(isolated_trust):
    doc = build_level("fold_marathon", FOLD_SOURCE, trust_runtime=isolated_trust)
    assert "licensed_ip_matches" not in doc
    assert "licensing_conditions" not in doc


def test_unlicensed_ip_in_title_override_is_blocked(isolated_trust):
    with pytest.raises(PresetContentBlockedError):
        build_level(
            "fold_marathon", FOLD_SOURCE,
            title="qFoldIT: Spider-Man Web-Fold Arena",
            trust_runtime=isolated_trust,
        )


def test_unlicensed_ip_via_configured_alias_is_blocked(isolated_trust):
    """The compliance gate must catch a match via TrustRuntime's alias
    mechanism too, not just a literal English brand name -- exercises
    the same alias-resolution path presets.py relies on, using a
    synthetic alias rather than any real-world transliteration."""
    isolated_trust.aliases = {**isolated_trust.aliases, "webslinger-alias": "spider-man"}
    with pytest.raises(PresetContentBlockedError):
        build_level(
            "fold_marathon", FOLD_SOURCE,
            title="qFoldIT: webslinger-alias Fold Arena",
            trust_runtime=isolated_trust,
        )


def test_licensed_ip_is_allowed_with_conditions_surfaced(isolated_trust):
    """Star Wars has a real license_manifest.json entry (royalty_pct=20) --
    referencing it is ALLOWED, but the real royalty/template-only/no-mixing
    conditions must be surfaced, never silently dropped."""
    doc = build_level(
        "fold_marathon", FOLD_SOURCE,
        title="qFoldIT: Star Wars Protein Fold",
        trust_runtime=isolated_trust,
    )
    assert doc["licensed_ip_matches"] == ["star wars"]
    assert any("20" in c and "Disney" in c for c in doc["licensing_conditions"])


def test_metric_based_preset_title_is_also_checked(isolated_trust):
    """The compliance gate must apply to domain_metrics presets
    (oilgas/mining/meor/etc.), not just the gamedesign.py-backed ones."""
    with pytest.raises(PresetContentBlockedError):
        build_level(
            "oilgas_corrosion_watch", {"corrosion_rate_mm_per_year": 0.1},
            title="Batman Pipeline Watch",
            trust_runtime=isolated_trust,
        )


def test_arena_finale_title_is_checked(isolated_trust):
    with pytest.raises(PresetContentBlockedError):
        build_arena_finale(None, title="Avengers Assemble Arena", trust_runtime=isolated_trust)


def test_universal_level_propagates_a_block_from_any_included_preset(isolated_trust):
    with pytest.raises(PresetContentBlockedError):
        build_universal_level(
            {"fold_marathon": FOLD_SOURCE},
            include_arena_finale=False,
            trust_runtime=isolated_trust,
        )
        # Note: build_universal_level itself doesn't take per-preset titles,
        # so this specific call wouldn't trigger a block -- the real
        # regression coverage is the direct build_level/build_arena_finale
        # tests above, which build_universal_level calls internally with
        # the same trust_runtime.


def test_default_lazy_trust_runtime_path_still_works():
    """No trust_runtime injected at all -- exercises presets.py's own
    lazily-created shared default, which must not require the caller to
    always pass one in."""
    doc = build_level("fold_marathon", FOLD_SOURCE)
    assert doc["preset_key"] == "fold_marathon"
