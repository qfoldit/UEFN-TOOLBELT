"""
UEFN TOOLBELT — mcp_server.py
=========================================
External FastMCP bridge that connects Claude Code to the UEFN editor.

This is the *outside-UEFN* side of the two-process MCP architecture:

    Claude Code  ←── stdio ──→  mcp_server.py (this file, external)
                                       │
                                  HTTP POST 127.0.0.1:8765
                                       │
                             UEFN editor process
                             └── Content/Python/UEFN_Toolbelt/tools/mcp_bridge.py

Requirements:
    pip install mcp
    (Uses the standard 'mcp' package from Anthropic — same as Claude Code MCP ecosystem)

One-time setup:
    pip install mcp
    # Place this file anywhere accessible (project root is fine)

Claude Code config — add to .mcp.json in your project root:
    {
      "mcpServers": {
        "uefn-toolbelt": {
          "command": "python",
          "args": ["<ABSOLUTE_PATH_TO_THIS_FILE>"]
        }
      }
    }

Then in UEFN (Output Log or Toolbelt dashboard):
    import UEFN_Toolbelt as tb; tb.run("mcp_start")

After that, Claude Code has full control over UEFN — 358 tools, live actor data,
arbitrary Python execution, viewport control, and more.

What this exposes (beyond Kirch's original 22 tools):
    run_toolbelt_tool   — call any of the 358 registered toolbelt tools by name
    list_toolbelt_tools — list every available tool with category and description
    mcp_get_log         — read the last N lines of the MCP listener log ring

qFoldIT Trust & Compliance integration (2026-08):
    run_toolbelt_tool and execute_python are now gated by qfoldit_trust_runtime
    before anything reaches the UEFN editor — default-deny on watchlisted
    brand/IP terms unless a real, sourced license_manifest.json entry (or an
    Epic-owned content namespace reference) covers them. See README.md /
    INTEGRATION.md in this repo for the full design and its known limits.
        qfoldit_check_license        — look up documented terms for a brand/IP
        qfoldit_list_licensed_brands — list everything currently covered
        qfoldit_connect_science_mcp  — gate connecting a scientific MCP server
        qfoldit_evaluate_commission  — gate a paid off-platform commission

Author: Ocean Bennett
qFoldIT integration merged with the original author now on the team.
License: AGPL-3.0 with visible attribution requirement (see LICENSE)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from qfoldit.compliance.trust_runtime import TrustRuntime
from qfoldit.science.mcp_registry import ScienceMCPRegistry
from qfoldit.monetization.monetization_registry import MonetizationRegistry
from qfoldit.science.pipelines.quantum_runner import simulate_quantum_walk_fold, predict_peptide_quantum_vqe
from qfoldit.science.gamedesign import generate_game_design
from qfoldit.science.uag_bridge import to_uag_seed, validate_uag_seed
from qfoldit.science.presets import (
    list_presets as _list_level_presets,
    describe_arena_finale as _describe_arena_finale,
    build_level as _build_level_preset,
    build_arena_finale as _build_arena_finale,
    build_universal_level as _build_universal_level,
)
from qfoldit.science.exceptions import PresetError
from qfoldit.science.experiment_record import build_experiment_record, list_experiment_records

# ─── Configuration ────────────────────────────────────────────────────────────

try:
    LISTENER_PORT = int(os.environ.get("UEFN_MCP_PORT", "8765"))
    if not (1 <= LISTENER_PORT <= 65535):
        raise ValueError(f"Port {LISTENER_PORT} out of range")
except ValueError:
    LISTENER_PORT = 8765
LISTENER_URL    = f"http://127.0.0.1:{LISTENER_PORT}"
VERSE_BOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "verse-book", "docs")

# Chapter topic → filename map for verse_book_chapter()
_VERSE_CHAPTERS: dict[str, str] = {
    "overview":       "00_overview.md",
    "expressions":    "01_expressions.md",
    "primitives":     "02_primitives.md",
    "types":          "02_primitives.md",
    "containers":     "03_containers.md",
    "arrays":         "03_containers.md",
    "maps":           "03_containers.md",
    "operators":      "04_operators.md",
    "mutability":     "05_mutability.md",
    "var":            "05_mutability.md",
    "functions":      "06_functions.md",
    "control":        "07_control.md",
    "if":             "07_control.md",
    "for":            "07_control.md",
    "failure":        "08_failure.md",
    "failable":       "08_failure.md",
    "decides":        "08_failure.md",
    "structs":        "09_structs_enums.md",
    "enums":          "09_structs_enums.md",
    "classes":        "10_classes_interfaces.md",
    "interfaces":     "10_classes_interfaces.md",
    "inheritance":    "10_classes_interfaces.md",
    "subtyping":      "11_types.md",
    "access":         "12_access.md",
    "public":         "12_access.md",
    "private":        "12_access.md",
    "effects":        "13_effects.md",
    "specifiers":     "13_effects.md",
    "computes":       "13_effects.md",
    "suspends":       "13_effects.md",
    "concurrency":    "14_concurrency.md",
    "async":          "14_concurrency.md",
    "spawn":          "14_concurrency.md",
    "race":           "14_concurrency.md",
    "sync":           "14_concurrency.md",
    "live_variables": "15_live_variables.md",
    "listenable":     "15_live_variables.md",
    "modules":        "16_modules.md",
    "using":          "16_modules.md",
    "persistable":    "17_persistable.md",
    "evolution":      "18_evolution.md",
    "syntax":         "VerseSyntaxValidation.md",
    "index":          "concept_index.md",
}
REQUEST_TIMEOUT        = 30.0
LONG_OPERATION_TIMEOUT = 120.0   # for tool runs that may take longer

# ─── HTTP client ──────────────────────────────────────────────────────────────


def _send(command: str, params: dict | None = None,
          timeout: float = REQUEST_TIMEOUT) -> dict:
    """
    Send a command to the UEFN listener and return the result dict.

    Raises:
        ConnectionError: Listener is not running or UEFN isn't open.
        RuntimeError:    Command failed inside UEFN.
        TimeoutError:    UEFN took too long to respond.
    """
    payload = json.dumps({"command": command, "params": params or {}}).encode()
    req = urllib.request.Request(
        LISTENER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        if "Connection refused" in str(e) or "No connection" in str(e):
            raise ConnectionError(
                "UEFN listener is not running.\n"
                "  Start it: In UEFN Output Log or Toolbelt dashboard → MCP: Start Listener\n"
                "  Or:       import UEFN_Toolbelt as tb; tb.run('mcp_start')"
            ) from e
        raise
    except Exception as e:
        if "timed out" in str(e).lower():
            raise TimeoutError(
                f"Command '{command}' timed out after {timeout}s.\n"
                "  The UEFN editor may be blocked. Try a shorter operation."
            ) from e
        raise

    if not body.get("success", False):
        err = body.get("error", "Unknown error")
        tb  = body.get("traceback", "")
        raise RuntimeError(f"UEFN error for '{command}': {err}\n{tb}".strip())

    return body.get("result", {})


def _j(obj: Any) -> str:
    """Pretty-print any object as JSON string."""
    return json.dumps(obj, indent=2)


# ─── qFoldIT Trust & Compliance Runtime ────────────────────────────────────────
# Everything qFoldIT-related now lives under qfoldit/ (compliance/, science/,
# monetization/) instead of loose files at the repo root — see qfoldit/README.md.

_TOOLBELT_ROOT = os.path.dirname(os.path.abspath(__file__))
_QFOLDIT_DIR = os.path.join(_TOOLBELT_ROOT, "qfoldit")
_QFOLDIT_LOGS_DIR = os.path.join(_QFOLDIT_DIR, "logs")
os.makedirs(_QFOLDIT_LOGS_DIR, exist_ok=True)
_QFOLDIT_EXPERIMENT_RECORDS_PATH = os.path.join(_QFOLDIT_LOGS_DIR, "experiment_records.log.jsonl")


def _detect_engine_version() -> str:
    """Best-effort read of the current engine version from the live UEFN
    listener (so manifest staleness checks track the real editor, not a
    hardcoded config value). Falls back to QFOLDIT_ENGINE_VERSION env var,
    then to 'UE5' — never raises, since this runs at import time before
    the listener may even be up yet."""
    try:
        result = _send("ping")
        for key in ("engine_version", "unreal_version", "ue_version"):
            if result.get(key):
                v = str(result[key])
                return "UE6" if v.startswith("6") else "UE5" if v.startswith("5") else v
    except Exception:
        pass
    return os.environ.get("QFOLDIT_ENGINE_VERSION", "UE5")


def _qfoldit_asset_metadata_fn(asset_ref: str) -> dict | None:
    """Resolve a candidate content path through the LIVE editor's own Asset
    Registry — the same local IPC channel (_send) every other tool in this
    file already uses, not a network call. Returns real provenance data or
    None if the ref doesn't resolve to an actual asset.

    plugin_id is derived from the asset's real package_path mount point
    (e.g. '/LegoBrandContent/...' -> 'LegoBrandContent', '/Game/...' ->
    'Game') since that's what the engine can actually tell us today via
    get_asset_info/does_asset_exist. This is a real signal — brand template
    plugins mount their content under their own root, distinct from your
    project's /Game/ — but it is only as good as what license_manifest.json's
    content_plugin_ids actually documents per brand. Fill those in from a
    real Content Browser inspection before relying on plugin_id matches;
    until then, TrustRuntime falls back to the namespace-prefix check.
    """
    try:
        result = _send("get_asset_info", {"asset_path": asset_ref}, timeout=5)
    except Exception:
        return None
    asset = (result or {}).get("asset")
    if not asset:
        return None
    package_path = asset.get("package_path") or asset.get("object_path") or asset_ref
    mount = package_path.strip("/").split("/", 1)[0] if package_path else ""
    return {"resolved_path": package_path, "plugin_id": mount}


_trust = TrustRuntime.with_extended_watchlist(
    manifest_path=os.path.join(_QFOLDIT_DIR, "compliance", "license_manifest.json"),
    engine_version=_detect_engine_version(),
    audit_log_path=os.path.join(_QFOLDIT_LOGS_DIR, "trust_audit.log.jsonl"),
    asset_metadata_fn=_qfoldit_asset_metadata_fn,
)
_sci_registry = ScienceMCPRegistry(
    registry_path=os.path.join(_QFOLDIT_DIR, "science", "science_mcp_registry.json"),
    connection_log_path=os.path.join(_QFOLDIT_LOGS_DIR, "science_mcp_connections.log.jsonl"),
)
_mon_registry = MonetizationRegistry(
    channels_path=os.path.join(_QFOLDIT_DIR, "monetization", "monetization_channels.json"),
    commission_log_path=os.path.join(_QFOLDIT_LOGS_DIR, "commission_ledger.log.jsonl"),
    trust=_trust,
)


# ─── FastMCP server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    "uefn-toolbelt",
    instructions=(
        "MCP server for the UEFN Toolbelt — the most comprehensive Python toolbelt "
        "for Unreal Editor for Fortnite (UEFN 40.00+, March 2026).\n\n"
        "IMPORTANT: Start the listener in UEFN first:\n"
        "  import UEFN_Toolbelt as tb; tb.run('mcp_start')\n\n"
        "Key tools:\n"
        "  run_toolbelt_tool   — run ANY of the 358 registered toolbelt tools\n"
        "  execute_python      — run arbitrary Python inside UEFN with full unreal.*\n"
        "  list_toolbelt_tools — see every tool available\n"
        "  get_all_actors      — snapshot the level\n"
        "  get_selected_actors — what the user has selected right now\n\n"
        "Verse code generation (spec-accurate):\n"
        "  verse_book_search   — search the authoritative Verse spec by keyword\n"
        "  verse_book_chapter  — fetch a full spec chapter by topic\n"
        "  verse_book_update   — git pull the latest spec from upstream\n\n"
        "IMPORTANT for Verse codegen: always call verse_book_search or verse_book_chapter\n"
        "BEFORE writing Verse code to ensure syntax is spec-accurate.\n\n"
        "The execute_python tool pre-populates: unreal, actor_sub, asset_sub, level_sub, tb."
    ),
)

# ─── System ───────────────────────────────────────────────────────────────────


@mcp.tool()
def ping() -> str:
    """Check if the UEFN Toolbelt listener is running and get its status."""
    return _j(_send("ping"))


@mcp.tool()
def execute_python(code: str) -> str:
    """Execute arbitrary Python inside the UEFN editor on the main thread.

    Pre-populated globals:
        unreal      — the full unreal Python module (37K+ types)
        actor_sub   — EditorActorSubsystem
        asset_sub   — EditorAssetSubsystem
        level_sub   — LevelEditorSubsystem
        tb          — UEFN_Toolbelt package (tb.run('tool_name', **kwargs))

    Assign to `result` to return a value. Use print() for stdout.

    Examples:
        # Get world name
        result = unreal.EditorLevelLibrary.get_editor_world().get_name()

        # Count actors by class
        actors = actor_sub.get_all_level_actors()
        from collections import Counter
        result = dict(Counter(a.get_class().get_name() for a in actors))

        # Run a toolbelt tool programmatically
        tb.run('material_apply_preset', preset='chrome')
    """
    decision = _trust.evaluate(tool_name="execute_python", kwargs={"code": code})
    if not decision.allowed:
        return _trust.deny_response(decision)

    result = _send("execute_python", {"code": code}, timeout=LONG_OPERATION_TIMEOUT)
    parts = []
    note = _trust.allow_response_note(decision)
    if note:
        parts.append(note)
    if result.get("stdout"):
        parts.append(f"stdout:\n{result['stdout'].rstrip()}")
    if result.get("stderr"):
        parts.append(f"stderr:\n{result['stderr'].rstrip()}")
    if result.get("result") is not None:
        parts.append(f"result: {_j(result['result'])}")
    return "\n\n".join(parts) if parts else "(no output)"


@mcp.tool()
def mcp_get_log(last_n: int = 50) -> str:
    """Get the last N lines from the MCP listener's internal log ring."""
    result = _send("get_log", {"last_n": last_n})
    lines = result.get("lines", [])
    return "\n".join(lines) if lines else "(log is empty)"


