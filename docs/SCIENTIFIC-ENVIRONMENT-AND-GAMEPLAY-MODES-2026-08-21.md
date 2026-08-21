# qFoldIT Scientific Environment & Gameplay Modes

**Version:** 1.0
**Status:** Cross-engine capability contract alignment

## Purpose

UEFN runtime missions should be able to visualize scientific processes as part of gameplay rather than as separate screens.

## Scientific environment capabilities

The adapter is aligned to the qFoldIT scientific-environment contract with the following target capability family:

- particle systems;
- fluid/liquid visualization;
- volumetric effects;
- scalar/vector field visualization;
- thermal and energy fields;
- diffusion and dissolution;
- reaction/procedural effects;
- scientific and reactive materials;
- transparent and bio-material surfaces.

## Gameplay modes

In addition to research, arena, co-op, sandbox and validation modes, UEFN missions should support:

- **Build Mode** — spatial construction under scientific constraints.
- **Racing Mode** — time/route optimization where motion, geometry or process parameters are the search space.

## Quantum scheduling

Every mission may carry a Quantum Opportunity Score policy. UEFN gameplay should expose quantum execution as a meaningful state transition and record the policy/version in mission provenance.

## Runtime boundary

Scientific visualization is an interaction surface. Authoritative scientific validation remains external to the runtime.

## Implementation path

1. canonical environment profile;
2. engine-specific visual primitives;
3. UAG bindings;
4. gameplay-mode templates;
5. mission routing capability matching;
6. realtime event capture;
7. scientific validation reconciliation.
