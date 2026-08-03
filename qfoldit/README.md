# qFoldIT — inside UEFN-TOOLBELT

Everything from the qFoldIT project (compliance gate, science pipeline,
monetization) now lives here as one self-contained package, instead of
loose files at the repo root. `mcp_server.py` imports from here; nothing
outside this folder should need its own copy of qFoldIT data.

```
qfoldit/
  compliance/
    trust_runtime.py        TrustRuntime — default-deny IP watchlist/manifest
                             gate in front of run_toolbelt_tool/execute_python,
                             plus engine-backed asset provenance verification.
    license_manifest.json   Documented brand license terms (LEGO, TMNT, Star
                             Wars, etc.) — royalty %, scope, content_plugin_ids.
    watchlist_loader.py     Optional extension loader — merges DEFAULT_WATCHLIST
                             with real-world trademark term sets from
                             watchlists/*.json. Opt-in via
                             TrustRuntime.with_extended_watchlist(); a plain
                             TrustRuntime() is unaffected.
    watchlists/
      scientific_equipment_watchlist.json  Lab/analytical-equipment brands
                             (Thermo Fisher, Agilent, Danaher sub-brands,
                             Eppendorf, Bruker, Illumina, etc.) — trademark
                             basis, no Epic IP Partner pathway exists for
                             these, so a match resolves to BLOCKED unless a
                             real creator_independent_license manifest entry
                             is added.
      vehicle_watchlist.json  Vehicle/heavy-equipment brands (amphibious ATVs,
                             articulated all-terrain vehicles, long-haul
                             trucks, construction equipment, passenger cars,
                             mining/tactical transport) — same
                             trademark/no-Epic-pathway basis. Several generic-
                             word brand names (e.g. words that collide with
                             "north" or "gas" once transliterated) are
                             documented but shipped 'enabled': false to avoid
                             false-positive noise from ordinary words — see
                             the file's _README before enabling them.
  science/
    mcp_registry.py         ScienceMCPRegistry — verified/connected/
                             best_effort/reference_only gate for which
                             scientific MCP servers auto-connect.
    science_mcp_registry.json
    exceptions.py           Shared exception types for the pipelines/.
    gamedesign.py            Deterministic (sha256-seeded, no LLM) generator
                             turning a science result into a game design doc
                             (levels, par scores, achievements).
    uag_bridge.py            Deterministic bridge from gamedesign.py's output
                             to a starter UAG (Universal Assembly Graph) for
                             the game-designer skill — see
                             ../.claude/skills/game-designer/. Produces a
                             skeleton (one 'group' node per level, no
                             meshes/lights invented), not a finished scene.
    experiment_record.py     ExperimentRecord — ties one run's science
                             result + TrustRuntime licensing decisions +
                             game-design seed + UAG metadata into one
                             sha256-identified record. Generates a
                             citation-grounded, quantum-vs-classical-honest
                             methods_section() and a named-boolean
                             publication_checklist() — never a bare
                             "publication ready: yes/no" without evidence.
    pipelines/
      quantum_runner.py     Two DIFFERENT capabilities — read the module
                             docstring before assuming either is "the
                             quantum backend":
                               1. predict_peptide_quantum_vqe() — a real
                                  CVaR-VQE wrapper (QuPepFold, PLOS ONE
                                  2026). Import-guarded: returns
                                  status="unavailable" (never a fabricated
                                  energy) unless the separate `qupepfold`
                                  package is installed.
                               2. simulate_quantum_walk_fold() — a REAL but
                                  CLASSICAL Metropolis simulation inspired
                                  by QFold (Casares et al. 2022), not a
                                  quantum computation. Has a documented,
                                  test-confirmed limitation: single-
                                  dihedral moves can leave chains ~14+
                                  residues kinetically trapped in a
                                  self-clashed state — see its docstring's
                                  "KNOWN LIMITATION" section before
                                  assuming "more steps = better fold".
  monetization/
    monetization_registry.py MonetizationRegistry — gates paid off-platform
                             commissions through the same IP watchlist, and
                             estimates Boltz-2 compute cost locally (no
                             network call) from boltz_pricing.json.
    monetization_channels.json
    boltz_pricing.json      Local rate table. rate_usd_per_gpu_second ships
                             as null on purpose — fill it in from your real
                             Modal billing before quoting a price.
  logs/                     Runtime-generated audit/connection/commission/
                             experiment-record logs (trust_audit.log.jsonl,
                             experiment_records.log.jsonl, etc.) — gitignore
                             this directory; nothing here should be committed.

../.claude/skills/
  game-designer/            Claude Skill (SKILL.md) — LLM-driven: turns a
                             scene concept (optionally seeded by
                             uag_bridge.to_source_context()) into a validated
                             Universal Assembly Graph. Engine-neutral; does
                             not itself talk to UEFN or any other engine.
  unreal-world-builder/     Claude Skill (SKILL.md) — the ONLY engine adapter
                             in this repo. Takes a validated UAG and realizes
                             it by calling this repo's own run_toolbelt_tool
                             MCP tool with real, grep-verified tool names
                             (light_place, zone_spawn, audio_place,
                             niagara_spawn_system, import_fbx, stamp_place,
                             device_set_property, ...). Documents its own
                             gaps (no camera-actor or ui_panel tool exists
                             yet) rather than papering over them. Every
                             asset name it passes through run_toolbelt_tool
                             is automatically checked by
                             compliance/trust_runtime.py — no separate
                             IP-compliance logic needed in this skill.
```