# ─── qFoldIT Trust & Compliance ─────────────────────────────────────────────


@mcp.tool()
def qfoldit_check_license(term: str) -> str:
    """Look up what's actually documented for a brand/IP term before you
    build with it — e.g. qfoldit_check_license("lego") shows the real
    royalty %, template-only restriction, and source link from Epic's
    Brand Rules. Returns 'no manifest entry' for anything not licensed
    (Marvel, DC, Rick and Morty, etc.) — that means it stays blocked in
    execute_python / run_toolbelt_tool regardless of how it's phrased.
    """
    return _trust.describe(term)


@mcp.tool()
def qfoldit_list_licensed_brands() -> str:
    """List every brand currently covered by a real license_manifest.json
    entry, with rightsholder and license_type. Anything not on this list
    has no general creator license and is blocked by default."""
    lines = []
    for term, entry in _trust.manifest.items():
        lines.append(f"{term}: {entry.rightsholder} ({entry.license_type})")
    return "\n".join(lines) if lines else "(manifest is empty — everything watchlisted is blocked)"


@mcp.tool()
def qfoldit_connect_science_mcp(name: str, allow_best_effort: bool = False) -> str:
    """Check/record whether a scientific MCP server (protein design, Boltz,
    engine bridges, etc.) is safe to connect right now. 'verified' and
    'connected' servers pass immediately; 'best_effort' community bridges
    need allow_best_effort=True; 'reference_only' entries never connect
    (there's nothing live to reach)."""
    ok, reason = _sci_registry.can_connect(name, allow_best_effort=allow_best_effort)
    _sci_registry._log_connection(name, ok, reason)
    return json.dumps({"server": name, "connectable": ok, "reason": reason}, indent=2)


