---
name: game-designer
description: Produces a Universal Assembly Graph (UAG) -- qFoldIT's engine-neutral JSON scene/interaction plan -- from a natural-language description of a scene, an interaction concept, or the output of another qFoldIT science skill (e.g. plant-growth, mining). Use this skill whenever the user wants to design a game world, interactive environment, gameplay system, or level BEFORE targeting a specific engine, or when they explicitly ask for a "Universal Assembly Graph"/UAG. This skill does NOT talk to any engine directly -- for that, hand the resulting UAG to one of the engine-adapter skills (unreal-world-builder, unity-experience-builder, unigine-simulation-engineer, openusd-architect, apple-spatial-designer, threejs-web-designer).
---

# game-designer

## Purpose

Turns a scene/gameplay concept into a validated **Universal Assembly Graph (UAG)** -- see `references/uag_schema.md` for the full schema. This is the FIRST step of the qFoldIT digital-twin pipeline; every engine-specific skill in this plugin consumes a UAG produced here rather than reimplementing scene-design logic per engine.

## Workflow

1. **Gather the scene intent.** What is being represented (a greenhouse, a molecular VR lab, an ore-body prospecting map)? Is there qFoldIT science-skill output feeding it (e.g. `plant-growth` morphology multipliers, `mining` bio-oxidation results)? If the user hasn't specified, ask -- don't invent scientific parameters that should come from the relevant science skill instead.
2. **Design nodes.** Break the scene into `nodes` (mesh/light/camera/trigger_volume/ui_panel/particle_emitter/audio_source/group/custom) per the schema. Keep transforms and properties engine-agnostic -- no engine class names here (see "Principle" in the schema doc).
3. **Design connections/constraints/interactions.** Parent/child hierarchy, physics/interaction constraints, and trigger-based interactions (on_grab, on_proximity, etc.) as needed for the concept.
4. **Validate.** Run `scripts/uag_validate.py <file>` (this validator is shared -- the same script lives in every downstream engine skill's expectations, so a UAG that fails here will fail everywhere). Fix all `errors` before proceeding; review `warnings` (usually node/trigger types without a known engine mapping yet) and flag them to the user rather than silently dropping them.
5. **Hand off.** Tell the user which engine-adapter skill(s) are appropriate for their target platform, and pass the validated UAG JSON to that skill. Do not attempt engine-specific work yourself -- that's what `digital-twin-builder` (for simulation semantics) and the per-engine skills are for.

## Example

```bash
python3 scripts/uag_validate.py my_scene.uag.json
```

Output is `{"valid": true/false, "errors": [...], "warnings": [...], "node_count": N}` -- see the script for exact validation rules (unique ids, valid references, no parent_child cycles).

## What this skill deliberately does NOT do

- Does not call any engine's MCP tools directly (no ModelContextProtocol, unity-mcp, kit-usd-agents calls here).
- Does not invent scientific/engineering numbers -- if a node's properties should come from `plant-growth`, `mining`, etc., use that skill's actual output, don't approximate it here.
- Does not skip validation -- an unvalidated UAG handed to an engine skill risks silent partial export (missing nodes, broken hierarchy).
