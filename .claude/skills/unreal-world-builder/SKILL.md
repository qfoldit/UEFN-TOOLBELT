---
name: unreal-world-builder
description: Takes a validated Universal Assembly Graph (UAG) produced by the game-designer skill and realizes it in UEFN by calling this repo's own MCP tools (run_toolbelt_tool, qfoldit_* tools). Use this skill whenever a UAG needs to be turned into actual placed actors/lights/audio/particles in a live UEFN project, or when the user asks to "build"/"export"/"spawn" a UAG scene into Unreal/UEFN specifically. Do NOT use this for Unity/Unigine/OpenUSD/RealityKit/Three.js targets -- those need their own adapter skills, which do not live in this repo (this repo is UEFN-specific).
---

# unreal-world-builder

## Purpose

The UEFN-facing half of the UAG -> engine pipeline. `game-designer` produces an engine-neutral scene graph; this skill is the ONLY skill in this repository that turns that graph into real actors inside a live UEFN project, by calling the MCP tools this repo already exposes (`mcp_server.py`) rather than any hypothetical new integration.

This skill deliberately covers Unreal/UEFN only. The UAG schema (`uag_schema.md`) lists five other engine targets (Unity, UNIGINE, OpenUSD, RealityKit, Three.js) — those belong to separate adapter skills that are not part of this repository. Don't attempt to fake their behavior here.

## Preconditions

1. The UAG must already be validated: run `python3 .claude/skills/game-designer/scripts/uag_validate.py <file>` (or, if the UAG came from `qfoldit_gamedesign_to_uag_seed`, it's already validated in the tool's own response) and confirm `"valid": true` before touching anything below. A UAG with unresolved `errors` must not be exported — this mirrors the exact rule in `game-designer/SKILL.md` step 4.
2. A live UEFN project/editor connection must be reachable via this repo's MCP bridge (the same connection `run_toolbelt_tool` and `list_toolbelt_tools` already use). If it isn't, say so plainly rather than pretending actors were placed.
3. Every `mesh_ref` / asset name that ends up as a tool-call argument goes through `TrustRuntime` automatically — `run_toolbelt_tool` calls `_trust.evaluate()` internally (see `mcp_server.py`) before anything reaches the editor. This skill does not need its own separate IP check; it inherits the same default-deny gate (entertainment-IP watchlist plus, if the project opted in via `TrustRuntime.with_extended_watchlist()`, the scientific-equipment/vehicle trademark watchlists too). If a call comes back blocked, report the block reason to the user — do not try to reword the asset name to sneak past it.

## Node/constraint/interaction -> tool mapping

This table only lists mappings that are backed by a real, existing tool in `Content/Python/UEFN_Toolbelt/tools/` — verified by grep against this checkout, not assumed. Anything not in this table is a genuine gap (see "Known gaps" below); per `uag_schema.md`'s own validation rule, an unmapped node must be reported to the user, never silently skipped.

| UAG element | UEFN Toolbelt tool (via `run_toolbelt_tool`) | Notes |
|---|---|---|
| `node type=mesh` | `import_fbx` (new asset) or `stamp_place` (existing saved prefab/stamp) | Choose based on whether `properties.mesh_ref` points to an external file or an already-imported/stamped prefab name. |
| `node type=light` | `light_place` (`light_type`, `intensity`, position from the node's `transform`) | Follow with `light_set` if `properties.color`/`intensity` need adjusting after placement. |
| `node type=trigger_volume` | `zone_spawn` | Use the node's `transform` for placement/extent; `zone_resize_to_selection` if the volume needs to match spawned contents instead of a fixed size. |
| `node type=particle_emitter` | `niagara_spawn_system` | `properties` should carry the Niagara system asset path this maps to `asset_path`. |
| `node type=audio_source` | `audio_place` | `properties` should carry `asset_path`; follow with `audio_set_volume`/`audio_set_radius` for `properties.intensity`-equivalent fields. |
| `node type=group` | No direct tool — group nodes are structural only. Realize each child node individually; use `actor_cluster_to_folder` afterward if the group should also become an editor-outliner folder. |
| `connection type=parent_child` | Re-parent via the relevant placement tool's own parenting args if it exposes one, otherwise `actor_place_next_to`/`actor_chain_place` for spatial (not true scene-graph) parenting — UEFN's actor attachment isn't uniformly exposed across every tool, verify per-tool before assuming true attachment happened. |
| `constraint type=physics_collision` | `physics_add` | |
| `interaction trigger=on_grab` / `on_proximity` / etc. | `device_set_property` / `device_call_method` on the relevant Verse device (e.g. a Prop Manipulator or Trigger Device) | This is the one place native Verse device wiring, not a Python actor-placement tool, is the correct target — say so to the user rather than forcing a placement-tool call that doesn't apply. |

## Known gaps — report these, don't paper over them

- **`node type=camera`**: no tool in this repo spawns a persistent in-game `CameraActor`. `viewport_camera_get`/`viewport_move_to_camera` only move the *editor* viewport camera, and `seq_actor_to_spline`/`seq_batch_keyframe` (Sequencer tools) only animate an existing camera along a path. If a UAG needs a real in-game camera actor, tell the user this is unimplemented in the current toolbelt rather than approximating it with the viewport camera.
- **`node type=ui_panel`**: no toolbelt tool spawns Verse UI widgets. This repo's Verse-side tools (`verse_snippet_generator.py`, `verse_templates.py`) generate/lint Verse *code*, they don't place a runtime UI panel actor. Tell the user this needs hand-written or generated Verse UI code, not a `run_toolbelt_tool` call.
- **`node type=custom`**: by definition schema-less — ask the user what it should map to rather than guessing.

## Workflow

1. Validate the UAG (see Preconditions #1). Stop and report if invalid.
2. Call `qfoldit_scene_build_start()` and keep its `since_ts` value — this brackets everything that follows so it can later be proven to have gone through the licensing gate, object by object, not just asserted.
3. Walk `nodes` in an order that respects `parent_id` (parents before children) so re-parenting calls have something to attach to.
4. For each node, look it up in the mapping table above and call the corresponding tool via `run_toolbelt_tool(tool_name, kwargs)`, translating `transform.position`/`rotation_euler_deg`/`scale` into that tool's own position/rotation/scale kwargs (check the tool's own docstring via `list_toolbelt_tools()` for its exact parameter names — they are not identical across every tool).
5. Apply `constraints` and `interactions` after all nodes exist, since they reference node ids that must already have real actors behind them.
6. For anything in "Known gaps," stop and tell the user explicitly instead of silently dropping the node — same principle `uag_validate.py` already enforces for unmapped types at the schema level.
7. Report back what was actually placed (and what was blocked by `TrustRuntime`, and what fell into a known gap) — don't claim success for nodes that were skipped for either reason.
8. If this build is part of a reproducible-experiment record (see `qfoldit/science/experiment_record.py`), pass the `since_ts` from step 2 as `qfoldit_build_experiment_record`'s `auto_collect_licensing_since` argument. This pulls in the real TrustRuntime decision for every `run_toolbelt_tool` call made during this build — not just the science-tool calls — so the resulting record's `publication_checklist.licensing_all_cleared` is evidence about the whole scene, not only about how the science was generated.