@mcp.tool()
def qfoldit_evaluate_commission(
    task_description: str,
    task_type: str = "other",
    sequence_length: int | None = None,
    num_samples: int = 1,
) -> str:
    """Gate a paid off-platform commission (L-system, drug-design,
    molecular/atomic structure, etc.) BEFORE accepting payment. Runs the
    same IP watchlist/manifest check used for UEFN calls, and flags if
    fulfilling it needs a metered paid backend (e.g. Boltz) so pricing can
    account for real pass-through cost.

    Pass sequence_length (residue count) for protein/drug-design commissions
    to get a local, offline compute estimate from boltz_pricing.json. The
    dollar figure is None until rate_usd_per_gpu_second is filled in there
    from your real Modal billing — this never invents a price."""
    d = _mon_registry.evaluate_commission(
        task_description, task_type=task_type,
        sequence_length=sequence_length, num_samples=num_samples,
    )
    return json.dumps({
        "accepted": d.accepted,
        "reason": d.reason,
        "requires_paid_backend": d.requires_paid_backend,
        "backend_used": d.backend_used,
        "cost_estimate": {
            "estimated_seconds": d.cost_estimate.estimated_seconds,
            "estimated_cost_usd": d.cost_estimate.estimated_cost_usd,
            "gpu_type": d.cost_estimate.gpu_type,
            "calibrated_from_real_runs": d.cost_estimate.calibrated_from_real_runs,
            "note": d.cost_estimate.note,
        } if d.cost_estimate else None,
    }, indent=2)


@mcp.tool()
def qfoldit_quantum_walk_fold(
    sequence: str,
    steps: int = 500,
    continuous_space: bool = True,
    seed: int | None = None,
) -> str:
    """Run a real, classical quantum-walk-INSPIRED Metropolis simulation over
    (phi, psi) torsion angles and return a genuine 3D backbone coordinate
    tensor for a peptide sequence — for in-editor structural previews (e.g.
    driving a facility-twin or level layout from a real folding trajectory).

    HONESTY NOTE (read before treating this as "real quantum folding"): this
    is a CLASSICAL simulation inspired by the QFold algorithm (Casares et
    al., Quantum Sci. Technol. 7, 025013, 2022) — a biased random-walk
    proposal distribution feeding a real Metropolis acceptance step and a
    real NeRF backbone reconstruction. It does not run on a quantum circuit
    simulator or quantum hardware. Treat the output as a lightweight
    structural preview, not a substitute for actual QFold/IBMQ runs or
    physical force-field refinement. For the real CVaR-VQE quantum backend
    (requires the separate qupepfold/Qiskit stack), use
    qfoldit_quantum_vqe_fold instead — it honestly reports 'unavailable'
    rather than silently falling back to this classical approximation."""
    ip_decision = _trust.evaluate(tool_name="qfoldit_quantum_walk_fold", kwargs={"sequence": sequence})
    if not ip_decision.allowed:
        return json.dumps({"status": "blocked", "reason": ip_decision.reason}, indent=2)

    async def _run():
        return await simulate_quantum_walk_fold(sequence, steps=steps, continuous_space=continuous_space, seed=seed)
    result = asyncio.run(_run())
    return json.dumps(result, indent=2)