**Where this sits in the wider qFoldIT architecture:** `game-designer`/UAG and
`unreal-world-builder` are two middle layers of a larger stack described in
the (external, not-yet-integrated) MPNC visual-standards document — see
`STANDARTS.html`'s §7 "Integration with qFoldIT Architecture" for the full
7-layer map (SKG → SEM → UAG → UWI → MCP → UEFN-TOOLBELT). Only the UAG layer
(`game-designer`) and a UEFN-only slice of the UWI layer
(`unreal-world-builder`) exist in this repo; SKG/SEM live in a separate
`scientific-world-schema` repo that hasn't been brought in here, and the
other five engine adapters (Unity/UNIGINE/OpenUSD/RealityKit/Three.js) belong
to a sibling `qfoldit-universal-digital-twin` package this repo only
references by name (see the `reference_only` entries in
`science/science_mcp_registry.json`).

## MCP tools exposed (in `mcp_server.py`)

| Tool | Backed by |
|---|---|
| `qfoldit_check_license` / `qfoldit_list_licensed_brands` | `compliance/trust_runtime.py` |
| `qfoldit_connect_science_mcp` | `science/mcp_registry.py` |
| `qfoldit_evaluate_commission` | `monetization/monetization_registry.py` |
| `qfoldit_quantum_walk_fold` | `science/pipelines/quantum_runner.py` (classical simulation) |
| `qfoldit_quantum_vqe_fold` | `science/pipelines/quantum_runner.py` (real VQE, import-guarded) |
| `qfoldit_generate_game_design` | `science/gamedesign.py` |
| `qfoldit_gamedesign_to_uag_seed` | `science/uag_bridge.py` — hands off to `.claude/skills/game-designer/` |
| `qfoldit_scene_build_start` | `compliance/trust_runtime.py` (`now_ts()`) — timestamp marker to bracket a scene build |
| `qfoldit_collect_scene_licensing` | `compliance/trust_runtime.py` (`decisions_since()`) — read back real `run_toolbelt_tool` decisions |
| `qfoldit_build_experiment_record` | `science/experiment_record.py` — reproducibility + licensing + publication-checklist record; persists to `logs/experiment_records.log.jsonl` |
| `qfoldit_list_experiment_records` | `science/experiment_record.py` (`list_experiment_records()`) — read back persisted records |
| `qfoldit_trust_dashboard` (Content/Python tool, category: Dashboard) | reads `logs/` + the two manifests, read-only |

