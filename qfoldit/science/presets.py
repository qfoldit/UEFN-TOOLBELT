"""
presets.py -- qFoldIT LEVEL PRESETS: TEN named level "recipes" sitting on
top of gamedesign.py, plus one combined "Universal Level" that stitches
all ten into a single playthrough, and a separate arena finale mechanism.

WHAT A PRESET IS
----------------
A LevelPreset is metadata, not a science engine: a title/tagline/
difficulty for a theme, PLUS which capability it expects, PLUS which
entry in science_mcp_registry.json is that domain's canonical /
"reference" build -- i.e. the one entry with status
"verified" or "connected" for that capability, as opposed to any
"best_effort" (unverified community bridge) or "reference_only"
(documentation-only) entry that might exist for something adjacent. From
science_mcp_registry.json today:

  domain                                  reference_mcp
  ---------------------------------------  --------------------------
  protein fold (classical walk)            protein_design_mcp
  peptide CVaR-VQE ground state            protein_design_mcp
  general molecular/spin VQE (H2 bench)    qfoldit_quantum_lab
  HP-lattice QAOA folding                  qfoldit_qfold_lab
  ADMET / molecular safety                 boltz_api
  plant growth + L-system rendering        qfoldit_plant_growth_lab
  pipeline CO2 corrosion                   qfoldit_oilgas_lab
  microbial enhanced oil recovery (MEOR)   qfoldit_meor_lab
  bio-oxidation / biosorption / cyanide     qfoldit_mining_lab
  biogeochemical prospecting                qfoldit_prospecting_lab
  (arena finale, not one of the 10)        uefn_toolbelt

Everything else on file for adjacent capabilities (protein_mcp_upstream,
protein_design_mcp_upstream, uefn_mcp_server_kirchuvakov,
uefn_verse_mcp_quangdang46, unity_mcp_server, unigine_mcpbridge,
kit_usd_agents) stays best_effort/reference_only and is deliberately NOT
promoted to canonical here -- see mcp_registry.py's own STATUS LEVELS
docstring for why that distinction matters.

Six of the ten presets (quantum_lab, hp_lattice_challenge,
plant_growth_garden, oilgas_corrosion_watch, meor_recovery_run,
mining_bioleach_challenge, prospecting_survey minus quantum_lab which
reuses gamedesign's existing quantum_vqe shape -- see PRESETS below for
the exact split) are backed by qfoldit-skills Claude Skill plugins
bundled in this environment rather than code inside this repo. This
module does not call those skills itself (no LLM call, no network call,
same rule as gamedesign.py) -- it only RE-THEMES a result someone already
obtained by running that skill. The expected field names for those six
are a best-effort mapping from each skill's own public description, NOT
independently inspected against real output in this authoring session --
flagged plainly in science_mcp_registry.json's notes for each entry and
in each preset's `.notes` below, the same "documented-uncertainty"
convention already used by pipelines/quantum_runner.py's qupepfold
wrapper. If a skill's real output uses different field names, update the
MetricSpec lists below -- never silently rename the incoming data to
force a match.

WHAT A PRESET IS NOT
--------------------
No LLM call, no network call, nothing fabricated. build_level() only
re-themes a science result that was already produced elsewhere. If no
source is supplied, this module raises PresetSourceRequiredError rather
than inventing one -- there is no "demo data" path here, intentionally.

THE ARENA FINALE (not one of the 10)
-------------------------------------
arena_showdown is real and useful, but it isn't a science domain -- it's
a round-based multiplayer wrapper (gamedesign.generate_multiplayer_challenge)
realized in a live UEFN session. Kept as a dedicated function
(build_arena_finale) rather than an 11th PRESETS entry, so `len(PRESETS)
== 10` stays literally true; build_universal_level() can still append it
as an optional closing round.

THE UNIVERSAL LEVEL
--------------------
build_universal_level() takes a dict of {preset_key: source_or_None} and
produces one combined document: every present preset's levels are
renumbered into one sequential run, achievements are namespaced
(f"{preset_key}:{achievement_id}") to avoid id collisions, and a
`segments` manifest records, per preset, whether it was included and
which reference MCP backed it. Presets with no source are listed as
`included: false` rather than silently dropped or faked.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .exceptions import PresetContentBlockedError, PresetNotFoundError, PresetSourceRequiredError
from .gamedesign import (
    _DIFFICULTY_PAR_TIGHTNESS,
    _seed_from_source,
    _stars_from_margin,
    generate_game_design,
    generate_multiplayer_challenge,
)
from .mcp_registry import ScienceMCPRegistry
from ..compliance.trust_runtime import TrustRuntime

Difficulty = Literal["story", "adaptive", "hardcore"]


@dataclass
class MetricSpec:
    """One headline metric this preset reads from a real source dict --
    never fabricated, simply skipped if the key is absent."""
    key: str
    label: str
    higher_is_better: bool = False
    unit: str = ""


@dataclass
class LevelPreset:
    key: str
    title: str
    tagline: str
    domain: str                          # human-readable theme label
    expects_source_kind: str             # "quantum_walk_fold" | "quantum_vqe" | "admet_profile" | "domain_metrics"
    difficulty: Difficulty
    reference_mcp: str                   # key into science_mcp_registry.json -- the canonical build for this domain
    metrics: list[MetricSpec] | None = None   # set -> use _build_metric_level; None -> delegate to gamedesign.generate_game_design
    list_metric: tuple[str, str] | None = None   # (key, label) -- achievement unlocked if source[key] == []
    p_value_metric: tuple[str, str, float] | None = None  # (key, label, threshold) -- achievement unlocked if source[key] < threshold
    notes: str = ""


# ---------------------------------------------------------------------------
# The catalog -- exactly TEN single-player presets. Keys are stable
# identifiers; treat renaming one as a breaking change for any caller
# that persisted a preset_key.
# ---------------------------------------------------------------------------
PRESETS: dict[str, LevelPreset] = {

    "fold_marathon": LevelPreset(
        key="fold_marathon",
        title="qFoldIT: Protein Folding Dynamics",
        tagline="Fold your way from chaos to a stable conformation, one Metropolis move at a time.",
        domain="protein folding (classical walk simulation)",
        expects_source_kind="quantum_walk_fold",
        difficulty="adaptive",
        reference_mcp="protein_design_mcp",
        notes=(
            "Source: qfoldit_quantum_walk_fold / simulate_quantum_walk_fold(). A REAL classical "
            "Metropolis simulation inspired by, but not equivalent to, actual quantum-walk QFold -- "
            "see quantum_runner.py's own module docstring before presenting a run as 'quantum'."
        ),
    ),

    "quantum_boss": LevelPreset(
        key="quantum_boss",
        title="qFoldIT: Quantum Peptide Folding (VQE)",
        tagline="Beat the quantum computer to the peptide's ground state.",
        domain="peptide ground-state search (CVaR-VQE)",
        expects_source_kind="quantum_vqe",
        difficulty="hardcore",
        reference_mcp="protein_design_mcp",
        notes=(
            "Source: qfoldit_quantum_vqe_fold / predict_peptide_quantum_vqe(). Import-guarded -- "
            "returns status='unavailable' (never a fabricated energy) unless the separate "
            "'qupepfold' package is installed. Build only from an actual result dict."
        ),
    ),

    "quantum_lab": LevelPreset(
        key="quantum_lab",
        title="qFoldIT: Quantum Chemistry & Molecular VQE",
        tagline="Drive a small molecule's Hamiltonian down to its true ground-state energy.",
        domain="general molecular/spin VQE (statevector simulation)",
        expects_source_kind="quantum_vqe",
        difficulty="adaptive",
        reference_mcp="qfoldit_quantum_lab",
        notes=(
            "Source: a qfoldit-quantum skill result -- same 'ground_state_energy' shape gamedesign.py "
            "already detects, but a DIFFERENT domain from quantum_boss: general small-molecule/spin "
            "Hamiltonians (validated on H2/STO-3G), not peptide folding. Do not mix the two sources up "
            "when picking which preset to build."
        ),
    ),

    "hp_lattice_challenge": LevelPreset(
        key="hp_lattice_challenge",
        title="qFoldIT: HP-Lattice Protein Folding (QAOA)",
        tagline="Pack the chain onto the lattice and maximize hydrophobic contacts.",
        domain="2D HP-lattice protein folding (QAOA)",
        expects_source_kind="domain_metrics",
        difficulty="adaptive",
        reference_mcp="qfoldit_qfold_lab",
        metrics=[
            MetricSpec("hp_energy", "HP Lattice Energy", higher_is_better=False),
            MetricSpec("num_hydrophobic_contacts", "Hydrophobic Contacts Formed", higher_is_better=True),
        ],
        notes=(
            "Expects a qfoldit-qfold skill result. Field names (hp_energy, num_hydrophobic_contacts) "
            "are a best-effort mapping from the skill's public description -- not independently "
            "inspected. Distinct from fold_marathon/quantum_boss: this is a discrete HP-lattice model "
            "(Dill, 1985) via QAOA, not a continuous torsion-angle walk or a peptide VQE."
        ),
    ),

    "safety_gauntlet": LevelPreset(
        key="safety_gauntlet",
        title="qFoldIT: ADMET Toxicology & Drug Design",
        tagline="Clear every safety trial before your candidate molecule ships.",
        domain="ADMET / molecular safety screening",
        expects_source_kind="admet_profile",
        difficulty="story",
        reference_mcp="boltz_api",
        notes=(
            "Source: a result dict shaped like {'endpoints': {name: {'status', 'score'}, ...}} -- "
            "e.g. from a Boltz ADME call. This repo does not implement predict_admet_profile() "
            "itself; gamedesign.py documents the expected shape."
        ),
    ),

    "plant_growth_garden": LevelPreset(
        key="plant_growth_garden",
        title="qFoldIT: PARAMETRIC L-SYSTEMS",
        tagline="Tune the light and nutrients until the plant thrives, then watch it render as a living L-system.",
        domain="plant growth / morphology (NPK + light response)",
        expects_source_kind="domain_metrics",
        difficulty="story",
        reference_mcp="qfoldit_plant_growth_lab",
        metrics=[
            MetricSpec("growth_rate", "Growth Rate", higher_is_better=True),
            MetricSpec("compactness", "Canopy Compactness", higher_is_better=True),
        ],
        list_metric=("deficiency_symptoms", "No Deficiency Symptoms"),
        notes=(
            "Expects a qfoldit-plant-growth-model skill result, paired with qfoldit-l-systems for "
            "the visual. Field names (growth_rate, compactness, deficiency_symptoms) are a "
            "best-effort mapping from the skill's public description -- not independently inspected."
        ),
    ),

    "oilgas_corrosion_watch": LevelPreset(
        key="oilgas_corrosion_watch",
        title="qFoldIT: Pipeline Corrosion Engineering",
        tagline="Dose the inhibitor right and keep the corrosion rate below the line.",
        domain="pipeline CO2 (sweet) corrosion",
        expects_source_kind="domain_metrics",
        difficulty="adaptive",
        reference_mcp="qfoldit_oilgas_lab",
        metrics=[
            MetricSpec("corrosion_rate_mm_per_year", "Corrosion Rate", higher_is_better=False, unit=" mm/yr"),
            MetricSpec("remaining_wall_life_years", "Remaining Wall Life", higher_is_better=True, unit=" yr"),
        ],
        notes=(
            "Expects a qfoldit-oilgas skill result (de Waard-Milliams correlation). Field names are "
            "a best-effort mapping from the skill's public description -- not independently "
            "inspected. Never fabricate a corrosion rate; this preset refuses without a real result."
        ),
    ),

    "meor_recovery_run": LevelPreset(
        key="meor_recovery_run",
        title="qFoldIT: Microbial Enhanced Oil Recovery",
        tagline="Grow the right biosurfactant-producing culture and squeeze out the trapped oil.",
        domain="microbial enhanced oil recovery (MEOR)",
        expects_source_kind="domain_metrics",
        difficulty="adaptive",
        reference_mcp="qfoldit_meor_lab",
        metrics=[
            MetricSpec("ift_reduction_pct", "Interfacial Tension Reduction", higher_is_better=True, unit="%"),
            MetricSpec("incremental_oil_recovery_pct", "Incremental Oil Recovery", higher_is_better=True, unit="%"),
        ],
        notes=(
            "Expects a qfoldit-meor skill result (capillary desaturation curve). Field names are a "
            "best-effort mapping from the skill's public description -- not independently inspected."
        ),
    ),

    "mining_bioleach_challenge": LevelPreset(
        key="mining_bioleach_challenge",
        title="qFoldIT: Biomining & Bioleaching",
        tagline="Bio-oxidize the ore, recover the metal, and detoxify the tailings before discharge.",
        domain="bio-oxidation / biosorption / cyanide degradation",
        expects_source_kind="domain_metrics",
        difficulty="hardcore",
        reference_mcp="qfoldit_mining_lab",
        metrics=[
            MetricSpec("biooxidation_extent_pct", "Bio-oxidation Extent", higher_is_better=True, unit="%"),
            MetricSpec("cyanide_degradation_pct", "Cyanide Degradation", higher_is_better=True, unit="%"),
        ],
        notes=(
            "Expects a qfoldit-mining skill result (Shrinking Core / Arrhenius / Langmuir / "
            "pseudo-second-order kinetics). Field names are a best-effort mapping from the skill's "
            "public description -- not independently inspected."
        ),
    ),

    "prospecting_survey": LevelPreset(
        key="prospecting_survey",
        title="qFoldIT: Biogeochemical Mineral Prospecting",
        tagline="Find the microbial indicator signal that actually separates on-deposit from background.",
        domain="biogeochemical mineral-exploration prospecting",
        expects_source_kind="domain_metrics",
        difficulty="hardcore",
        reference_mcp="qfoldit_prospecting_lab",
        metrics=[
            MetricSpec("anomaly_score", "Anomaly Score", higher_is_better=True),
        ],
        p_value_metric=("permutation_p_value", "Statistically Significant Signal", 0.05),
        notes=(
            "Expects a qfoldit-prospecting skill result (Chao1/inverse-Simpson diversity, "
            "response-ratio effect sizes, permutation validity check). Field names are a "
            "best-effort mapping from the skill's public description -- not independently "
            "inspected. The 'Statistically Significant Signal' achievement is gated on the "
            "skill's own reported permutation_p_value < 0.05 -- never lowered to unlock easier."
        ),
    ),
}

# The arena finale is deliberately NOT in PRESETS -- see module docstring.
_ARENA_KEY = "arena_showdown"
_ARENA_PRESET = LevelPreset(
    key=_ARENA_KEY,
    title="qFoldIT Arena: Live Showdown",
    tagline="Two teams race the same real metric to zero, live, in front of an audience.",
    domain="round-based multiplayer, realized in UEFN",
    expects_source_kind="any",
    difficulty="adaptive",
    reference_mcp="uefn_toolbelt",
    notes=(
        "Wraps gamedesign.generate_multiplayer_challenge(). Placement in a live round still "
        "requires either a human-authored Verse script or the UEFN-TOOLBELT backend's own "
        "verse_gen_game_skeleton tool, reviewed before deployment. reference_mcp is uefn_toolbelt "
        "(the runtime that actually places devices/actors), not a science server."
    ),
)


def _reference_note(preset: LevelPreset, registry: ScienceMCPRegistry) -> dict[str, Any]:
    """Live reachability snapshot for a preset's canonical MCP server --
    computed fresh every call (never cached) so a stale 'reachable' claim
    can't survive a registry/session change."""
    rec = registry.servers.get(preset.reference_mcp)
    reachable, reason = registry.can_connect(preset.reference_mcp)
    return {
        "reference_mcp": preset.reference_mcp,
        "reference_mcp_provider": rec.provider if rec else "unknown",
        "reference_mcp_status": rec.status if rec else "unregistered",
        "reachable_now": reachable,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Compliance gate. Presets are levels ASSEMBLED FROM PROMPTS -- a `title`
# override, or a stray string value inside a `source` dict, is exactly as
# capable of naming an unlicensed universe/character/item as anything typed
# into run_toolbelt_tool/execute_python. Those two are always gated by
# compliance/trust_runtime.py's default-deny watchlist/manifest check; a
# level built here is no different just because it hasn't been placed in
# UEFN yet -- the same text ends up as level/achievement titles that a
# downstream skill (uag_bridge.py -> game-designer -> unreal-world-builder)
# will turn into real scene/prop names. So every build_level()/
# build_arena_finale() call runs its OWN generated text through
# TrustRuntime.evaluate() before returning, not just at final placement
# time. This is mandatory, not opt-in -- there is no bypass flag,
# deliberately, matching the "default-deny, no silent escalation"
# philosophy the rest of compliance/ already follows.
# ---------------------------------------------------------------------------

_default_trust_runtime: TrustRuntime | None = None


def _get_default_trust_runtime() -> TrustRuntime:
    """Lazily build ONE shared TrustRuntime (extended watchlist, so
    Cyrillic/native-script aliases are covered too) the first time a
    preset needs to compliance-check its own text and no caller-supplied
    instance was given. Cached at module level so repeated preset builds
    share one audit trail instead of spawning a fresh log file per call --
    mirrors how mcp_server.py builds its own `_trust` once at import
    time. Callers that already have a TrustRuntime (e.g. mcp_server.py's
    `_trust`) should pass it in via the `trust_runtime=` parameter instead,
    so the whole app shares a single audit log."""
    global _default_trust_runtime
    if _default_trust_runtime is None:
        _default_trust_runtime = TrustRuntime.with_extended_watchlist()
    return _default_trust_runtime


def _collect_doc_text(doc: dict[str, Any]) -> str:
    """Every free-text field in a built level document that could carry a
    prompt- or source-controlled string -- title, tagline(s),
    narrative_intro, and every level/achievement's title/description/
    source_metric. Deliberately broad: the cost of scanning one extra
    static field is nothing; the cost of missing the one field that
    actually carries the injected text is a compliance gap."""
    parts: list[str] = []
    for key in ("title", "tagline", "preset_tagline", "narrative_intro", "difficulty_note"):
        val = doc.get(key)
        if isinstance(val, str):
            parts.append(val)
    for lvl in doc.get("levels", []):
        parts.append(str(lvl.get("title", "")))
        parts.append(str(lvl.get("description", "")))
    for ach in doc.get("achievements", []):
        parts.append(str(ach.get("title", "")))
        parts.append(str(ach.get("description", "")))
        parts.append(str(ach.get("source_metric", "")))
    return " | ".join(p for p in parts if p)


def _compliance_check(doc: dict[str, Any], *, context_label: str, trust_runtime: TrustRuntime | None) -> None:
    """Run a built level document's own generated text through the SAME
    default-deny gate as run_toolbelt_tool/execute_python. Mutates `doc`
    in place on an ALLOWED-with-conditions decision (attaches
    `licensing_conditions`/`licensed_ip_matches` so a real royalty/
    template-only/no-mixing obligation surfaces to the caller instead of
    silently disappearing) and raises PresetContentBlockedError on a
    BLOCKED decision -- never returns a level whose own text references
    an unlicensed universe/character/item.
    """
    trust = trust_runtime or _get_default_trust_runtime()
    text = _collect_doc_text(doc)
    if not text:
        return
    decision = trust.evaluate(f"qfoldit_preset:{context_label}", {"generated_text": text})
    if not decision.allowed:
        raise PresetContentBlockedError(
            f"Preset '{context_label}' was not built: its own generated text "
            f"matched watchlisted term(s) {decision.matched_terms} with no covering "
            f"license_manifest.json entry. {decision.reason} If this is a genuinely "
            f"licensed brand, add a real manifest entry rather than routing around "
            f"this check; otherwise remove the reference (e.g. rephrase the title "
            f"override) and rebuild."
        )
    if decision.matched_terms:
        doc["licensed_ip_matches"] = decision.matched_terms
        doc["licensing_conditions"] = decision.conditions


def _build_metric_level(
    source: dict[str, Any],
    *,
    title: str,
    tagline: str,
    difficulty: Difficulty,
    metrics: list[MetricSpec],
    list_metric: tuple[str, str] | None = None,
    p_value_metric: tuple[str, str, float] | None = None,
) -> dict[str, Any]:
    """
    Shared, deterministic single-level builder for the six "domain_metrics"
    presets (hp_lattice_challenge, plant_growth_garden,
    oilgas_corrosion_watch, meor_recovery_run, mining_bioleach_challenge,
    prospecting_survey). Reads whichever of `metrics` are actually present
    in `source` -- never fabricates a missing one. The star/par thresholds
    below are gameplay calibration (same spirit as gamedesign.py's own
    _DIFFICULTY_PAR_TIGHTNESS), not a scientific claim about the metric.
    """
    tightness = _DIFFICULTY_PAR_TIGHTNESS[difficulty]
    seed = _seed_from_source(source)

    levels: list[dict[str, Any]] = []
    headline = next((m for m in metrics if m.key in source and source[m.key] is not None), None)
    if headline is not None:
        value = float(source[headline.key])
        if headline.higher_is_better:
            # Gameplay-only calibration: treat the value as already a 0-100
            # percentage if it looks like one, else clamp to a 0-1 ratio.
            ratio = (value / 100.0) if 0.0 <= value <= 100.0 else min(abs(value), 1.0)
            stars = 3 if ratio >= 0.75 * tightness else 2 if ratio >= 0.45 * tightness else 1
            par = round(value, 4)
        else:
            par = round(abs(value) * tightness, 4) if value else 1.0
            stars = _stars_from_margin(abs(value), max(par, 1e-6), tightness)
        levels.append({
            "level_number": 1,
            "title": f"{title}: {headline.label}",
            "description": (
                f"Reported {headline.label.lower()} = {value:g}{headline.unit}."
            ),
            "par_score": par,
            "checkpoint_energy": round(value, 4),
            "stars": stars,
        })

    achievements: list[dict[str, Any]] = []
    for m in metrics:
        if m.key not in source or source[m.key] is None:
            continue
        val = source[m.key]
        achievements.append({
            "id": m.key,
            "title": m.label,
            "description": f"Cleared '{m.label}' using the reported {m.key}={val!r}.",
            "unlocked": True,
            "source_metric": f"{m.key}={val!r}",
        })

    if list_metric is not None:
        lm_key, lm_label = list_metric
        if lm_key in source and isinstance(source[lm_key], list):
            achievements.append({
                "id": lm_key,
                "title": lm_label,
                "description": f"Cleared '{lm_label}': {lm_key} reported as an empty list.",
                "unlocked": len(source[lm_key]) == 0,
                "source_metric": f"{lm_key}={source[lm_key]!r}",
            })

    if p_value_metric is not None:
        pv_key, pv_label, threshold = p_value_metric
        if pv_key in source and source[pv_key] is not None:
            p_val = float(source[pv_key])
            achievements.append({
                "id": pv_key,
                "title": pv_label,
                "description": f"Cleared '{pv_label}': reported {pv_key}={p_val:.4g} against threshold {threshold}.",
                "unlocked": p_val < threshold,
                "source_metric": f"{pv_key}={p_val:.4g}, threshold={threshold}",
            })

    total_score = sum(lvl["stars"] for lvl in levels) + sum(1 for a in achievements if a["unlocked"])
    source_kind = "domain_metrics" if (levels or achievements) else "unknown"

    return {
        "title": title,
        "tagline": tagline,
        "difficulty": difficulty,
        "seed": seed,
        "levels": levels,
        "achievements": achievements,
        "narrative_intro": (
            f"{tagline} This run is uniquely identified as seed #{seed} -- replaying the same "
            "source result always regenerates the same level."
        ),
        "total_score": total_score,
        "source_kind": source_kind,
    }


def list_presets(registry: ScienceMCPRegistry | None = None) -> list[dict[str, Any]]:
    """Every one of the ten registered presets, plus a live reachability
    check for its reference_mcp, so a caller can see *before* building a
    level whether the canonical MCP backing it is actually connectable
    this session. Does not include the arena finale -- see
    describe_arena_finale() for that."""
    registry = registry or ScienceMCPRegistry()
    out: list[dict[str, Any]] = []
    for preset in PRESETS.values():
        d = asdict(preset)
        d["reference"] = _reference_note(preset, registry)
        out.append(d)
    return out


def describe_arena_finale(registry: ScienceMCPRegistry | None = None) -> dict[str, Any]:
    """Describe the arena finale mechanism (not one of the ten presets)."""
    registry = registry or ScienceMCPRegistry()
    d = asdict(_ARENA_PRESET)
    d["reference"] = _reference_note(_ARENA_PRESET, registry)
    return d


def get_preset(key: str) -> LevelPreset:
    try:
        return PRESETS[key]
    except KeyError:
        raise PresetNotFoundError(
            f"Unknown preset '{key}'. Known presets: {sorted(PRESETS)}. "
            f"(The arena finale is '{_ARENA_KEY}', built separately via build_arena_finale().)"
        ) from None


def build_level(
    key: str,
    source: dict[str, Any] | None = None,
    *,
    title: str | None = None,
    difficulty: Difficulty | None = None,
    registry: ScienceMCPRegistry | None = None,
    trust_runtime: TrustRuntime | None = None,
) -> dict[str, Any]:
    """
    Build one named preset level (one of the ten in PRESETS) from a real
    science result.

    Args:
        key: a PRESETS key (see list_presets()).
        source: the raw result dict a real pipeline/skill already
            produced. Always required -- never fabricated here.
        title: overrides the preset's default title. Presets are levels
            ASSEMBLED FROM PROMPTS -- this override is exactly the kind
            of free text compliance/trust_runtime.py exists to check, so
            it (and every other generated text field) is scanned before
            this function returns; see PresetContentBlockedError.
        difficulty: overrides the preset's default difficulty.
        registry: inject a ScienceMCPRegistry (mainly for tests); a
            fresh default one is used otherwise so reachability is
            always checked live.
        trust_runtime: inject a TrustRuntime (e.g. mcp_server.py's own
            shared `_trust` instance, so the whole app logs to one audit
            trail); a lazily-created shared default is used otherwise.

    Returns:
        The underlying gamedesign document (or domain-metrics document)
        dict, with `preset_key`, `preset_tagline`, and `reference` (this
        preset's canonical-MCP reachability snapshot) added. If the
        generated text matched a LICENSED brand (e.g. a manifest entry
        with a royalty_pct), `licensed_ip_matches` and
        `licensing_conditions` are attached too -- surfaced, never
        silently dropped.

    Raises:
        PresetNotFoundError: unknown key.
        PresetSourceRequiredError: source is None.
        PresetContentBlockedError: the built level's own text matched a
            watchlisted term with no covering manifest entry.
    """
    preset = get_preset(key)
    registry = registry or ScienceMCPRegistry()
    reference = _reference_note(preset, registry)
    effective_difficulty = difficulty or preset.difficulty
    effective_title = title or preset.title

    if source is None:
        raise PresetSourceRequiredError(
            f"Preset '{key}' expects a real '{preset.expects_source_kind}' result -- "
            "presets.py never fabricates one. "
            f"See PRESETS['{key}'].notes for the exact expected shape."
        )

    if preset.metrics is not None:
        doc = _build_metric_level(
            source,
            title=effective_title,
            tagline=preset.tagline,
            difficulty=effective_difficulty,
            metrics=preset.metrics,
            list_metric=preset.list_metric,
            p_value_metric=preset.p_value_metric,
        )
    else:
        doc = generate_game_design(source, title=effective_title, difficulty=effective_difficulty)

    doc["preset_key"] = preset.key
    doc["preset_tagline"] = preset.tagline
    doc["reference"] = reference
    _compliance_check(doc, context_label=key, trust_runtime=trust_runtime)
    return doc


def build_arena_finale(
    source: dict[str, Any] | None = None,
    *,
    title: str | None = None,
    registry: ScienceMCPRegistry | None = None,
    round_duration_seconds: int = 300,
    team_count: int = 2,
    trust_runtime: TrustRuntime | None = None,
) -> dict[str, Any]:
    """
    Build the arena finale -- a round-based multiplayer challenge, not
    one of the ten domain presets (see module docstring). `source` is
    optional: an empty/partial one just means
    generate_multiplayer_challenge() reports objective=None rather than a
    fabricated one (see its own docstring). Same compliance gate as
    build_level() -- `title` and any source-derived text are scanned
    before this function returns; see PresetContentBlockedError.
    """
    registry = registry or ScienceMCPRegistry()
    reference = _reference_note(_ARENA_PRESET, registry)
    challenge = generate_multiplayer_challenge(
        source or {},
        round_duration_seconds=round_duration_seconds,
        team_count=team_count,
    )
    challenge["title"] = title or _ARENA_PRESET.title
    challenge["preset_key"] = _ARENA_PRESET.key
    challenge["preset_tagline"] = _ARENA_PRESET.tagline
    challenge["reference"] = reference
    _compliance_check(challenge, context_label=_ARENA_KEY, trust_runtime=trust_runtime)
    return challenge


def build_universal_level(
    sources: dict[str, dict[str, Any] | None],
    *,
    registry: ScienceMCPRegistry | None = None,
    include_arena_finale: bool = True,
    round_duration_seconds: int = 300,
    team_count: int = 2,
    trust_runtime: TrustRuntime | None = None,
) -> dict[str, Any]:
    """
    Build the "level uniting all presets": every one of the ten presets
    present (non-None) in `sources` is built and stitched into one
    sequential Universal Level; the arena finale, if included, is kept
    as a separate closing round rather than mixed into the level
    sequence (a live multiplayer round isn't a "level" in the same sense
    as the single-player ones).

    Args:
        sources: {preset_key: source_dict_or_None}, keys from PRESETS
            (plus, optionally, "arena_showdown" whose value is merged
            into the finale's combined objective-source). A
            missing/None preset is skipped (segments[...]['included'] is
            False) -- never fabricated.
        registry: inject a ScienceMCPRegistry (mainly for tests).
        include_arena_finale: whether to append the arena finale as a
            closing segment.
        round_duration_seconds, team_count: passed to the arena finale.
        trust_runtime: inject a TrustRuntime, forwarded to every
            build_level()/build_arena_finale() call this makes so the
            whole Universal Level shares one compliance audit trail.
            Same default-deny gate as those two -- see
            PresetContentBlockedError.

    Returns:
        A dict with: title, tagline, universal_seed (sha256 of the
        sorted per-segment seeds -- deterministic given the same
        sources), levels (renumbered, retitled with a "[domain]"
        prefix), achievements (id-namespaced per preset), total_score,
        arena_finale (or None), and segments (a manifest of every one of
        the ten presets considered, included or not, each with its own
        reference-MCP reachability snapshot, plus the arena finale
        segment if included).

    Raises:
        PresetContentBlockedError: any included preset's (or the arena
            finale's) own generated text matched a watchlisted term with
            no covering manifest entry -- propagated as-is from
            build_level()/build_arena_finale() rather than caught and
            silently dropping just that one segment, since a level built
            from a partially-blocked run is not a level you should ship.
    """
    registry = registry or ScienceMCPRegistry()
    segments: list[dict[str, Any]] = []
    all_levels: list[dict[str, Any]] = []
    all_achievements: list[dict[str, Any]] = []
    total_score = 0
    seeds: list[str] = []
    next_level_number = 1

    for key, preset in PRESETS.items():
        source = sources.get(key)
        if source is None:
            segments.append({
                "preset_key": key,
                "title": preset.title,
                "domain": preset.domain,
                "included": False,
                "reason": "no source supplied for this preset",
                "reference": _reference_note(preset, registry),
            })
            continue

        doc = build_level(key, source, registry=registry, trust_runtime=trust_runtime)
        seeds.append(doc["seed"])

        renumbered: list[dict[str, Any]] = []
        for lvl in doc["levels"]:
            lvl = dict(lvl)
            lvl["level_number"] = next_level_number
            lvl["title"] = f"[{preset.domain}] {lvl['title']}"
            renumbered.append(lvl)
            next_level_number += 1
        all_levels.extend(renumbered)

        for ach in doc["achievements"]:
            ach = dict(ach)
            ach["id"] = f"{key}:{ach['id']}"
            all_achievements.append(ach)

        total_score += doc["total_score"]
        segments.append({
            "preset_key": key,
            "title": preset.title,
            "domain": preset.domain,
            "included": True,
            "level_range": (
                [renumbered[0]["level_number"], renumbered[-1]["level_number"]]
                if renumbered else None
            ),
            "seed": doc["seed"],
            "reference": doc["reference"],
        })

    arena_finale: dict[str, Any] | None = None
    if include_arena_finale:
        combined_source: dict[str, Any] = {}
        for k, s in sources.items():
            if s:
                combined_source.update(s)
        arena_finale = build_arena_finale(
            combined_source,
            registry=registry,
            round_duration_seconds=round_duration_seconds,
            team_count=team_count,
            trust_runtime=trust_runtime,
        )
        seeds.append(arena_finale["seed"])
        segments.append({
            "preset_key": _ARENA_KEY,
            "title": _ARENA_PRESET.title,
            "domain": _ARENA_PRESET.domain,
            "included": True,
            "level_range": None,
            "seed": arena_finale["seed"],
            "reference": arena_finale["reference"],
        })

    universal_seed = hashlib.sha256("|".join(sorted(seeds)).encode("utf-8")).hexdigest()[:12]

    return {
        "title": "qFoldIT: Universal Level",
        "tagline": "All ten qFoldIT science domains gamified, stitched into one continuous playthrough.",
        "difficulty_note": (
            "each included segment keeps its own preset difficulty "
            "(see segments[*].preset_key -> PRESETS[...].difficulty); "
            "there is no single combined difficulty knob"
        ),
        "universal_seed": universal_seed,
        "levels": all_levels,
        "achievements": all_achievements,
        "total_score": total_score,
        "arena_finale": arena_finale,
        "segments": segments,
    }