@mcp.tool()
def qfoldit_quantum_vqe_fold(sequence: str, alpha: float = 0.1, shots: int = 1024) -> str:
    """Estimate a low-energy peptide conformation using QuPepFold's real
    CVaR-optimized Variational Quantum Eigensolver (Uttarkar et al., PLOS
    ONE, 2026). This is the genuine quantum backend — but it requires the
    separate 'qupepfold' package (Qiskit/Braket-dependent) that this
    toolbelt's default Python environment does not ship. If unavailable,
    returns status='unavailable' with an install_hint — NEVER a fabricated
    energy value. Sequence should be short (~10 residues), the published
    benchmark range for CVaR-VQE reliably reaching the ground state."""
    ip_decision = _trust.evaluate(tool_name="qfoldit_quantum_vqe_fold", kwargs={"sequence": sequence})
    if not ip_decision.allowed:
        return json.dumps({"status": "blocked", "reason": ip_decision.reason}, indent=2)

    async def _run():
        return await predict_peptide_quantum_vqe(sequence, alpha=alpha, shots=shots)
    result = asyncio.run(_run())
    return json.dumps(result, indent=2)


@mcp.tool()
def qfoldit_generate_game_design(source_json: str, title: str | None = None, difficulty: str = "adaptive") -> str:
    """Turn a qFoldIT science result (the JSON output of
    qfoldit_quantum_walk_fold or qfoldit_quantum_vqe_fold, passed as a
    string) into a structured, deterministic game design document — levels,
    a par/scoring system, and achievements, ready to drive VR-lab level
    layout. Same input always produces the same output (sha256-seeded, no
    LLM call) so any level/score can be traced back to the exact number in
    the source result that produced it. Does not itself spawn anything in
    the editor — combine with run_toolbelt_tool for that."""
    try:
        source = json.loads(source_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"source_json is not valid JSON: {e}"}, indent=2)
    doc = generate_game_design(source, title=title, difficulty=difficulty)
    return json.dumps(doc, indent=2)


@mcp.tool()
def qfoldit_gamedesign_to_uag_seed(game_design_json: str) -> str:
    """Bridge qfoldit_generate_game_design's output into a starter UAG
    (Universal Assembly Graph) for the game-designer skill
    (.claude/skills/game-designer/SKILL.md). Takes the JSON string
    produced by qfoldit_generate_game_design and returns a minimal,
    already-valid UAG with one 'group' node per level (par score,
    checkpoint energy, and stars preserved in each node's properties)
    plus a ready-made source_context string. This is a SKELETON, not a
    finished scene — no meshes/lights/interactions are invented here.
    Hand the result to the game-designer skill to design the actual
    scene content for each level group."""
    try:
        doc = json.loads(game_design_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"game_design_json is not valid JSON: {e}"}, indent=2)
    uag = to_uag_seed(doc)
    check = validate_uag_seed(uag)
    return json.dumps({"uag": uag, "validation": check}, indent=2)


@mcp.tool()
def qfoldit_list_level_presets() -> str:
    """List qFoldIT's TEN named LEVEL PRESETS (science/presets.py) —
    themed recipes on top of qfoldit_generate_game_design / a shared
    domain-metrics builder, one per science domain: fold_marathon,
    quantum_boss, quantum_lab, hp_lattice_challenge, safety_gauntlet,
    plant_growth_garden, oilgas_corrosion_watch, meor_recovery_run,
    mining_bioleach_challenge, prospecting_survey. Each entry names its
    expected source shape and its canonical ("reference") MCP server
    from science_mcp_registry.json, plus a LIVE reachability check for
    that server this session. The arena finale (live UEFN multiplayer)
    is NOT one of the ten — see qfoldit_describe_arena_finale. Presets
    never fabricate a science result; see PRESETS[key].notes for what
    each one actually expects."""
    return json.dumps(_list_level_presets(), indent=2)


@mcp.tool()
def qfoldit_describe_arena_finale() -> str:
    """Describe the arena finale (round-based multiplayer, realized in a
    live UEFN session via uefn_toolbelt) — kept separate from the ten
    science-domain presets since it isn't a science domain itself. Build
    it with qfoldit_build_arena_finale, or let
    qfoldit_build_universal_level append it automatically."""
    return json.dumps(_describe_arena_finale(), indent=2)


@mcp.tool()
def qfoldit_build_level_preset(
    preset_key: str,
    source_json: str,
    title: str | None = None,
    difficulty: str | None = None,
) -> str:
    """Build one of the ten named preset levels (see
    qfoldit_list_level_presets) from a real science result. `source_json`
    must be the JSON string a real pipeline/skill already produced (see
    PRESETS[preset_key].notes for the exact expected shape — e.g.
    qfoldit_quantum_walk_fold's output for fold_marathon, or a
    qfoldit-oilgas skill result for oilgas_corrosion_watch). Never
    fabricates a result: an invalid/missing source returns
    status='error' explaining what's expected rather than inventing
    numbers. Returns the underlying level document plus which canonical
    MCP server backs this preset and whether it's reachable right now."""
    try:
        source = json.loads(source_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"source_json is not valid JSON: {e}"}, indent=2)
    try:
        doc = _build_level_preset(preset_key, source, title=title, difficulty=difficulty)
    except PresetError as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)
    return json.dumps(doc, indent=2)