`run_toolbelt_tool` and `execute_python` are gated by `compliance/trust_runtime.py`
before reaching the live editor — see the main README's
[qFoldIT Trust & Compliance Layer](../README.md#qfoldit-trust--compliance-layer)
section for the full picture.

## Running the tests

```bash
cd UEFN-TOOLBELT-main
python3 tests/test_qfoldit_trust_runtime.py         # 16/16
python3 tests/test_qfoldit_science_mcp_registry.py  # 7/7
python3 tests/test_qfoldit_monetization_registry.py # 8/8
python3 tests/test_qfoldit_quantum_runner.py         # 12/12 — includes the
                                                      #   kinetic-trapping
                                                      #   limitation test
python3 tests/test_qfoldit_gamedesign.py             # 8/8 — includes a real
                                                      #   end-to-end run
                                                      #   against quantum_runner
python3 tests/test_qfoldit_watchlist_extensions.py   # 8/8 — scientific-
                                                      #   equipment/vehicle
                                                      #   watchlist extensions
python3 tests/test_qfoldit_uag_bridge.py             # 9/9 — includes a
                                                      #   sync-check against
                                                      #   the game-designer
                                                      #   skill's own validator
python3 tests/test_qfoldit_experiment_record.py       # 9/9 — includes a real
                                                      #   end-to-end run
                                                      #   against quantum_runner
python3 tests/test_qfoldit_scene_licensing_collection.py  # 8/8 — audit-log
                                                      #   read-back + record
                                                      #   persistence
```

## Main goal: gameplay as a reproducible scientific experiment

The project's stated north star is that every game object, action, and
computation should automatically correspond to licensing, scientific-
validity, and publication-readiness requirements. `experiment_record.py`
is the concrete piece that ties the rest of this together toward that goal:

- **Licensing** — every `TrustRuntime.evaluate()` decision that fed into a
  run is embedded verbatim in the record (not summarized/asserted), so a
  record with a `matched_terms`/blocked entry is automatically flagged
  `publication_ready: false` in `publication_checklist()`.
- **Scientific validity** — `methods_section()` pulls from a small,
  hand-checked citation table keyed to the ACTUAL algorithm, not the tool's
  marketing name: the classical Metropolis "quantum_walk" simulation is
  always described as classical, and the real VQE path always carries its
  own documented "not independently verified against qupepfold's real API"
  caveat forward into the generated text.
- **Reproducibility** — `experiment_id` is a sha256 hash over exactly the
  deterministic inputs/outputs (`reproduce_with` + `science_result` +
  `game_design_seed`), so two records with the same id are, by
  construction, the same experiment — this doesn't add new determinism, it
  just records the determinism `quantum_runner.py`/`gamedesign.py` already
  have.
- **Publication readiness is reported, not decided** —
  `publication_checklist()` returns named boolean checks (licensing
  cleared, science kind recognized, algorithm correctly labeled,
  reproduction recorded, verification caveat disclosed), not a single
  yes/no verdict. A human still makes the actual publication call.

**Closed:** scene-object licensing is now collected automatically, not just
science-tool calls. `TrustRuntime.decisions_since()` reads the runtime's own
audit log back out (every `run_toolbelt_tool` decision was already being
logged via `_audit()` — this just reads it back instead of leaving it
stranded in the log file). `qfoldit_scene_build_start()` returns a timestamp
marker to bracket one scene build; `unreal-world-builder` calls it before
placing anything and passes the marker to
`qfoldit_build_experiment_record(auto_collect_licensing_since=...)` when the
build finishes, so the resulting record's `publication_checklist` is
evidence about every placed object, not only about how the science was
generated. `qfoldit_collect_scene_licensing()` exposes the same read-back
standalone if you want to inspect it without building a full record.
Records are now also durable: `qfoldit_build_experiment_record` persists
every record it builds to `qfoldit/logs/experiment_records.log.jsonl`
(`qfoldit_list_experiment_records` reads it back), so a record isn't lost
the moment the MCP response scrolls out of context.

**Live server now uses the extended watchlist by default.** `mcp_server.py`'s
`_trust` instance is built with `TrustRuntime.with_extended_watchlist()`, not
plain `TrustRuntime()` — the scientific-equipment and vehicle trademark
watchlists (see above) are active in the running server, not just exercised
in tests. (The plain `TrustRuntime()` constructor's own default behavior is
still unchanged — that guarantee is what the extension's own opt-in test,
`test_default_trust_runtime_unaffected_when_extension_not_opted_in`, checks.)

**Still open, flagged rather than assumed solved:**
- `unreal-world-builder`'s "Known gaps" (no tool spawns a persistent
  `CameraActor` or a Verse UI panel) mean a UAG containing those node types
  can't be fully realized yet — the skill reports this rather than papering
  over it, but it's still a real capability gap for "every game object."
- `publication_checklist()` checks are necessary, not sufficient, for an
  actual publication — it can't verify the underlying science is *correct*,
  only that it's labeled honestly, reproducible, and cleared. Peer review
  still has to happen with a human.
- The five non-UEFN engine adapters (Unity/UNIGINE/OpenUSD/RealityKit/
  Three.js) referenced by `science_mcp_registry.json` still don't exist in
  this repo — an experiment whose scene targets one of those engines has no
  `*-world-builder` skill to realize it or collect its licensing decisions
  yet.

Tests stay in the top-level `tests/` folder (not nested inside `qfoldit/`)
so they run alongside the rest of the toolbelt's own test suite
(`smoke_test.py`) from one place — only the qFoldIT *code and data* moved.

## What's brought in so far vs. what's still outside

Brought into this folder and wired into `mcp_server.py` as real, tested MCP
tools: the IP compliance gate (now also covering scientific-equipment and
vehicle trademarks, opt-in), the science-MCP connection gate, commission
monetization + Boltz pricing, the classical quantum-walk folding simulation,
the import-guarded real VQE wrapper, the deterministic gamification layer,
and a deterministic bridge from that gamification layer into a starter UAG
scene graph. Also brought in, as Claude Skills under `../.claude/skills/`:
`game-designer` (UAG authoring) and `unreal-world-builder` (the UEFN-only
engine adapter that actually calls `run_toolbelt_tool`).

Not yet brought in (exists in the original qFoldIT/Protein-Design-MCP repo,
not copied here): the heavy structure-prediction pipelines that need GPU/model
weights (Boltz-2 structure prediction itself, ESMFold, AlphaFold2, RFdiffusion,
ProteinMPNN, PyRosetta), ADMET/ZairaChem bioactivity scoring, the full
cross-engine UWI translation layer (only the UEFN slice exists here, as
`unreal-world-builder` — Unity/UNIGINE/OpenUSD/RealityKit/Three.js adapters
live in a separate `qfoldit-universal-digital-twin` package this repo only
references by name), facility-twin/brick-kit level generators, and OpenUSD
spatial export. These are real and tested in their own repo (see its
`STATUS.md`) but pulling each one in cleanly (subprocess/conda-env wiring,
optional-dependency handling) is its own piece of work — flagged here rather
than silently left out.
