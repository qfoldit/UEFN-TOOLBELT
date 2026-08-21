# qFoldIT UEFN Toolbelt — Native Unreal MCP Compatibility

**Date:** 2026-08-21

## Purpose

UEFN now ships Unreal MCP inside the editor. qFoldIT UEFN-TOOLBELT is therefore positioned as a higher-level scientific/gameplay capability layer that operates through the vendor-supported editor/MCP surface rather than competing with or replacing Epic's MCP implementation.

## Verified vendor architecture

Epic's Fortnite 42.00 release made Unreal MCP available in UEFN. Epic documents an MCP server embedded in the UEFN editor process, reachable locally by MCP-compatible clients such as Claude Code, Cursor and MCP Inspector.

The native surface includes:

- Verse Scene Graph entity creation/modification;
- Verse file read/write;
- Creative device placement and property editing;
- play-session start/stop/inspection.

The documented local endpoint defaults to `http://127.0.0.1:8000/mcp`.

## qFoldIT layer

```text
Claude / MCP Client
       │
       ▼
Epic UEFN MCP
       │
       ▼
UEFN Editor APIs / Verse / Scene Graph
       │
       ▼
qFoldIT UEFN-TOOLBELT
       │
       ├── higher-level composite tools
       ├── UAG execution
       ├── mission-specific capability profiles
       ├── scientific quest/gameplay tasks
       ├── evidence/event instrumentation
       └── qFoldIT mission contract integration
       │
       ▼
CAMEO / Scientific Validator / Evidence
```

The qFoldIT Toolbelt should avoid reproducing low-level vendor primitives when the native MCP already exposes them. New qFoldIT tools should be justified by one or more of:

1. multi-step workflow compression;
2. scientific mission semantics;
3. UAG abstraction;
4. safety/policy enforcement;
5. evidence/provenance capture;
6. higher-level content or world-building automation;
7. human-compute / Attention Capture instrumentation.

## Claude compatibility

Epic documents Claude Code as an MCP-compatible client for UEFN. qFoldIT therefore treats Claude as a supported agentic client surface but does not require Anthropic-specific APIs in the Toolbelt implementation.

This keeps the Toolbelt client-agnostic and preserves interoperability with other MCP clients.

## Scientific authority boundary

UEFN/Verse execution is an interaction/runtime surface, not the authority for scientific truth.

The authoritative path remains:

`Mission → UAG → Runtime → Submission/Event → CAMEO → Scientific Validator → Evidence/Contribution Record`.

## Security note

Epic's current Unreal MCP documentation describes a local editor process boundary and states that the default server has no authentication layer and is not designed for remote use. qFoldIT integrations must not silently extend this endpoint into a remote production service. Corporate/scientific access control belongs at the qFoldIT gateway and evidence boundary.

## Design rule

**Native vendor MCP first; qFoldIT semantic/composite layer second.**

This maximizes compatibility, minimizes duplicated low-level tooling and keeps qFoldIT's differentiated value focused on scientific missions, UAG, higher-level orchestration, human-compute instrumentation and validation/evidence rather than ownership of the editor protocol itself.