@mcp.tool()
def qfoldit_build_arena_finale(
    source_json: str | None = None,
    title: str | None = None,
    round_duration_seconds: int = 300,
    team_count: int = 2,
) -> str:
    """Build the arena finale — a round-based multiplayer challenge
    (gamedesign.generate_multiplayer_challenge), not one of the ten
    science-domain presets. `source_json` is optional: omit it (or pass
    an empty object) to get a challenge with objective=None rather than
    a fabricated one."""
    source = None
    if source_json is not None:
        try:
            source = json.loads(source_json)
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"source_json is not valid JSON: {e}"}, indent=2)
    doc = _build_arena_finale(
        source, title=title, round_duration_seconds=round_duration_seconds, team_count=team_count,
    )
    return json.dumps(doc, indent=2)


@mcp.tool()
def qfoldit_build_universal_level(
    sources_json: str,
    include_arena_finale: bool = True,
    round_duration_seconds: int = 300,
    team_count: int = 2,
) -> str:
    """Build the "Universal Level" that stitches all TEN qFoldIT level
    presets into one continuous playthrough. `sources_json` must be a
    JSON object mapping preset keys (fold_marathon, quantum_boss,
    quantum_lab, hp_lattice_challenge, safety_gauntlet,
    plant_growth_garden, oilgas_corrosion_watch, meor_recovery_run,
    mining_bioleach_challenge, prospecting_survey) to the real result
    dict each one produced — omit a key (or map it to null) to skip that
    preset rather than fabricate its content; the returned `segments`
    list records exactly which presets were included and which weren't,
    each with its canonical-MCP reachability snapshot, plus the arena
    finale segment if included. Deterministic: the same sources always
    regenerate the same universal_seed."""
    try:
        sources = json.loads(sources_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"sources_json is not valid JSON: {e}"}, indent=2)
    if not isinstance(sources, dict):
        return json.dumps({"status": "error", "error": "sources_json must decode to a JSON object"}, indent=2)
    try:
        doc = _build_universal_level(
            sources,
            include_arena_finale=include_arena_finale,
            round_duration_seconds=round_duration_seconds,
            team_count=team_count,
        )
    except PresetError as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)
    return json.dumps(doc, indent=2)


@mcp.tool()
def qfoldit_scene_build_start() -> str:
    """Return a timestamp marker to scope licensing collection to one
    scene-building sequence. Call this once BEFORE unreal-world-builder
    starts placing objects for a UAG, keep the `since_ts` value it
    returns, then pass that same value as
    `qfoldit_build_experiment_record`'s `auto_collect_licensing_since`
    argument once the scene is finished — this is what lets the
    resulting experiment record prove every object placed during that
    build was checked, not just the science-tool calls."""
    return json.dumps({"since_ts": _trust.now_ts()}, indent=2)


@mcp.tool()
def qfoldit_collect_scene_licensing(since_ts: str | None = None) -> str:
    """Read TrustRuntime's own audit log back out as a JSON array of
    licensing decisions (tool_name/allowed/matched_terms/reason),
    filtered to run_toolbelt_tool calls (the ones that place actual
    scene objects) and optionally to everything at or after `since_ts`
    (get this from qfoldit_scene_build_start). Every entry here is a
    real decision TrustRuntime already made and logged — nothing is
    re-derived or guessed. Feed the result directly into
    qfoldit_build_experiment_record's licensing_decisions_json, or just
    use that tool's auto_collect_licensing_since shortcut instead of
    calling this separately."""
    decisions = _trust.decisions_since(since_ts=since_ts, tool_name="run_toolbelt_tool")
    return json.dumps(decisions, indent=2)


@mcp.tool()
def qfoldit_list_experiment_records(limit: int = 20) -> str:
    """List the most recently built experiment records (from
    qfoldit_build_experiment_record, which persists every record it
    builds to qfoldit/logs/experiment_records.log.jsonl automatically).
    Read-only — same pattern as qfoldit_trust_dashboard. Returns []
    (not an error) if no records have been built yet."""
    records = list_experiment_records(_QFOLDIT_EXPERIMENT_RECORDS_PATH, limit=limit)
    return json.dumps(records, indent=2)


@mcp.tool()
def qfoldit_build_experiment_record(
    science_result_json: str,
    science_source_kind: str,
    reproduce_with_json: str,
    game_design_seed: str | None = None,
    uag_metadata_json: str | None = None,
    licensing_decisions_json: str | None = None,
    auto_collect_licensing_since: str | None = None,
) -> str:
    """Assemble a reproducible, licensing-cleared, publication-honest
    ExperimentRecord from qFoldIT results already produced in this
    session — this is the tool that operationalizes "gameplay as a
    reproducible scientific experiment," now covering every scene
    object's licensing decision, not just science-tool calls. Every
    built record is automatically appended to
    qfoldit/logs/experiment_records.log.jsonl (see
    qfoldit_list_experiment_records) so it survives past this one
    response.

    Args:
        science_result_json: The JSON string output of
            qfoldit_quantum_walk_fold or qfoldit_quantum_vqe_fold.
        science_source_kind: "quantum_walk_fold" or "quantum_vqe" —
            must match which of the two produced science_result_json,
            since this controls which citation/quantum-vs-classical
            disclosure gets attached (see experiment_record.py's
            _METHOD_CITATIONS — an unrecognized kind gets a visible
            placeholder, never a guessed citation).
        reproduce_with_json: JSON object of the exact function name +
            parameters (including any seed) needed to regenerate
            science_result_json byte-for-byte, e.g.
            '{"function": "simulate_quantum_walk_fold", "sequence": "ACDE",
              "steps": 200, "seed": 42}'. Required for the
            publication_checklist's reproducibility check to pass.
        game_design_seed: Optional — the "seed" field from a prior
            qfoldit_generate_game_design call's output.
        uag_metadata_json: Optional — the JSON string of a prior
            qfoldit_gamedesign_to_uag_seed call's uag["metadata"].
        licensing_decisions_json: Optional — JSON array of
            hand-supplied licensing decisions, each shaped like
            {"tool_name": ..., "allowed": ..., "matched_terms": [...],
            "reason": ...}. Merged with anything auto-collected below,
            not replaced by it.
        auto_collect_licensing_since: Optional — a `since_ts` value
            from qfoldit_scene_build_start. When given, this tool
            automatically pulls every run_toolbelt_tool licensing
            decision made since that marker (via
            TrustRuntime.decisions_since) and includes them alongside
            whatever's in licensing_decisions_json — this is what
            proves every game object placed while building the scene
            was checked, without the caller having to copy decisions
            by hand.

    Returns a JSON object with the full record plus a precomputed
    methods_section (citation-grounded prose) and publication_checklist
    (named boolean checks — never a bare "ready"/"not ready" verdict)."""
    try:
        science_result = json.loads(science_result_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"science_result_json is not valid JSON: {e}"}, indent=2)
    try:
        reproduce_with = json.loads(reproduce_with_json)
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"reproduce_with_json is not valid JSON: {e}"}, indent=2)
    uag_metadata = None
    if uag_metadata_json:
        try:
            uag_metadata = json.loads(uag_metadata_json)
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"uag_metadata_json is not valid JSON: {e}"}, indent=2)
    licensing_decisions: list[dict[str, Any]] = []
    if licensing_decisions_json:
        try:
            licensing_decisions.extend(json.loads(licensing_decisions_json))
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"licensing_decisions_json is not valid JSON: {e}"}, indent=2)
    if auto_collect_licensing_since is not None:
        licensing_decisions.extend(
            _trust.decisions_since(since_ts=auto_collect_licensing_since, tool_name="run_toolbelt_tool")
        )

    record = build_experiment_record(
        science_result=science_result,
        science_source_kind=science_source_kind,
        game_design_seed=game_design_seed,
        uag_metadata=uag_metadata,
        licensing_decisions=licensing_decisions or None,
        reproduce_with=reproduce_with,
        persist_path=_QFOLDIT_EXPERIMENT_RECORDS_PATH,
    )
    return json.dumps(record, indent=2)


