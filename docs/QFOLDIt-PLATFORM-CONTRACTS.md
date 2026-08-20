# qFoldIT Platform Contract Alignment

## Role

UEFN-TOOLBELT is the Unreal Editor for Fortnite runtime adapter within the qFoldIT platform. It is a runtime implementation, not the scientific source of truth.

## Canonical contracts

- `qfoldit.mission/1.0`
- `qfoldit.scientific-state/1.0`
- `qfoldit.uag/1.0`
- `qfoldit.engine-adapter/1.0`
- `qfoldit.event/1.0`

## Runtime responsibilities

UEFN may create and update interactive worlds, execute runtime gameplay logic, collect player actions, produce candidate structures and emit evidence references. Scientific validation remains delegated to the configured scientific validation service.

## Capability registry

The adapter manifest is the canonical runtime capability declaration. README inventories and examples should describe the manifest and verified implementation rather than becoming an independent capability source.

## Validation boundary

```text
UEFN runtime
  -> local/runtime checks
  -> submission/evidence
  -> mission orchestration
  -> scientific validator
  -> validated result
```

## State boundary

Runtime state is exported as a projection. Mission registry data and scientific validation records remain authoritative outside the engine.
