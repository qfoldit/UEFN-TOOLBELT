# UEFN TOOLBELT — Full Pipeline Demo
# ====================================
# Run this in the UEFN Python REPL (Output Log > Python (REPL) tab)
# to see the complete 8-phase AI game-building pipeline live.
#
# Prerequisites:
#   1. UEFN is open with a BLANK TEMPLATE LEVEL (not a production project)
#   2. UEFN Toolbelt is installed (Content/Python/ contains UEFN_Toolbelt/)
#   3. Nuclear reload first — paste this into the REPL:
#      import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
#
# Each block below is a separate paste into the REPL.
# Wait for each block to complete before running the next (Quirk #22).
# ⚠️ Phases 1–3 are read-only. Phase 4 onward modifies the level.

import UEFN_Toolbelt as tb

# ------------------------------------------------------------------
# PHASE 0 — RECON: Know the level before touching it
#
# Exports every actor in the level (transforms, class, folder,
# bounds, asset path, tags) to Saved/UEFN_Toolbelt/world_state.json.
# The summary block at the top shows class counts + folder map —
# read that first for a quick level overview.
# ------------------------------------------------------------------
result = tb.run("world_state_export")
print(f"Actors exported: {result.get('actor_count')}")
print(f"Output: {result.get('output_path')}")


# ------------------------------------------------------------------
# PHASE 1 — RECON: Build the device palette
#
# Scans the Asset Registry for every Creative device Blueprint
# available in Fortnite (not just what's placed — the full catalog).
# Writes device_catalog.json — Claude reads this to pick devices.
# ------------------------------------------------------------------
result = tb.run("device_catalog_scan")
print(f"Devices found: {result.get('device_count')}")
print(f"Output: {result.get('output_path')}")


# ------------------------------------------------------------------
# PHASE 2 — HEALTH CHECK: Level audit before building
#
# Runs 6 audit categories: actors, memory, assets, naming,
# LODs, performance. Returns a score 0–100 with grade (A+…F)
# and ordered list of issues to fix before publishing.
# ------------------------------------------------------------------
result = tb.run("level_health_report")
print(f"Health score: {result.get('score')}/100  ({result.get('grade')})")
print(f"Status: {result.get('overall_status')}")
for issue in result.get("top_issues", [])[:5]:
    print(f"  • {issue}")


# ------------------------------------------------------------------
# PHASE 3 — SCAFFOLD: Professional folder structure + Verse skeleton
#
# Creates 56 content folders in the Content Browser and generates
# a wired Verse game manager skeleton (creative_device subclass,
# @editable refs, OnBegin stub) deployed to the Verse source dir.
# ------------------------------------------------------------------
result = tb.run("project_setup", project_name="MyGame")
print("Verse file:", result.get("verse_path"))
print("Next steps:", result.get("next_steps"))


# ------------------------------------------------------------------
# PHASE 4 — LAYOUT: Spawn a symmetrical competitive arena
#
# Places floor tiles, walls, and ramp platforms in a symmetric
# Red vs Blue layout. Fully undoable (Ctrl+Z).
# Change size to "small", "large", or "extra_large".
# ------------------------------------------------------------------
result = tb.run("arena_generate", size="medium", apply_team_colors=True)
print(f"Arena: {result.get('placed')} actors placed")
print(f"  Red spawns: {result.get('red_spawns')}")
print(f"  Blue spawns: {result.get('blue_spawns')}")


# ------------------------------------------------------------------
# PHASE 5 — VERSE: Deploy a battle-tested game template
#
# Lists available templates first, then deploys one.
# Templates are production-tested skeletons: elimination scoring,
# zone capture, round flow, item spawner cycle, countdown race.
# Claude reads verse_template_list, picks the right one, fills in
# device labels from world_state.json, then deploys.
# ------------------------------------------------------------------
result = tb.run("verse_template_list")
print("Available templates:")
for t in result.get("templates", []):
    print(f"  {t['name']:30s}  {t['description']}")

# Deploy the elimination scoring template
result = tb.run("verse_template_deploy",
                name="elimination_scoring",
                filename="game_manager.verse",
                overwrite=True)
print("Deployed:", result.get("verse_path"))


# ------------------------------------------------------------------
# PHASE 6 — BUILD: Trigger Verse compilation
#
# One manual step: In UEFN, click Verse → Build Verse Code.
# Wait for the build to finish, then run Phase 7.
# ------------------------------------------------------------------
# [User clicks Build Verse in UEFN menu]


# ------------------------------------------------------------------
# PHASE 7 — ERROR LOOP: Read errors, fix, redeploy
#
# Reads the build log, extracts structured errors (file, line, col,
# message, error_type, fix_hint) + full content of every erroring
# .verse file so Claude can fix and redeploy in one shot.
# Repeat until build_status == "SUCCESS".
# ------------------------------------------------------------------
result = tb.run("verse_patch_errors")
print("Build status:", result.get("build_status"))
print("Errors:", result.get("error_count"))
if result.get("errors_by_file"):
    for filepath, errors in result["errors_by_file"].items():
        print(f"\n  {filepath}:")
        for e in errors[:3]:
            print(f"    Line {e['line']}: [{e.get('error_type','?')}] {e['message']}")
            if e.get("fix_hint"):
                print(f"    Fix: {e['fix_hint']}")


# ------------------------------------------------------------------
# PHASE 8 — VERIFY + CHECKPOINT
#
# Re-export world state to confirm level matches design intent,
# run a publish readiness audit (actor budget, required devices,
# Verse build status, memory, redirectors), then save a snapshot.
# ------------------------------------------------------------------
result = tb.run("publish_audit")
print(f"Publish ready: {result.get('overall_status')}")
print(f"Score: {result.get('score')}")
for step in result.get("next_steps", [])[:5]:
    print(f"  → {step}")

result = tb.run("snapshot_save", name="demo_v1")
print(f"Checkpoint saved: {result.get('snapshot_name')}")
print(f"  Actors: {result.get('actor_count')}")
print(f"  Path:   {result.get('output_path')}")


# ------------------------------------------------------------------
# BONUS — TEXTURE AUDIT: Catch oversized textures before publishing
# ------------------------------------------------------------------
result = tb.run("texture_audit")
print(f"Textures audited: {result.get('total_audited')}")
for t in result.get("oversized", [])[:5]:
    print(f"  ⚠ {t['name']}  {t.get('width')}×{t.get('height')}  {t.get('compression')}")


# ------------------------------------------------------------------
# BONUS — ACTIVITY LOG: Review everything the toolbelt did this session
# ------------------------------------------------------------------
result = tb.run("toolbelt_activity_stats")
print(f"Tools called: {result.get('total_calls')}")
print(f"Error rate:   {result.get('error_rate_pct')}%")
print(f"Slowest:      {result.get('slowest_tool')}")
print(f"Most called:  {result.get('most_called_tool')}")