# ─── Toolbelt bridge (the killer feature) ─────────────────────────────────────


@mcp.tool()
def run_toolbelt_tool(tool_name: str, kwargs: dict | None = None) -> str:
    """Run any registered UEFN Toolbelt tool by name.

    This is the single most powerful MCP tool — it exposes all 358 toolbelt tools
    to Claude Code through one command. Instead of writing custom execute_python
    code, just name the tool and pass its arguments as a dict.

    Args:
        tool_name: Registered tool name (e.g. 'material_apply_preset').
        kwargs:    Dict of keyword arguments for the tool (optional).

    Examples:
        run_toolbelt_tool("material_apply_preset", {"preset": "chrome"})
        run_toolbelt_tool("arena_generate", {"size": "large", "apply_team_colors": True})
        run_toolbelt_tool("scatter_hism", {"count": 200, "radius": 4000.0})
        run_toolbelt_tool("snapshot_save")
        run_toolbelt_tool("tag_add", {"key": "biome", "value": "desert"})
        run_toolbelt_tool("screenshot_focus_selection")
        run_toolbelt_tool("ref_full_report", {"scan_path": "/Game"})

    Use list_toolbelt_tools() first to discover available tool names.
    """
    decision = _trust.evaluate(tool_name=tool_name, kwargs=kwargs or {})
    if not decision.allowed:
        return _trust.deny_response(decision)

    result = _send(
        "run_tool",
        {"tool_name": tool_name, "kwargs": kwargs or {}},
        timeout=LONG_OPERATION_TIMEOUT,
    )
    note = _trust.allow_response_note(decision)
    return (note + "\n\n" + _j(result)) if note else _j(result)


@mcp.tool()
def list_toolbelt_tools(category: str = "") -> str:
    """List all registered UEFN Toolbelt tools.

    Args:
        category: Optional filter (e.g. 'Materials', 'Procedural', 'MCP Bridge').
                  Leave empty to list everything.

    Returns JSON with tool name, category, description, and tags for every tool.
    Pass a name to run_toolbelt_tool() to execute it.
    """
    result = _send("list_tools", {"category": category})
    tools = result.get("tools", [])
    count = result.get("count", len(tools))
    return f"// {count} tools registered\n{_j(tools)}"


@mcp.tool()
def describe_toolbelt_tool(tool_name: str) -> str:
    """Get the full parameter schema for a single UEFN Toolbelt tool.

    Returns the tool's name, description, category, tags, and complete parameter
    signatures (type, required, default) — everything needed to call it correctly
    without loading the full tool manifest.

    Use this before calling run_toolbelt_tool() when you need to verify parameter
    names, types, or defaults for a specific tool.

    Args:
        tool_name: Registered tool name (e.g. 'scatter_hism', 'material_apply_preset').

    Examples:
        describe_toolbelt_tool("scatter_hism")
        describe_toolbelt_tool("verse_gen_game_skeleton")
        describe_toolbelt_tool("snapshot_save")
    """
    result = _send("describe_tool", {"tool_name": tool_name})
    return _j(result)


# ─── Actors ───────────────────────────────────────────────────────────────────


@mcp.tool()
def get_all_actors(class_filter: str = "") -> str:
    """List all actors in the current UEFN level.

    Args:
        class_filter: Optional class name to filter by (e.g. 'StaticMeshActor').
    """
    return _j(_send("get_all_actors", {"class_filter": class_filter}))


@mcp.tool()
def get_selected_actors() -> str:
    """Get the actors currently selected in the UEFN viewport."""
    return _j(_send("get_selected_actors"))


