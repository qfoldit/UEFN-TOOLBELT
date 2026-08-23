# Migration Notice — UEFN Toolbelt

## Canonical destination

qFoldIT is consolidating UEFN Toolbelt functionality into:

**https://github.com/qfoldit/UEFN-QFOLDIT**

This repository remains the lineage/reference distribution while the reusable tool definitions, verification metadata and runtime adapter are integrated into the qFoldIT Scientific Cockpit.

## Target architecture

```text
UAG / Mission Contract
        ↓
Scientific Action Envelope
        ↓
Mission Permission
        ↓
UEFN Toolbelt Adapter
        ↓
UEFN MCP / UEFN Runtime
```

## Consolidation rule

Tool definitions should not own scientific truth or authorization. They become runtime capabilities invoked through qFoldIT's canonical permission and provenance layer.

Upstream license and attribution obligations remain intact. The qFoldIT implementation is independently governed by its own repository license and provenance policy.

## Status

**Legacy / consolidation source — new qFoldIT runtime development belongs in `UEFN-QFOLDIT`.**