@mcp.tool()
def spawn_actor(
    asset_path: str = "",
    actor_class: str = "",
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
) -> str:
    """Spawn an actor in the current level.

    Provide asset_path OR actor_class (not both).

    Args:
        asset_path:  Content path (e.g. '/Engine/BasicShapes/Cube').
        actor_class: Unreal class name (e.g. 'PointLight', 'CameraActor').
        location:    [x, y, z] world coordinates. Defaults to origin.
        rotation:    [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if asset_path:  params["asset_path"]  = asset_path
    if actor_class: params["actor_class"] = actor_class
    if location:    params["location"]    = location
    if rotation:    params["rotation"]    = rotation
    return _j(_send("spawn_actor", params))


@mcp.tool()
def delete_actors(actor_paths: list[str]) -> str:
    """Delete actors by path name or label.

    Args:
        actor_paths: List of actor path names or labels to delete.
    """
    return _j(_send("delete_actors", {"actor_paths": actor_paths}))


@mcp.tool()
def set_actor_transform(
    actor_path: str,
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
    scale:    Optional[list[float]] = None,
) -> str:
    """Set an actor's transform (any combination of location, rotation, scale).

    Args:
        actor_path: Actor path name or label.
        location:   [x, y, z] world coordinates.
        rotation:   [pitch, yaw, roll] in degrees.
        scale:      [x, y, z] scale factors.
    """
    params: dict[str, Any] = {"actor_path": actor_path}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    if scale:    params["scale"]    = scale
    return _j(_send("set_actor_transform", params))


@mcp.tool()
def set_actor_property(actor_path: str, property_name: str, value: Any) -> str:
    """Set a single editor property on an actor.

    Args:
        actor_path:    Actor path name or label.
        property_name: Property to set (e.g. 'mobility', 'hidden_in_game').
        value:         New value (must be JSON-serializable and match the property type).
    """
    return _j(_send("set_actor_property",
                    {"actor_path": actor_path, "property_name": property_name,
                     "value": value}))


@mcp.tool()
def get_actor_properties(actor_path: str, properties: list[str]) -> str:
    """Read specific editor properties from an actor.

    Args:
        actor_path: Actor path name or label.
        properties: Property names to read (e.g. ['mobility', 'hidden_in_game']).
    """
    return _j(_send("get_actor_properties",
                    {"actor_path": actor_path, "properties": properties}))


# ─── Assets ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_assets(directory: str = "/Game/", recursive: bool = True,
                class_filter: str = "") -> str:
    """List assets in a Content Browser directory.

    Args:
        directory:    Content path (e.g. '/Game/', '/Game/Materials/').
        recursive:    Include subdirectories (default True).
        class_filter: Class name filter (e.g. 'Material', 'StaticMesh').
    """
    return _j(_send("list_assets", {"directory": directory,
                                    "recursive": recursive,
                                    "class_filter": class_filter}))


@mcp.tool()
def get_asset_info(asset_path: str) -> str:
    """Get detailed info (class, package, path) about an asset.

    Args:
        asset_path: Full asset path (e.g. '/Game/Materials/M_Base').
    """
    return _j(_send("get_asset_info", {"asset_path": asset_path}))


@mcp.tool()
def get_selected_assets() -> str:
    """Get assets currently selected in the Content Browser."""
    return _j(_send("get_selected_assets"))


@mcp.tool()
def rename_asset(old_path: str, new_path: str) -> str:
    """Rename or move an asset.

    Args:
        old_path: Current asset path.
        new_path: New destination path.
    """
    return _j(_send("rename_asset", {"old_path": old_path, "new_path": new_path}))


@mcp.tool()
def delete_asset(asset_path: str) -> str:
    """Delete an asset permanently.

    Args:
        asset_path: Full asset path to delete.
    """
    return _j(_send("delete_asset", {"asset_path": asset_path}))


@mcp.tool()
def duplicate_asset(source_path: str, dest_path: str) -> str:
    """Duplicate an asset to a new path.

    Args:
        source_path: Source asset path.
        dest_path:   Destination asset path.
    """
    return _j(_send("duplicate_asset", {"source_path": source_path,
                                        "dest_path": dest_path}))


@mcp.tool()
def does_asset_exist(asset_path: str) -> str:
    """Check if an asset exists at the given path.

    Args:
        asset_path: Asset path to check.
    """
    return _j(_send("does_asset_exist", {"asset_path": asset_path}))


@mcp.tool()
def save_asset(asset_path: str) -> str:
    """Save a modified asset to disk.

    Args:
        asset_path: Asset path to save.
    """
    return _j(_send("save_asset", {"asset_path": asset_path}))


@mcp.tool()
def import_asset(
    source_file: str,
    destination_path: str,
    replace_existing: bool = True,
    save: bool = True,
) -> str:
    """Import an external file (FBX, PNG, WAV, etc.) into the Content Browser.

    Args:
        source_file:      Absolute path to the file on disk.
        destination_path: Content Browser destination (e.g. '/Game/Imports').
        replace_existing: Overwrite if an asset at that path already exists.
        save:             Save the imported asset immediately.
    """
    return _j(_send("import_asset", {
        "source_file":       source_file,
        "destination_path":  destination_path,
        "replace_existing":  replace_existing,
        "save":              save,
    }))


@mcp.tool()
def search_assets(class_name: str = "", directory: str = "/Game/",
                  recursive: bool = True) -> str:
    """Search for assets using the Asset Registry.

    Args:
        class_name: Class name filter (e.g. 'Material', 'Texture2D', 'StaticMesh').
        directory:  Directory to search.
        recursive:  Include subdirectories.
    """
    return _j(_send("search_assets", {"class_name": class_name,
                                      "directory": directory,
                                      "recursive": recursive}))


# ─── Materials ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_material_instance(
    parent_path: str,
    instance_name: str,
    destination: str = "/Game/Materials",
    scalar_params: Optional[dict] = None,
    vector_params: Optional[dict] = None,
    texture_params: Optional[dict] = None,
) -> str:
    """Create a new MaterialInstanceConstant from a parent material.

    Args:
        parent_path:    Content path to the parent Material (e.g. '/Game/Materials/M_Master').
        instance_name:  Name for the new MI asset (e.g. 'MI_TeamRed').
        destination:    Content Browser destination folder.
        scalar_params:  {param_name: float} — e.g. {"Roughness": 0.2, "Metallic": 0.9}
        vector_params:  {param_name: [r,g,b,a]} — e.g. {"BaseColor": [1.0, 0.1, 0.1, 1.0]}
        texture_params: {param_name: asset_path} — e.g. {"DiffuseTex": "/Game/T_Rock"}
    """
    return _j(_send("create_material_instance", {
        "parent_path":    parent_path,
        "instance_name":  instance_name,
        "destination":    destination,
        "scalar_params":  scalar_params or {},
        "vector_params":  vector_params or {},
        "texture_params": texture_params or {},
    }))


@mcp.tool()
def batch_exec(commands: list[dict]) -> str:
    """Execute multiple bridge commands in a single UEFN editor tick.

    Faster than sending commands one-by-one for multi-step sequences.
    Each entry: {"command": "name", "params": {...}}

    Example:
        batch_exec([
            {"command": "run_tool", "params": {"tool_name": "snapshot_save"}},
            {"command": "run_tool", "params": {"tool_name": "bulk_align",
                                               "kwargs": {"axis": "Z"}}},
            {"command": "save_current_level", "params": {}},
        ])
    """
    return _j(_send("batch_exec", {"commands": commands}, timeout=120.0))


@mcp.tool()
def undo() -> str:
    """Undo the last action in the UEFN editor."""
    return _j(_send("undo"))


@mcp.tool()
def redo() -> str:
    """Redo the last undone action in the UEFN editor."""
    return _j(_send("redo"))


@mcp.tool()
def get_history(tail: int = 30) -> str:
    """Get recent command history with per-command timing (elapsed_ms)."""
    return _j(_send("history", {"tail": tail}))


# ─── Level ────────────────────────────────────────────────────────────────────


@mcp.tool()
def save_current_level() -> str:
    """Save the current level to disk."""
    return _j(_send("save_current_level"))


@mcp.tool()
def get_level_info() -> str:
    """Get info about the current level: world name and actor count."""
    return _j(_send("get_level_info"))


# ─── Viewport ─────────────────────────────────────────────────────────────────


@mcp.tool()
def get_viewport_camera() -> str:
    """Get the current editor viewport camera location and rotation."""
    return _j(_send("get_viewport_camera"))


@mcp.tool()
def set_viewport_camera(
    location: Optional[list[float]] = None,
    rotation: Optional[list[float]] = None,
) -> str:
    """Move the editor viewport camera.

    Args:
        location: [x, y, z] world coordinates.
        rotation: [pitch, yaw, roll] in degrees.
    """
    params: dict[str, Any] = {}
    if location: params["location"] = location
    if rotation: params["rotation"] = rotation
    return _j(_send("set_viewport_camera", params))


# ─── Verse Book (spec-aware code generation) ──────────────────────────────────


def _verse_book_missing() -> str:
    return (
        "verse-book not found at expected path.\n"
        "Fix: cd to the project root and run:\n"
        "  git clone https://github.com/verselang/book.git verse-book"
    )


@mcp.tool()
def verse_book_search(query: str, context_lines: int = 8) -> str:
    """Search the authoritative Verse language spec for a keyword or concept.

    Always call this before writing Verse code to verify syntax.
    Returns matching sections with surrounding context from all spec chapters.

    Args:
        query:         Keyword, specifier, or concept to look up
                       (e.g. 'suspends', 'editable', 'creative_device', 'race',
                       'Subscribe', 'map', 'option', 'interface').
        context_lines: Lines of context around each match (default 8).

    Examples:
        verse_book_search("suspends")          # effect specifier syntax
        verse_book_search("@editable")         # device property declarations
        verse_book_search("race block")        # concurrency race pattern
        verse_book_search("Subscribe")         # event subscription pattern
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for fname in sorted(os.listdir(VERSE_BOOK_PATH)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(VERSE_BOOK_PATH, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        i = 0
        while i < len(lines):
            if pattern.search(lines[i]):
                start = max(0, i - context_lines)
                end   = min(len(lines), i + context_lines + 1)
                snippet = "".join(lines[start:end])
                results.append(f"### {fname} — line {i + 1}\n{snippet}")
                i = end  # skip past this match block
            else:
                i += 1

    if not results:
        return f"No matches for '{query}' in the Verse spec."

    capped = results[:12]
    header = f"// {len(results)} match(es) for '{query}' — showing {len(capped)}\n\n"
    return header + "\n---\n".join(capped)


@mcp.tool()
def verse_book_chapter(topic: str) -> str:
    """Fetch a complete chapter from the Verse language spec by topic.

    Use when you need full coverage of a language area before generating code.
    Chapters are pulled from the live verse-book clone — always current.

    Args:
        topic: Topic name. Supported values:
               overview, expressions, primitives, containers, operators,
               mutability, functions, control, failure, structs, enums,
               classes, interfaces, types, access, effects, concurrency,
               async, live_variables, modules, persistable, evolution,
               syntax, index.

    Examples:
        verse_book_chapter("concurrency")   # async/suspends/race/sync
        verse_book_chapter("classes")       # class/interface/inheritance
        verse_book_chapter("failure")       # failable expressions, decides
        verse_book_chapter("effects")       # effect specifiers: computes/reads/writes
    """
    if not os.path.isdir(VERSE_BOOK_PATH):
        return _verse_book_missing()

    topic_key = topic.lower().replace(" ", "_").replace("-", "_")
    fname = _VERSE_CHAPTERS.get(topic_key)

    if fname is None:
        # Fuzzy fallback — partial match
        for key, f in _VERSE_CHAPTERS.items():
            if topic_key in key or key in topic_key:
                fname = f
                break

    if fname is None:
        available = sorted(set(_VERSE_CHAPTERS.keys()))
        return f"Unknown topic '{topic}'.\nAvailable topics: {available}"

    fpath = os.path.join(VERSE_BOOK_PATH, fname)
    try:
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        return f"// {fname}  ({len(content.splitlines())} lines)\n\n{content}"
    except Exception as e:
        return f"Error reading {fname}: {e}"


@mcp.tool()
def verse_book_update() -> str:
    """Pull the latest Verse spec from upstream (git pull on verse-book/).

    Run this when Epic releases Verse language updates to stay current.
    Returns the git output showing what changed.
    """
    book_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verse-book")
    if not os.path.isdir(os.path.join(book_root, ".git")):
        return _verse_book_missing()
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=book_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return f"// git pull — verse-book\n{output}"
    except subprocess.TimeoutExpired:
        return "git pull timed out after 30s."
    except Exception as e:
        return f"git pull failed: {e}"


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Allow --port override: python mcp_server.py --port 8766
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--port" and i < len(sys.argv) - 1:
            LISTENER_PORT = int(sys.argv[i + 1])
            LISTENER_URL  = f"http://127.0.0.1:{LISTENER_PORT}"

    mcp.run()
